import os
import json
import boto3
import pg8000.native
from urllib.parse import unquote_plus
import logging


# LOGGING

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# AWS CLIENT

s3 = boto3.client("s3")


# DB CONFIG (ENV VARS)

DB_HOST = os.environ["DB_HOST"]
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]


# SQL: CREATE TABLE

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.rawg_games (
    id BIGINT PRIMARY KEY,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,

    released DATE,
    updated TIMESTAMPTZ,

    metacritic INTEGER,
    rating DOUBLE PRECISION,
    rating_top INTEGER,
    ratings_count INTEGER,
    reviews_text_count INTEGER,
    added INTEGER,
    suggestions_count INTEGER,

    reddit_count INTEGER,
    twitch_count INTEGER,
    youtube_count INTEGER,

    platforms JSONB,
    metacritic_platforms JSONB,
    esrb_rating JSONB,
    added_by_status JSONB,

    website TEXT,
    background_image TEXT,
    background_image_additional TEXT,

    processed_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""


# SQL UPSERT

UPSERT_SQL = """
INSERT INTO public.rawg_games (
    id, slug, name, released, updated,
    metacritic, rating, rating_top, ratings_count,
    reviews_text_count, added, suggestions_count,
    reddit_count, twitch_count, youtube_count,
    platforms, metacritic_platforms, esrb_rating, added_by_status,
    website, background_image, background_image_additional,
    processed_at, updated_at
)
VALUES (
    :id, :slug, :name, :released, :updated,
    :metacritic, :rating, :rating_top, :ratings_count,
    :reviews_text_count, :added, :suggestions_count,
    :reddit_count, :twitch_count, :youtube_count,
    :platforms::jsonb, :metacritic_platforms::jsonb,
    :esrb_rating::jsonb, :added_by_status::jsonb,
    :website, :background_image, :background_image_additional,
    now(), now()
)
ON CONFLICT (id) DO UPDATE SET
    slug = EXCLUDED.slug,
    name = EXCLUDED.name,
    released = EXCLUDED.released,
    updated = EXCLUDED.updated,
    metacritic = EXCLUDED.metacritic,
    rating = EXCLUDED.rating,
    rating_top = EXCLUDED.rating_top,
    ratings_count = EXCLUDED.ratings_count,
    reviews_text_count = EXCLUDED.reviews_text_count,
    added = EXCLUDED.added,
    suggestions_count = EXCLUDED.suggestions_count,
    reddit_count = EXCLUDED.reddit_count,
    twitch_count = EXCLUDED.twitch_count,
    youtube_count = EXCLUDED.youtube_count,
    platforms = EXCLUDED.platforms,
    metacritic_platforms = EXCLUDED.metacritic_platforms,
    esrb_rating = EXCLUDED.esrb_rating,
    added_by_status = EXCLUDED.added_by_status,
    website = EXCLUDED.website,
    background_image = EXCLUDED.background_image,
    background_image_additional = EXCLUDED.background_image_additional,
    updated_at = now();
"""


# HELPERS

def to_jsonb(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, str) and v.strip():
        try:
            return json.dumps(json.loads(v), ensure_ascii=False)
        except:
            return None
    return None

def i(v):
    try:
        return int(v) if v is not None else None
    except:
        return None

def f(v):
    try:
        return float(v) if v is not None else None
    except:
        return None

def clean_date(v):
    if not v or v in ("", "0000-00-00"):
        return None
    return v

def extract_games(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return payload["data"]
        if isinstance(payload.get("results"), list):
            return payload["results"]
        if "id" in payload:
            return [payload]
    return []

def clean_game(g):
    slug = (g.get("slug") or "").strip()
    name = (g.get("name") or "").strip()

    return {
        "id": i(g.get("id")),
        "slug": slug,
        "name": name,
        "released": clean_date(g.get("released")),
        "updated": clean_date(g.get("updated")),

        "metacritic": i(g.get("metacritic")),
        "rating": f(g.get("rating")),
        "rating_top": i(g.get("rating_top")),
        "ratings_count": i(g.get("ratings_count")),
        "reviews_text_count": i(g.get("reviews_text_count")),
        "added": i(g.get("added")),
        "suggestions_count": i(g.get("suggestions_count")),

        "reddit_count": i(g.get("reddit_count")),
        "twitch_count": i(g.get("twitch_count")),
        "youtube_count": i(g.get("youtube_count")),

        "platforms": to_jsonb(g.get("platforms_json") or g.get("platforms")),
        "metacritic_platforms": to_jsonb(g.get("metacritic_platforms_json")),
        "esrb_rating": to_jsonb(g.get("esrb_rating_json")),
        "added_by_status": to_jsonb(g.get("added_by_status_json")),

        "website": g.get("website"),
        "background_image": g.get("background_image"),
        "background_image_additional": g.get("background_image_additional"),
    }


# LAMBDA HANDLER

def lambda_handler(event, context):

    records = event.get("Records", [])
    if not records:
        logger.info("Evento sin records")
        return {"ok": True}

    conn = pg8000.native.Connection(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        timeout=30,
    )

    
    conn.run(CREATE_TABLE_SQL)

    total_files = 0
    total_rows = 0

    try:
        for r in records:
            bucket = r["s3"]["bucket"]["name"]
            key = unquote_plus(r["s3"]["object"]["key"])

            if not (key.startswith("rawg/data/") or key.startswith("rawg/daily/")):
                continue
            if not key.endswith(".json"):
                continue

            logger.info(f"Procesando archivo: {key}")
            total_files += 1

            obj = s3.get_object(Bucket=bucket, Key=key)
            payload = json.loads(obj["Body"].read().decode("utf-8"))

            games = extract_games(payload)
            logger.info(f"Juegos extraídos: {len(games)}")

            file_rows = 0
            for g in games:
                row = clean_game(g)
                if row["id"] is None or row["slug"] == "" or row["name"] == "":
                    continue

                conn.run(UPSERT_SQL, **row)
                file_rows += 1
                total_rows += 1

            
            conn.run("COMMIT")
            logger.info(f"Commit OK para {key} | filas: {file_rows}")

        logger.info(f"Archivos procesados: {total_files}")
        logger.info(f"Registros totales upserted: {total_rows}")

        return {"ok": True, "files": total_files, "rows": total_rows}

    finally:
        conn.close()
