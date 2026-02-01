from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import os
import re
import time
from collections import Counter
from typing import Any, Dict, Optional
import requests
APPREVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"
APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
APP_MAP = {
    262060: {"name": "Darkest Dungeon", "is_dlc": False},
    580100: {"name": "Crimson Court", "is_dlc": True},
    702540: {"name": "Shieldbreaker", "is_dlc": True},
    735730: {"name": "Color of Madness", "is_dlc": True},
    345800: {"name": "Soundtrack", "is_dlc": True},
}



def now_ts() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_slug(s: str, max_len: int = 80) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s)
    return s.strip("_")[:max_len] or "steam"


def write_gz_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def ts_to_iso_utc(ts: Any) -> Optional[str]:
    try:
        if ts is None:
            return None
        return dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc).isoformat()
    except Exception:
        return None



def fetch_app_name(appid: int, timeout: int = 30) -> Optional[str]:
    r = requests.get(APPDETAILS_URL, params={"appids": appid}, timeout=timeout)
    try:
        return r.json().get(str(appid), {}).get("data", {}).get("name")
    except Exception:
        return None


def fetch_reviews_page(
    appid: int,
    cursor: str,
    num_per_page: int,
    timeout: int = 30,
) -> Dict[str, Any]:
    params = {
        "json": 1,
        "cursor": cursor,
        "language": "english",
        "num_per_page": num_per_page,
        "filter": "all",
        "review_type": "all",
        "purchase_type": "all",
        "day_range": 36500,
    }
    r = requests.get(APPREVIEWS_URL.format(appid=appid), params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()



def classify_player(playtime_min: Optional[int]) -> str:
    if playtime_min is None:
        return "unknown"
    if playtime_min < 10 * 60:
        return "casual"
    if playtime_min < 50 * 60:
        return "midcore"
    return "hardcore"


def normalize_review(appid: int, review: Dict[str, Any]) -> Dict[str, Any]:
    author = review.get("author") or {}
    meta = APP_MAP.get(appid, {})

    playtime_at_review = author.get("playtime_at_review")
    player_type = classify_player(playtime_at_review)

    return {
        "source": "steam",
        "appid": appid,
        "game_name": meta.get("name"),
        "is_dlc": meta.get("is_dlc", False),
        "player_type": player_type,

        "review_id": str(review.get("recommendationid") or ""),
        "steam_language": review.get("language"),
        "created_at": ts_to_iso_utc(review.get("timestamp_created")),
        "updated_at": ts_to_iso_utc(review.get("timestamp_updated")),
        "voted_up": review.get("voted_up"),
        "votes_up": review.get("votes_up"),
        "votes_funny": review.get("votes_funny"),
        "comment_count": review.get("comment_count"),
        "weighted_vote_score": review.get("weighted_vote_score"),
        "steam_purchase_type": review.get("purchase_type"),
        "received_for_free": review.get("received_for_free"),
        "written_during_early_access": review.get("written_during_early_access"),
        "steam_deck": review.get("steam_deck"),
        "review_text": review.get("review"),

        "author_steamid": author.get("steamid"),
        "author_num_games_owned": author.get("num_games_owned"),
        "author_num_reviews": author.get("num_reviews"),
        "author_playtime_forever": author.get("playtime_forever"),
        "author_playtime_last_two_weeks": author.get("playtime_last_two_weeks"),
        "author_playtime_at_review": playtime_at_review,
        "author_last_played": ts_to_iso_utc(author.get("last_played")),
    }


def write_csv_from_jsonl(jsonl_path: str, csv_path: str) -> None:
    rows = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    fieldnames = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                fieldnames.append(k)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)



def crawl_one_game_en(appid: int, game_dir: str, max_reviews: int, delay_s: float):
    os.makedirs(game_dir, exist_ok=True)
    raw_dir = os.path.join(game_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    reviews_jsonl = os.path.join(game_dir, "reviews.jsonl")
    reviews_csv = os.path.join(game_dir, "reviews.csv")

    cursor = "*"
    seen_cursors = set()
    seen_review_ids = set()
    fetched = 0
    pages = 0
    voted_counter = Counter()

    while fetched < max_reviews:
        pages += 1
        payload = fetch_reviews_page(appid, cursor, min(100, max_reviews - fetched))
        write_gz_json(os.path.join(raw_dir, f"page_{pages:04d}.json.gz"), payload)

        new_cursor = payload.get("cursor")
        if not new_cursor or new_cursor in seen_cursors:
            break
        seen_cursors.add(new_cursor)
        cursor = new_cursor

        for rv in payload.get("reviews", []):
            rid = str(rv.get("recommendationid") or "")
            if not rid or rid in seen_review_ids:
                continue
            seen_review_ids.add(rid)

            norm = normalize_review(appid, rv)
            append_jsonl(reviews_jsonl, norm)
            fetched += 1

            if norm["voted_up"] is True:
                voted_counter["positive"] += 1
            elif norm["voted_up"] is False:
                voted_counter["negative"] += 1

        time.sleep(delay_s)

    write_csv_from_jsonl(reviews_jsonl, reviews_csv)



def main():
    TARGET_APPIDS = list(APP_MAP.keys())
    OUT_DIR = "steam_darkest_dungeon_reviews"
    MAX_REVIEWS = 1_000_000
    DELAY = 1.2

    run_dir = os.path.join(OUT_DIR, now_ts())
    games_dir = os.path.join(run_dir, "games")
    os.makedirs(games_dir, exist_ok=True)

    for appid in TARGET_APPIDS:
        name = fetch_app_name(appid) or str(appid)
        game_dir = os.path.join(games_dir, f"{appid}_{safe_slug(name)}")
        crawl_one_game_en(appid, game_dir, MAX_REVIEWS, DELAY)

    print("DONE:", run_dir)


if __name__ == "__main__":
    main()
