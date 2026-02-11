import json
import os
import boto3
import urllib.request
from datetime import datetime, timedelta
import random
import time

s3 = boto3.client("s3")

# Configuracion
PAGES_PER_RUN = 10
PAGE_SIZE = 40              # máximo RAWG
STATE_KEY = "state/rawg_page.txt"
SLEEP_BETWEEN_CALLS = 0.1   # evita throttling

# Helpers
def get_game_detail(games_url, api_key, game_id):
    url = f"{games_url}/{game_id}?key={api_key}"
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())

def safe_json(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None

# Lambda 
def lambda_handler(event, context):
    api_base = os.environ["API_URL"].rstrip("/")
    if not api_base.endswith("/games"):
        games_url = f"{api_base}/games"
    else:
        games_url = api_base

    bucket_name = os.environ["BUCKET_NAME"]

    # MODO DE EJECUCIÓN
    mode = event.get("mode", "initial")
    is_daily = mode == "daily"

    # API KEYS (rotación)
    api_keys = [
        os.environ.get("API_KEY_1"),
        os.environ.get("API_KEY_2"),
        os.environ.get("API_KEY_3"),
        os.environ.get("API_KEY_4"),
        os.environ.get("API_KEY_5"),
    ]
    api_keys = [k for k in api_keys if k]
    if not api_keys:
        raise ValueError("No hay API keys configuradas")
    api_key = random.choice(api_keys)

    # Leer el Estado 
   
    if is_daily:
        current_page = 1
    else:
        try:
            obj = s3.get_object(Bucket=bucket_name, Key=STATE_KEY)
            current_page = int(obj["Body"].read().decode("utf-8"))
        except s3.exceptions.NoSuchKey:
            current_page = 1

    # Filtro
    updated_range = None
    if is_daily:
        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        updated_range = f"{yesterday},{today}"

    all_rows = []
    pages_processed = 0

    # Extracion 
    for i in range(PAGES_PER_RUN):
        page = current_page + i
        url = (
            f"{games_url}"
            f"?key={api_key}"
            f"&page={page}"
            f"&page_size={PAGE_SIZE}"
        )
        if updated_range:
            url += f"&updated={updated_range}"

        with urllib.request.urlopen(url) as response:
            games = json.loads(response.read()).get("results", [])

        if not games:
            break

        pages_processed += 1

        for game in games:
            detail = get_game_detail(games_url, api_key, game["id"])

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

    if not all_rows:
        return {"statusCode": 200, "body": "No hay más datos para extraer"}

    # GUARDAR JSON EN S3 
    end_page = current_page + pages_processed - 1
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    prefix = "daily" if is_daily else "full"

    file_name = f"rawg_{prefix}_pages_{current_page}_to_{end_page}_{timestamp}.json"
    object_key = f"rawg/data/{file_name}"

    payload = {
        "mode": mode,
        "start_page": current_page,
        "end_page": end_page,
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
            "producer": "lambda-rawg-extractor",
            "mode": mode,
            "pages": f"{current_page}-{end_page}",
        },
    )

    # ACTUALIZAR ESTADO (SOLO FULL)
    next_page = current_page + pages_processed
    if not is_daily:
        s3.put_object(
            Bucket=bucket_name,
            Key=STATE_KEY,
            Body=str(next_page),
            ContentType="text/plain",
        )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "mode": mode,
                "pages_processed": pages_processed,
                "rows_written": len(all_rows),
                "start_page": current_page,
                "end_page": end_page,
                "next_page": next_page,
                "s3_key": object_key,
            }
        ),
    }