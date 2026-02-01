"""Steam English Reviews Crawler (Top N by review count) + Raw + Stats

Muc tieu (Buoc 1 - Thu thap du lieu, truoc tien xu li):
- Lay TOP N game theo so luong danh gia (Steam Search sort_by=Reviews_DESC, CHI TRANG 1)
- Cao review TIENG ANH cho tung game qua endpoint appreviews (JSON)
- Luu:
  + raw JSON tung page (gzip)
  + dataset dang JSONL + CSV
  + thong ke per-game + batch

Gioi han:
- Top game chi duoc parse tu trang search dau tien cua Steam (khong phai ranking toan bo Steam)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import os
import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional

import requests

SEARCH_URL = "https://store.steampowered.com/search/"
APPREVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"
APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"


def vn_now_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).isoformat()


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


def fetch_search_html(timeout: int = 30) -> str:
    params = {
        "sort_by": "Reviews_DESC",
        "supportedlang": "english",
        "ndl": 1,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get(SEARCH_URL, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def parse_top_appids(html: str, top_n: int) -> List[int]:
    out: List[int] = []
    seen = set()
    for m in re.finditer(r'data-ds-appid="([0-9,]+)"', html):
        raw = m.group(1)
        first = raw.split(",", 1)[0]
        try:
            appid = int(first)
        except Exception:
            continue
        if appid in seen:
            continue
        seen.add(appid)
        out.append(appid)
        if len(out) >= top_n:
            break
    return out


def fetch_app_name(appid: int, timeout: int = 30) -> Optional[str]:
    params = {"appids": appid, "l": "english"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get(APPDETAILS_URL, params=params, headers=headers, timeout=timeout)
    if r.status_code != 200:
        return None
    try:
        obj = r.json()
        data = obj.get(str(appid), {}).get("data")
        if isinstance(data, dict):
            name = data.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    except Exception:
        return None
    return None


def fetch_reviews_page(
    appid: int,
    cursor: str,
    language: str,
    num_per_page: int,
    filter_: str,
    review_type: str,
    purchase_type: str,
    day_range: int,
    timeout: int = 30,
) -> Dict[str, Any]:
    params = {
        "json": 1,
        "cursor": cursor,
        "language": language,
        "num_per_page": num_per_page,
        "filter": filter_,
        "review_type": review_type,
        "purchase_type": purchase_type,
        "day_range": day_range,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    url = APPREVIEWS_URL.format(appid=appid)
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def ts_to_iso_utc(ts: Any) -> Optional[str]:
    try:
        if ts is None:
            return None
        return dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc).isoformat()
    except Exception:
        return None


def normalize_review(appid: int, review: Dict[str, Any]) -> Dict[str, Any]:
    rid = str(review.get("recommendationid") or "")
    author = review.get("author") or {}

    return {
        "source": "steam",
        "appid": appid,
        "review_id": rid,
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
        "author_playtime_at_review": author.get("playtime_at_review"),
        "author_last_played": ts_to_iso_utc(author.get("last_played")),
    }


def write_csv_from_jsonl(jsonl_path: str, csv_path: str) -> None:
    if not os.path.exists(jsonl_path):
        fieldnames = ["source", "appid", "review_id", "created_at", "voted_up", "review_text"]
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
        return

    rows: List[Dict[str, Any]] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        fieldnames = ["source", "appid", "review_id", "created_at", "voted_up", "review_text"]
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
        return

    fieldnames: List[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                fieldnames.append(k)

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def crawl_one_game_en(
    appid: int,
    game_dir: str,
    max_reviews: int,
    delay_s: float,
    num_per_page: int = 100,
    filter_: str = "all",
    review_type: str = "all",
    purchase_type: str = "all",
    day_range: int = 36500,
) -> Dict[str, Any]:
    os.makedirs(game_dir, exist_ok=True)
    raw_dir = os.path.join(game_dir, "raw")

    reviews_jsonl = os.path.join(game_dir, "reviews.jsonl")
    reviews_csv = os.path.join(game_dir, "reviews.csv")
    stats_json = os.path.join(game_dir, "stats.json")

    cursor = "*"
    seen_cursors = set()
    seen_review_ids = set()

    fetched = 0
    pages = 0
    voted_counter = Counter()

    while fetched < max_reviews:
        pages += 1

        max_retry = 3
        payload = None
        for attempt in range(max_retry):
            try:
                payload = fetch_reviews_page(
                    appid=appid,
                    cursor=cursor,
                    language="english",
                    num_per_page=min(num_per_page, max_reviews - fetched),
                    filter_=filter_,
                    review_type=review_type,
                    purchase_type=purchase_type,
                    day_range=day_range,
                )
                break
            except Exception:
                if attempt == max_retry - 1:
                    raise
                time.sleep(2 ** attempt)

        if not payload:
            break

        write_gz_json(os.path.join(raw_dir, f"page_{pages:04d}.json.gz"), payload)

        new_cursor = payload.get("cursor")
        if not new_cursor or new_cursor in seen_cursors:
            break
        seen_cursors.add(new_cursor)
        cursor = new_cursor

        reviews = payload.get("reviews") or []
        if not reviews:
            break

        for rv in reviews:
            rid = str(rv.get("recommendationid") or "")
            if not rid or rid in seen_review_ids:
                continue
            seen_review_ids.add(rid)

            norm = normalize_review(appid, rv)
            append_jsonl(reviews_jsonl, norm)
            fetched += 1

            if norm.get("voted_up") is True:
                voted_counter["positive"] += 1
            elif norm.get("voted_up") is False:
                voted_counter["negative"] += 1
            else:
                voted_counter["unknown"] += 1

            if fetched >= max_reviews:
                break

        if delay_s > 0:
            time.sleep(delay_s)

    write_csv_from_jsonl(reviews_jsonl, reviews_csv)

    stats = {
        "source": "steam",
        "appid": appid,
        "language": "english",
        "pages_fetched": pages,
        "reviews_fetched": fetched,
        "label_proxy_distribution": dict(voted_counter),
        "files": {
            "reviews_jsonl": "reviews.jsonl",
            "reviews_csv": "reviews.csv",
            "stats_json": "stats.json",
            "raw_dir": "raw/",
        },
    }

    with open(stats_json, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--max-reviews-per-game", type=int, default=500)
    ap.add_argument("--out", default="steam_raw")
    ap.add_argument("--delay", type=float, default=1.2)
    ap.add_argument("--delay-between-games", type=float, default=2.0)
    args = ap.parse_args(argv)

    session = now_ts()
    run_dir = os.path.join(args.out, f"batch_top_reviews_en_{session}")
    games_dir = os.path.join(run_dir, "games")
    os.makedirs(games_dir, exist_ok=True)

    html = fetch_search_html()
    appids = parse_top_appids(html, top_n=args.top)

    with open(os.path.join(run_dir, "appids.json"), "w", encoding="utf-8") as f:
        json.dump(appids, f, ensure_ascii=False, indent=2)

    batch_stats: Dict[str, Any] = {
        "source": "steam",
        "type": "top_by_review_count",
        "language": "english",
        "top": args.top,
        "max_reviews_per_game": args.max_reviews_per_game,
        "started_at": vn_now_iso(),
        "notes": "Top games parsed from the first Steam search page only.",
        "games": [],
    }

    rating_total = Counter()
    total_reviews = 0

    for rank, appid in enumerate(appids, start=1):
        name = fetch_app_name(appid) or "unknown"
        slug = safe_slug(name)
        game_dir = os.path.join(games_dir, f"{rank:02d}_{appid}_{slug}")

        st = crawl_one_game_en(
            appid=appid,
            game_dir=game_dir,
            max_reviews=args.max_reviews_per_game,
            delay_s=args.delay,
        )

        batch_stats["games"].append({
            "rank": rank,
            "appid": appid,
            "name": name,
            "reviews_fetched": st.get("reviews_fetched"),
            "pages_fetched": st.get("pages_fetched"),
            "label_proxy_distribution": st.get("label_proxy_distribution"),
            "dir": os.path.relpath(game_dir, run_dir),
        })

        total_reviews += int(st.get("reviews_fetched") or 0)
        for k, v in (st.get("label_proxy_distribution") or {}).items():
            rating_total[k] += int(v)

        if args.delay_between_games > 0:
            time.sleep(args.delay_between_games)

    batch_stats["finished_at"] = vn_now_iso()
    batch_stats["total_reviews"] = total_reviews
    batch_stats["label_proxy_distribution_total"] = dict(rating_total)

    with open(os.path.join(run_dir, "batch_stats.json"), "w", encoding="utf-8") as f:
        json.dump(batch_stats, f, ensure_ascii=False, indent=2)

    print("DONE")
    print("Run dir:", run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
