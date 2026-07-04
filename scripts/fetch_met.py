"""Fetch Chinese artifacts from Met Museum Open Access API.

API docs: https://metmuseum.github.io/
No API key required. CC0 images.

Usage:
    python scripts/fetch_met.py --dry-run --verbose       # count
    python scripts/fetch_met.py --max 200                  # download 200 images
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
from typing import Iterator

from PIL import Image

from pattern_dataset.db import DB_PATH, get_conn, insert_pattern, insert_source
from pattern_dataset.http_client import HttpClient, RateLimiter

API_BASE = "https://collectionapi.met.museum.org/public/collection/v1"
DATASET_ROOT = Path("D:/desktop/pattern-dataset")
PATTERNS_DIR = DATASET_ROOT / "data/patterns/met"

# Met Asian Art department ID
ASIAN_ART_DEPT_ID = 6


def search_objects(
    client: HttpClient, query: str, has_images: bool = True, department_id: int | None = None
) -> dict:
    """Search Met collection. Returns {total, objectIDs: [...]}."""
    params = {"q": query, "hasImages": "true" if has_images else "false"}
    if department_id:
        params["departmentId"] = str(department_id)
    return client.get_json(f"{API_BASE}/search", params=params)


def get_object(client: HttpClient, object_id: int) -> dict:
    """Fetch a single object's metadata."""
    return client.get_json(f"{API_BASE}/objects/{object_id}")


def filter_china(obj: dict) -> bool:
    """Heuristic: object is Chinese."""
    country = (obj.get("country") or "").lower()
    culture = (obj.get("culture") or "").lower()
    dynasty = (obj.get("dynasty") or "").lower()
    return any("china" in x or "chinese" in x for x in (country, culture, dynasty))


def extract_pattern_type(obj: dict) -> str | None:
    """Map Met classification/title keywords to our taxonomy."""
    text = " ".join(
        filter(
            None,
            [
                obj.get("classification") or "",
                obj.get("title") or "",
                obj.get("medium") or "",
            ],
        )
    ).lower()
    rules = [
        ("porcelain", "青花瓷"),
        ("ceramic", "陶瓷"),
        ("silk", "织物"),
        ("embroider", "织物"),
        ("tapestry", "织物"),
        ("lacquer", "漆器"),
        ("bronze", "青铜"),
        ("jade", "玉器"),
        ("painting", "绘画"),
        ("scroll", "绘画"),
        ("calligrap", "书法"),
    ]
    for kw, label in rules:
        if kw in text:
            return label
    return None


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def already_have_sha256(conn: sqlite3.Connection, sha: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM patterns WHERE sha256 = ? LIMIT 1", (sha,)
    ).fetchone() is not None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="china", help="search query (default: china)")
    parser.add_argument("--max", type=int, default=0, help="max images to download (0=all)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-dept-filter", action="store_true", help="don't restrict to Asian Art dept")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    PATTERNS_DIR.mkdir(parents=True, exist_ok=True)
    client = HttpClient(rate_limiter=RateLimiter(calls=4.0))

    try:
        # 1. Search
        dept = None if args.no_dept_filter else ASIAN_ART_DEPT_ID
        result = search_objects(client, args.query, has_images=True, department_id=dept)
        total = result.get("total", 0)
        object_ids = result.get("objectIDs") or []
        print(f"[search] q={args.query!r} dept={'AsianArt' if dept else 'all'} total={total}")

        if args.dry_run:
            print(f"[dry-run] would fetch metadata for {len(object_ids)} objects")

        # 2. Insert source row
        with get_conn(args.db_path) as conn:
            insert_source(
                conn,
                {
                    "source_id": "met-asian-art",
                    "source_type": "api",
                    "license": "CC0",
                    "license_url": "https://www.metmuseum.org/information/terms-and-conditions",
                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "api_response": {
                        "endpoint": f"{API_BASE}/search",
                        "query": args.query,
                        "departmentId": dept,
                        "total_hits": total,
                    },
                    "notes": "Metropolitan Museum Open Access API. CC0.",
                },
            )

        fetched = 0
        skipped = 0
        failed = 0

        # 3. Iterate objects
        for i, oid in enumerate(object_ids):
            try:
                obj = get_object(client, oid)
            except Exception as e:
                if args.verbose:
                    print(f"  [err] obj {oid}: {e}")
                failed += 1
                continue

            if not filter_china(obj):
                skipped += 1
                continue

            image_url = obj.get("primaryImage") or obj.get("primaryImageSmall")
            if not image_url:
                skipped += 1
                continue

            if args.dry_run:
                fetched += 1
                if fetched % 50 == 0:
                    print(f"  [dry-run] china+image candidates so far: {fetched}")
                if args.max and fetched >= args.max:
                    break
                continue

            # Download
            ext_match = re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", image_url, re.I)
            ext = ext_match.group(1).lower() if ext_match else "jpg"
            dest = PATTERNS_DIR / f"met-{oid}.{ext}"
            if args.resume and dest.exists():
                skipped += 1
                continue

            try:
                client.download(image_url, dest)
            except Exception as e:
                if args.verbose:
                    print(f"  [err] dl {oid}: {e}")
                failed += 1
                continue

            sha = compute_sha256(dest)
            try:
                with Image.open(dest) as img:
                    size = img.size
            except Exception:
                size = None

            tags = []
            for k in ("classification", "culture", "dynasty", "period", "medium"):
                v = obj.get(k)
                if v:
                    tags.append(f"{k}:{v}")

            with get_conn(args.db_path) as conn:
                if args.resume and already_have_sha256(conn, sha):
                    dest.unlink(missing_ok=True)
                    skipped += 1
                    continue
                insert_pattern(
                    conn,
                    {
                        "pattern_id": f"met-{oid}",
                        "source_id": "met-asian-art",
                        "source_ref": str(oid),
                        "file_path": str(dest.relative_to(DATASET_ROOT)).replace("\\", "/"),
                        "file_format": ext,
                        "width_px": size[0] if size else None,
                        "height_px": size[1] if size else None,
                        "sha256": sha,
                        "title": obj.get("title"),
                        "dynasty": obj.get("dynasty") or obj.get("period"),
                        "pattern_type": extract_pattern_type(obj),
                        "tags": tags,
                        "review_status": "pending",
                        "notes": json.dumps(
                            {
                                "url": image_url,
                                "country": obj.get("country"),
                                "medium": obj.get("medium"),
                            },
                            ensure_ascii=False,
                        ),
                    },
                )
            fetched += 1
            if fetched % 25 == 0:
                print(f"  [progress] fetched={fetched} skipped={skipped} failed={failed}")

            if args.max and fetched >= args.max:
                break

        print(f"\n[summary] fetched={fetched} skipped={skipped} failed={failed}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
