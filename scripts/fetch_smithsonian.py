"""Fetch Chinese artifacts from Smithsonian Open Access API (FSG unit).

API docs: https://www.si.edu/openaccess/devtools
Endpoint: https://api.si.edu/openaccess/api/v1.0/content/{unit}/search

FSG = Freer Gallery of Art and Arthur M. Sackler Gallery (Asian art).
Filter: place=China (via indexedStructured.place.label = "China").
License: CC0 for records with online_media. Records without media have partial CC0
metadata but no image — we skip them.

Usage:
    export SI_API_KEY=...   # or pass --api-key
    python scripts/fetch_smithsonian.py --rows 100 --max 1000
    python scripts/fetch_smithsonian.py --resume            # skip patterns already in DB
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image

from pattern_dataset.db import DB_PATH, get_conn, insert_pattern, insert_source
from pattern_dataset.http_client import HttpClient, RateLimiter

API_BASE = "https://api.si.edu/openaccess/api/v1.0"
UNIT_CODE = "FSG"  # Freer + Sackler (Asian art)
DATASET_ROOT = Path("D:/desktop/pattern-dataset")
RAW_DIR = DATASET_ROOT / "data/raw/smithsonian"
PATTERNS_DIR = DATASET_ROOT / "data/patterns/smithsonian"

CHINA_PLACE_QUERIES = [
    'place:"China"',
    "China",
]


def search_url(unit: str = UNIT_CODE) -> str:
    return f"{API_BASE}/content/{unit}/search"


def normalize_record(rec: dict) -> dict | None:
    """Extract a flat dict from a Smithsonian record.

    Returns None if record has no downloadable image.
    """
    content = rec.get("content") or {}
    dnr = content.get("descriptiveNonRepeating") or {}
    idx = content.get("indexedStructured") or {}
    free = content.get("freetext") or {}

    # Object ID
    object_id = dnr.get("guid") or rec.get("id") or rec.get("unitCode")
    if not object_id:
        return None

    # Image URL (only CC0 records have online_media)
    online_media = dnr.get("online_media") or {}
    media_list = online_media.get("media") or []
    if not media_list:
        return None
    image_url = media_list[0].get("content")
    if not image_url:
        return None

    # Title
    title_obj = dnr.get("title") or {}
    title = (
        title_obj.get("content")
        if isinstance(title_obj, dict)
        else (title_obj if isinstance(title_obj, str) else None)
    )

    # Place (look for "China")
    places = idx.get("place") or []
    place_names: list[str] = []
    for p in places:
        if isinstance(p, dict):
            label = p.get("content") or p.get("label")
            if label:
                place_names.append(label)

    # Date
    dates = idx.get("date") or []
    date_label = ""
    for d in dates:
        if isinstance(d, dict):
            date_label = d.get("content") or date_label

    # Medium / physical description
    phys = free.get("physicalDescription") or []
    medium = ""
    for p in phys:
        if isinstance(p, dict):
            medium = p.get("content") or medium

    # Topic tags
    topics = idx.get("topic") or []
    topic_tags: list[str] = []
    for t in topics:
        if isinstance(t, dict):
            label = t.get("content") or t.get("label")
            if label:
                topic_tags.append(label)

    return {
        "object_id": str(object_id),
        "image_url": image_url,
        "title": title,
        "places": place_names,
        "date": date_label,
        "medium": medium,
        "topics": topic_tags,
        "raw_record": rec,
    }


def is_china(record: dict) -> bool:
    places = record.get("places") or []
    if not places:
        return False
    place_text = " ".join(places).lower()
    return "china" in place_text


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_search_page(
    client: HttpClient, api_key: str, query: str, start: int, rows: int
) -> dict:
    params = {
        "api_key": api_key,
        "q": query,
        "rows": rows,
        "start": start,
    }
    return client.get_json(search_url(), params=params)


def download_image(
    client: HttpClient, url: str, dest: Path
) -> tuple[int, str, tuple[int, int] | None]:
    """Download to dest. Returns (bytes, sha256, (width, height) or None)."""
    n = client.download(url, dest)
    sha = compute_sha256(dest)
    try:
        with Image.open(dest) as img:
            size = img.size
    except Exception:
        size = None
    return n, sha, size


def already_have_sha256(conn: sqlite3.Connection, sha: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM patterns WHERE sha256 = ? LIMIT 1", (sha,)
    ).fetchone()
    return row is not None


def insert_smithsonian_pattern(
    conn: sqlite3.Connection, record: dict, file_path: Path, sha: str, size: tuple[int, int] | None
) -> None:
    pattern_id = f"si-{record['object_id']}"
    insert_pattern(
        conn,
        {
            "pattern_id": pattern_id,
            "source_id": "smithsonian-fsg",
            "source_ref": record["object_id"],
            "file_path": str(file_path.relative_to(DATASET_ROOT)).replace("\\", "/"),
            "file_format": file_path.suffix.lstrip("."),
            "width_px": size[0] if size else None,
            "height_px": size[1] if size else None,
            "sha256": sha,
            "title": record.get("title"),
            "dynasty": record.get("date") or None,
            "tags": record.get("topics") or None,
            "review_status": "pending",
            "notes": json.dumps(
                {"places": record.get("places"), "medium": record.get("medium")},
                ensure_ascii=False,
            ),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=os.environ.get("SI_API_KEY"))
    parser.add_argument("--rows", type=int, default=100, help="rows per page")
    parser.add_argument("--max", type=int, default=0, help="max records to fetch (0=unlimited)")
    parser.add_argument("--resume", action="store_true", help="skip patterns already in DB")
    parser.add_argument(
        "--query",
        default='place:"China"',
        help='Smithsonian query string (default: place:"China")',
    )
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--dry-run", action="store_true", help="don't download, just count")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit(
            "ERROR: SI_API_KEY env var missing. Get one at https://api.data.gov/signup/"
        )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PATTERNS_DIR.mkdir(parents=True, exist_ok=True)

    client = HttpClient(rate_limiter=RateLimiter(calls=2.5))
    fetched = 0
    skipped = 0
    failed = 0
    start = 0
    seen_ids: set[str] = set()

    # One source row, written once per run
    with get_conn(args.db_path) as conn:
        insert_source(
            conn,
            {
                "source_id": "smithsonian-fsg",
                "source_type": "api",
                "license": "CC0",
                "license_url": "https://www.si.edu/termsofuse",
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "api_response": {
                    "unit": UNIT_CODE,
                    "query": args.query,
                    "endpoint": search_url(),
                },
                "notes": "Freer Gallery of Art and Arthur M. Sackler Gallery (Asian art). Filter: place=China.",
            },
        )

    try:
        while True:
            try:
                page = fetch_search_page(
                    client, args.api_key, args.query, start=start, rows=args.rows
                )
            except Exception as e:
                print(f"[err] page start={start}: {e}")
                failed += 1
                if failed > 5:
                    break
                start += args.rows
                continue

            rows = page.get("response", {}).get("rows") or page.get("rows") or []
            if not rows:
                print(f"[info] no more rows at start={start}")
                break

            total = page.get("response", {}).get("rowCount") or page.get("rowCount") or 0
            if args.verbose:
                print(f"[page] start={start} rows={len(rows)} total={total}")

            with get_conn(args.db_path) as conn:
                for rec in rows:
                    normalized = normalize_record(rec)
                    if not normalized:
                        skipped += 1
                        continue
                    if not is_china(normalized):
                        skipped += 1
                        continue
                    if normalized["object_id"] in seen_ids:
                        skipped += 1
                        continue
                    seen_ids.add(normalized["object_id"])

                    if args.dry_run:
                        fetched += 1
                        if fetched % 50 == 0:
                            print(f"[dry-run] would fetch {fetched}")
                        if args.max and fetched >= args.max:
                            break
                        continue

                    # Determine extension from URL
                    url = normalized["image_url"]
                    ext_match = re.search(r"\.(jpg|jpeg|png|tif|tiff|webp)(\?|$)", url, re.I)
                    ext = ext_match.group(1).lower() if ext_match else "jpg"

                    dest = PATTERNS_DIR / f"si-{normalized['object_id']}.{ext}"

                    if args.resume and dest.exists():
                        skipped += 1
                        continue

                    try:
                        _, sha, size = download_image(client, url, dest)
                    except Exception as e:
                        print(f"[err] download {url}: {e}")
                        failed += 1
                        continue

                    if args.resume and already_have_sha256(conn, sha):
                        # duplicate content; remove the new file
                        dest.unlink(missing_ok=True)
                        skipped += 1
                        continue

                    insert_smithsonian_pattern(conn, normalized, dest, sha, size)
                    fetched += 1

                    if fetched % 25 == 0:
                        print(f"[progress] fetched={fetched} skipped={skipped} failed={failed}")

                    if args.max and fetched >= args.max:
                        break

            if args.max and fetched >= args.max:
                break

            start += args.rows
            if total and start >= total:
                print(f"[done] reached end of results at start={start}")
                break

    finally:
        client.close()

    print(f"\n[summary] fetched={fetched} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
