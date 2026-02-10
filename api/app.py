import os
import re
import io
import base64
import traceback
import joblib
import pandas as pd
import requests
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
import sqlglot
from dotenv import load_dotenv
load_dotenv(".env", override=True)



# ENV Y CONFIGURACION

MODEL_PATH = os.getenv("MODEL_PATH", "model.joblib")

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_MODEL_NAME = os.getenv("HF_MODEL_NAME", "Qwen/Qwen2.5-Coder-7B-Instruct")

MAX_ROWS_TEXT = int(os.getenv("MAX_ROWS_TEXT", "50"))
MAX_ROWS_VISUAL = int(os.getenv("MAX_ROWS_VISUAL", "200"))
STATEMENT_TIMEOUT_MS = int(os.getenv("STATEMENT_TIMEOUT_MS", "7000"))

FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)
def safe_header_value(s: str, max_len: int = 800) -> str:
    s = (s or "").replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s

CATALOG_FORBIDDEN = re.compile(r"\b(pg_catalog|information_schema)\b", re.IGNORECASE)

app = FastAPI(title="RAWG FastAPI", version="1.4.0")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-SQL"],
)



# CARGAR MODELO

artifact = joblib.load(MODEL_PATH)

if isinstance(artifact, dict) and "pipeline" in artifact:
    PIPE = artifact["pipeline"]
    FEATURE_COLS = artifact.get("feature_cols", [])
    THRESHOLD = float(artifact.get("threshold", 0.5))
    SUCCESS_DEF = artifact.get("success_definition")
else:
    PIPE = artifact
    FEATURE_COLS = [
        "metacritic",
        "rating_top",
        "added",
        "reviews_text_count",
        "suggestions_count",
        "reddit_count",
        "twitch_count",
        "youtube_count",
        "release_year",
        "release_month",
        "days_since_release",
    ]
    THRESHOLD = 0.5
    SUCCESS_DEF = None



# DB ENGINE

_engine = None


def get_engine():
    global _engine
    if _engine is not None:
        return _engine

    if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
        raise RuntimeError("DB env vars missing")

    _engine = create_engine(
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
        pool_pre_ping=True,
    )
    return _engine


def run_sql(sql: str, max_rows: int) -> List[Dict[str, Any]]:
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS};"))
        res = conn.execute(text(sql))
        return [dict(r._mapping) for i, r in enumerate(res) if i < max_rows]



# TEXT2SQL 

def schema_hint() -> str:
    return (
        "Database: PostgreSQL\n"
        "Schema:\n"
        "- public.rawg_games(\n"
        "  id, name, slug, released, updated,\n"
        "  rating, ratings_count, metacritic, rating_top, added,\n"
        "  reviews_text_count, suggestions_count,\n"
        "  reddit_count, twitch_count, youtube_count\n"
        ")\n"
        "Rules:\n"
        "- Output ONLY ONE SQL query\n"
        "- READ ONLY: SELECT or WITH\n"
        "- Always include FROM public.rawg_games\n"
        "- If user says reviews use reviews_text_count\n"
    )


def extract_first_select(txt: str) -> str:
    t = (txt or "").strip()

    # If inside fenced code block, extract it
    m = re.search(r"```(?:sql)?\s*(.*?)\s*```", t, flags=re.I | re.S)
    if m:
        t = m.group(1).strip()

    # Extract from first SELECT/WITH to end (multiline)
    m2 = re.search(r"(?is)\b(SELECT|WITH)\b.*", t)
    if not m2:
        raise ValueError("No SQL returned")
    return m2.group(0).strip().rstrip(";")


def sanitize_sql(sql: str) -> str:
    s = (sql or "").strip().rstrip(";")

    if ";" in s:
        raise ValueError("Multiple statements")

    if "--" in s or "/*" in s or "*/" in s:
        raise ValueError("Comments not allowed")

    if FORBIDDEN.search(s):
        raise ValueError("Forbidden SQL")

    if CATALOG_FORBIDDEN.search(s):
        raise ValueError("System schemas not allowed")

    if not re.match(r"^(SELECT|WITH)\b", s, re.I):
        raise ValueError("Only SELECT/WITH allowed")

    if not re.search(r"\b(FROM|JOIN)\s+public\.rawg_games\b", s, re.I):
        raise ValueError("Must query public.rawg_games")

    sqlglot.parse_one(s, read="postgres")
    return s


def ensure_limit(sql: str, limit: int) -> str:
    m = re.search(r"(?is)\bLIMIT\s+(\d+)\b", sql)
    if m:
        n = int(m.group(1))
        if n > limit:
            sql = re.sub(r"(?is)\bLIMIT\s+\d+\b", f"LIMIT {limit}", sql)
        return sql
    return f"{sql}\nLIMIT {limit}"


def hf_generate_text(prompt: str) -> str:
    try:
        r = requests.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {HF_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "model": HF_MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 220,
            },
            timeout=90,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"HF generation failed: {str(e)}")


def generate_sql(question: str, mode: str) -> str:
    instruction = (
        "Return ONLY ONE PostgreSQL SQL query.\n"
        "READ ONLY: SELECT or WITH.\n"
        "Always include FROM public.rawg_games.\n"
        "No explanations.\n"
    )
    if mode == "visual":
        instruction += "Return EXACTLY two columns: label and value.\n"

    prompt = f"{schema_hint()}\n{instruction}\nQuestion: {question}\nSQL:"
    raw = hf_generate_text(prompt)
    sql = extract_first_select(raw)
    return sanitize_sql(sql)



# INPUT

class PredictIn(BaseModel):
    metacritic: Optional[float] = None
    rating_top: Optional[float] = None
    added: Optional[float] = None
    reviews_text_count: Optional[float] = None
    suggestions_count: Optional[float] = None
    reddit_count: Optional[float] = None
    twitch_count: Optional[float] = None
    youtube_count: Optional[float] = None
    release_year: Optional[int] = None
    release_month: Optional[int] = Field(default=None, ge=1, le=12)
    days_since_release: Optional[int] = Field(default=None, ge=0)


class AskTextIn(BaseModel):
    question: str


class AskVisualIn(BaseModel):
    question: str

@app.get("/health")
def health():
    return {"status": "ok"}


# PREDICT Y FASTAPI

def _predict_proba(pipe, X: pd.DataFrame) -> float:
    
    if hasattr(pipe, "predict_proba"):
        proba = pipe.predict_proba(X)
        # binary classifier -> class 1
        return float(proba[0][1])
    
    if hasattr(pipe, "predict"):
        y = pipe.predict(X)
        return float(y[0])
    raise RuntimeError("Model does not support predict_proba or predict")


@app.post("/predict")
def predict(inp: PredictIn):
    try:
        payload = inp.model_dump()
        
        X = pd.DataFrame([{c: payload.get(c, None) for c in FEATURE_COLS}])
        prob = _predict_proba(PIPE, X)
        pred = int(prob >= THRESHOLD)
        return {
            "threshold": THRESHOLD,
            "prob_success": prob,
            "pred_success": pred,
            "success_definition": SUCCESS_DEF,
            "features_used": FEATURE_COLS,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Predict failed: {str(e)}")


# ASK TEXT

@app.post("/ask-text")
def ask_text(inp: AskTextIn):
    try:
        sql = ensure_limit(generate_sql(inp.question, "text"), MAX_ROWS_TEXT)
        rows = run_sql(sql, MAX_ROWS_TEXT)
        return {"sql": sql, "rows": rows}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"ask-text failed: {str(e)}")



# ASK VISUAL 

@app.post("/ask-visual")
def ask_visual(inp: AskVisualIn):
    try:
        sql = ensure_limit(generate_sql(inp.question, "visual"), MAX_ROWS_VISUAL)
        rows = run_sql(sql, MAX_ROWS_VISUAL)

        df = pd.DataFrame(rows)
        if df.empty:
            raise HTTPException(status_code=404, detail="No rows returned")

        if "label" not in df.columns or "value" not in df.columns:
            df = df.iloc[:, :2].copy()
            df.columns = ["label", "value"]

        df["label"] = df["label"].astype(str).str.slice(0, 40)
        df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0)

        
        df = df.sort_values("value", ascending=False).head(30)

        import matplotlib.pyplot as plt

        plt.figure(figsize=(10, 5))
        plt.bar(df["label"], df["value"])
        plt.title(inp.question)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=160)
        plt.close()
        buf.seek(0)

        return StreamingResponse(
    buf,
    media_type="image/png",
    headers={"X-SQL": safe_header_value(sql)},
)


    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"ask-visual failed: {str(e)}")