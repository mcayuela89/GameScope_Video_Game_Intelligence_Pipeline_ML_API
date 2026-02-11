import json
import os
import boto3
import urllib.request
import urllib.error
from datetime import datetime, timedelta
import time

s3 = boto3.client("s3")
# CONFIG (ajustado a 15 min)
PAGE_SIZE = 40
PAGES_MAX = 70
SLEEP_BETWEEN_CALLS = 0.1
STOP_WHEN_REMAINING_MS = 60_000  # corta si quedan <60s

DAILY_STATE_KEY = "state/rawg_daily_last_date.txt"
OUTPUT_PREFIX = "rawg/daily/"

# HELPERS
def safe_json(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def open_json(url: str, timeout: int = 30) -> dict:
    """
    Lector genérico. Si falla, loggea y relanza.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        print("HTTPError code:", e.code)
        print("HTTPError url:", getattr(e, "url", "unknown"))
        raise


def get_game_detail(games_url: str, api_key: str, game_id: int) -> dict:
    url = f"{games_url}/{game_id}?key={api_key}"
    return open_json(url)


def build_games_url(api_url_env: str) -> str:
    """
    Acepta:
      - https://api.rawg.io/api
      - https://api.rawg.io/api/games
    Devuelve siempre el endpoint /games.
    """
    api_base = (api_url_env or "").strip().rstrip("/")
    if not api_base:
        raise ValueError("Falta API_URL en variables de entorno")

    if api_base.endswith("/games"):
        return api_base
    return f"{api_base}/games"


def read_s3_text(bucket: str, key: str):
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read().decode("utf-8").strip()
    except s3.exceptions.NoSuchKey:
        return None


def write_s3_text(bucket: str, key: str, text: str):
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=text.encode("utf-8"),
        ContentType="text/plain",
    )

# LAMBDA (DAILY)
def lambda_handler(event, context):
    bucket_name = os.environ.get("BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Falta BUCKET_NAME en variables de entorno")

    games_url = build_games_url(os.environ.get("API_URL"))

    # API KEYS (strip + SOLO 1 para depurar)
    api_keys = [
        os.environ.get("API_KEY_1", ""),
        os.environ.get("API_KEY_2", ""),
        os.environ.get("API_KEY_3", ""),
        os.environ.get("API_KEY_4", ""),
        os.environ.get("API_KEY_5", ""),
    ]
    api_keys = [k.strip() for k in api_keys if k and k.strip()]
    if not api_keys:
        raise ValueError("No hay API keys configuradas (vacías o con espacios)")

    api_key = api_keys[0]  # para depurar (luego puedes volver a rotación)

    # TEST rápido (valida endpoint + key)-
    test_url = f"{games_url}?key={api_key}&page_size=1"
    print("API_URL env:", os.environ.get("API_URL"))
    print("games_url:", games_url)
    print("Testing URL:", test_url.replace(api_key, "KEY_HIDDEN"))
    _ = open_json(test_url)
    print("✅ RAWG key + endpoint OK")

    # RANGO UPDATED (desde última ejecución)

    today = datetime.utcnow().date()
    today_str = today.strftime("%Y-%m-%d")

    last_date_str = read_s3_text(bucket_name, DAILY_STATE_KEY)
    if last_date_str:
        try:
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
        except ValueError:
            last_date = today - timedelta(days=1)
    else:
        last_date = today - timedelta(days=1)

    updated_range = f"{last_date},{today}"

    all_rows = []
    pages_processed = 0


    # EXTRACCIÓN (solo updated)
    for page in range(1, PAGES_MAX + 1):
        if context and context.get_remaining_time_in_millis() < STOP_WHEN_REMAINING_MS:
            print("⏳ Cortando por tiempo restante")
            break

        url = (
            f"{games_url}"
            f"?key={api_key}"
            f"&page={page}"
            f"&page_size={PAGE_SIZE}"
            f"&updated={updated_range}"
        )

        print("LIST URL:", url.replace(api_key, "KEY_HIDDEN"))

        #  CAMBIO CLAVE: si RAWG devuelve 404 al pasar de la última página,
        # lo tratamos como "no hay más resultados" y cortamos el bucle.
        try:
            data = open_json(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print("ℹ️ 404 en paginación: no hay más páginas para este updated_range. Fin.")
                break
            raise  # otros errores por si fallan

        games = data.get("results", [])
        if not games:
            break

        pages_processed += 1

        for game in games:
            if context and context.get_remaining_time_in_millis() < STOP_WHEN_REMAINING_MS:
                print("⏳ Cortando por tiempo restante dentro de detalles")
                break

            detail = get_game_detail(games_url, api_key, game["id"])

            # Misma estructura que la lambda masiva
            row = {
                "id": detail.get("id"),
                "slug": detail.get("slug"),
                "name": detail.get("name"),
                "name_original": detail.get("name_original"),
                "description": detail.get("description_raw"),
                "metacritic": detail.get("metacritic"),
                "metacritic_platforms_json": safe_json(detail.get("metacritic_platforms")),
                "released": detail.get("released"),
                "tba": detail.get("tba"),
                "updated": detail.get("updated"),
                "background_image": detail.get("background_image"),
                "background_image_additional": detail.get("background_image_additional"),
                "website": detail.get("website"),
                "rating": detail.get("rating"),
                "rating_top": detail.get("rating_top"),
                "ratings_json": safe_json(detail.get("ratings")),
                "reactions_json": safe_json(detail.get("reactions")),
                "added": detail.get("added"),
                "added_by_status_json": safe_json(detail.get("added_by_status")),
                "playtime": detail.get("playtime"),
                "screenshots_count": detail.get("screenshots_count"),
                "movies_count": detail.get("movies_count"),
                "creators_count": detail.get("creators_count"),
                "achievements_count": detail.get("achievements_count"),
                "parent_achievements_count": detail.get("parent_achievements_count"),
                "reddit_url": detail.get("reddit_url"),
                "reddit_name": detail.get("reddit_name"),
                "reddit_description": detail.get("reddit_description"),
                "reddit_logo": detail.get("reddit_logo"),
                "reddit_count": detail.get("reddit_count"),
                "twitch_count": detail.get("twitch_count"),
                "youtube_count": detail.get("youtube_count"),
                "reviews_text_count": detail.get("reviews_text_count"),
                "ratings_count": detail.get("ratings_count"),
                "suggestions_count": detail.get("suggestions_count"),
                "alternative_names_json": safe_json(detail.get("alternative_names")),
                "metacritic_url": detail.get("metacritic_url"),
                "parents_count": detail.get("parents_count"),
                "additions_count": detail.get("additions_count"),
                "game_series_count": detail.get("game_series_count"),
                "esrb_rating_json": safe_json(detail.get("esrb_rating")),
                "platforms_json": safe_json(detail.get("platforms")),
            }

            all_rows.append(row)
            time.sleep(SLEEP_BETWEEN_CALLS)
    # ACTUALIZAR ESTADO (siempre)
    write_s3_text(bucket_name, DAILY_STATE_KEY, today_str)

    if not all_rows:
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "No hay juegos actualizados en el rango (o se acabaron páginas)",
                "updated_range": updated_range,
                "pages_processed": pages_processed,
                "rows_written": 0
            })
        }
    # GUARDAR EN S3
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    object_key = f"{OUTPUT_PREFIX}rawg_daily_updated_{today_str}_{timestamp}.json"

    payload = {
        "mode": "daily",
        "updated_range": updated_range,
        "pages_processed": pages_processed,
        "rows_written": len(all_rows),
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "data": all_rows,
    }

    s3.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
        Metadata={
            "producer": "lambda-rawg-daily",
            "mode": "daily",
            "updated_range": updated_range,
        },
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "updated_range": updated_range,
            "pages_processed": pages_processed,
            "rows_written": len(all_rows),
            "s3_key": object_key
        })
    }
