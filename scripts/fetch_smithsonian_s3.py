"""Bulk-fetch Smithsonian metadata from the public S3 bucket.

S3 layout: s3://smithsonian-open-access/metadata/edan/{unit_code}/{NN}.txt
Each .txt is newline-delimited JSON (ndjson), one record per line.
Records carry `online_media.media[].content` image URLs when media exists.

Strategy:
    1. Download unit metadata files (default: FSG + CHNDM).
    2. Stream-parse ndjson.
    3. Filter by place=China + has Images media.
    4. Download each image, compute SHA256, insert into patterns table.

No API key required (anonymous S3 GET).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Iterator

from PIL import Image

from pattern_dataset.db import DB_PATH, get_conn, insert_pattern, insert_source
from pattern_dataset.http_client import HttpClient, RateLimiter

S3_BASE = "https://smithsonian-open-access.s3.amazonaws.com"
METADATA_PREFIX = "metadata/edan"

DATASET_ROOT = Path("D:/desktop/pattern-dataset")
RAW_DIR = DATASET_ROOT / "data/raw/smithsonian"
PATTERNS_DIR = DATASET_ROOT / "data/patterns/smithsonian"

# Smithsonian unit codes worth harvesting for Chinese-pattern research.
# FSG = Freer + Sackler (Asian art) — primary
# CHNDM = Cooper Hewitt (design/decorative arts)
# NMAH = National Museum of American History (has Chinese ceramics samples)
# SIL = Smithsonian Libraries (book scans — broader, skip by default)
DEFAULT_UNITS = ["fsg", "chndm", "nmah"]


def list_unit_files(unit: str, client: HttpClient) -> list[str]:
    """List .txt files under metadata/edan/{unit}/."""
    import re

    keys: list[str] = []
    marker = ""
    while True:
        url = f"{S3_BASE}/?prefix={METADATA_PREFIX}/{unit}/&max-keys=1000"
        if marker:
            url += f"&marker={marker}"
        r = client._request("GET", url)
        text = r.text
        keys_in_page = re.findall(r"<Key>([^<]+)</Key>", text)
        next_marker_match = re.search(r"<NextMarker>([^<]+)</NextMarker>", text)
        truncated = "<IsTruncated>true</IsTruncated>" in text
        keys.extend(k for k in keys_in_page if k.endswith(".txt"))
        if not truncated or not next_marker_match:
            break
        marker = next_marker_match.group(1)
    return keys


def download_text_file(key: str, client: HttpClient, dest: Path) -> Path:
    """Download a metadata .txt to dest. Returns dest path."""
    url = f"{S3_BASE}/{key}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    client.download(url, dest)
    return dest


def iter_records(txt_path: Path) -> Iterator[dict]:
    """Stream ndjson records from a metadata file."""
    with txt_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def extract_place_names(rec: dict) -> list[str]:
    places = rec.get("content", {}).get("indexedStructured", {}).get("place", []) or []
    out: list[str] = []
    for p in places:
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, dict):
            label = p.get("content") or p.get("label")
            if label:
                out.append(label)
    return out


def extract_topics(rec: dict) -> list[str]:
    topics = rec.get("content", {}).get("indexedStructured", {}).get("topic", []) or []
    out: list[str] = []
    for t in topics:
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, dict):
            label = t.get("content") or t.get("label")
            if label:
                out.append(label)
    return out


def extract_dates(rec: dict) -> str:
    dates = rec.get("content", {}).get("indexedStructured", {}).get("date", []) or []
    for d in dates:
        if isinstance(d, str):
            return d
        if isinstance(d, dict):
            c = d.get("content")
            if c:
                return c
    return ""


def extract_image_url(rec: dict) -> str | None:
    """Return first image URL (type=Images, usage=CC0). None if no image."""
    dnr = rec.get("content", {}).get("descriptiveNonRepeating", {}) or {}
    online_media = dnr.get("online_media")
    if not online_media:
        return None
    media_list = online_media.get("media") or []
    for m in media_list:
        if m.get("type") != "Images":
            continue
        url = m.get("content")
        if not url:
            continue
        # Prefer CC0, but accept any
        usage = m.get("usage") or {}
        if isinstance(usage, dict) and usage.get("access") == "CC0":
            return url
    # Fallback: any image url
    for m in media_list:
        if m.get("type") == "Images" and m.get("content"):
            return m["content"]
    return None


def is_china(place_names: list[str]) -> bool:
    return any("china" in (p or "").lower() for p in place_names)


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
    parser.add_argument(
        "--units", nargs="+", default=DEFAULT_UNITS, help="Unit codes to fetch"
    )
    parser.add_argument(
        "--max-per-unit", type=int, default=0, help="Max images per unit (0=unlimited)"
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--download-images",
        action="store_true",
        help="If set, also download + ingest images (default: metadata-only)",
    )
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    PATTERNS_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    client = HttpClient(rate_limiter=RateLimiter(calls=5.0))

    try:
        for unit in args.units:
            print(f"\n[unit] {unit}")
            unit_files = list_unit_files(unit, client)
            print(f"  metadata files: {len(unit_files)}")

            source_id = f"smithsonian-{unit}"
            unit_image_count = 0
            unit_metadata_records = 0
            unit_china_records = 0

            for file_key in unit_files:
                file_name = file_key.split("/")[-1]
                dest_txt = RAW_DIR / unit / file_name
                if args.resume and dest_txt.exists() and dest_txt.stat().st_size > 0:
                    if args.verbose:
                        print(f"  [skip-dl] {file_name} (already exists)")
                else:
                    try:
                        download_text_file(file_key, client, dest_txt)
                    except Exception as e:
                        print(f"  [err] dl {file_key}: {e}")
                        continue

                for rec in iter_records(dest_txt):
                    unit_metadata_records += 1
                    places = extract_place_names(rec)
                    img_url = extract_image_url(rec)
                    if not img_url:
                        continue
                    if not is_china(places):
                        continue
                    unit_china_records += 1

                    if args.download_images:
                        if args.max_per_unit and unit_image_count >= args.max_per_unit:
                            break

                        # Determine dest filename
                        object_id = rec.get("id") or rec.get("hash") or f"{unit}-{unit_metadata_records}"
                        ext = ".jpg"
                        dest_img = PATTERNS_DIR / f"si-{unit}-{object_id}{ext}"
                        if dest_img.exists() and args.resume:
                            continue

                        try:
                            n = client.download(img_url, dest_img)
                        except Exception as e:
                            if args.verbose:
                                print(f"    [err] img {img_url}: {e}")
                            continue

                        sha = compute_sha256(dest_img)
                        try:
                            with Image.open(dest_img) as img:
                                size = img.size
                        except Exception:
                            size = None

                        with get_conn(args.db_path) as conn:
                            if args.resume and already_have_sha256(conn, sha):
                                dest_img.unlink(missing_ok=True)
                                continue
                            insert_pattern(
                                conn,
                                {
                                    "pattern_id": f"si-{unit}-{object_id}",
                                    "source_id": source_id,
                                    "source_ref": object_id,
                                    "file_path": str(
                                        dest_img.relative_to(DATASET_ROOT)
                                    ).replace("\\", "/"),
                                    "file_format": "jpg",
                                    "width_px": size[0] if size else None,
                                    "height_px": size[1] if size else None,
                                    "sha256": sha,
                                    "title": rec.get("title"),
                                    "dynasty": extract_dates(rec) or None,
                                    "tags": extract_topics(rec) or None,
                                    "review_status": "pending",
                                    "notes": json.dumps(
                                        {"places": places, "url": img_url},
                                        ensure_ascii=False,
                                    ),
                                },
                            )
                        unit_image_count += 1
                        if unit_image_count % 10 == 0:
                            print(
                                f"    [progress] {unit}: {unit_image_count} images ingested"
                            )

                if args.max_per_unit and unit_image_count >= args.max_per_unit:
                    break

            print(
                f"  summary: metadata={unit_metadata_records} china_with_img={unit_china_records} downloaded={unit_image_count}"
            )

            # Log a source row for this unit (even if metadata-only)
            with get_conn(args.db_path) as conn:
                insert_source(
                    conn,
                    {
                        "source_id": source_id,
                        "source_type": "api",
                        "license": "CC0",
                        "license_url": "https://www.si.edu/termsofuse",
                        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "api_response": {
                            "bucket": "smithsonian-open-access",
                            "unit_code": unit,
                            "metadata_records": unit_metadata_records,
                            "china_with_image": unit_china_records,
                            "downloaded_images": unit_image_count,
                        },
                        "notes": f"Smithsonian Open Access bulk metadata via S3. Unit={unit}.",
                    },
                )
    finally:
        client.close()


if __name__ == "__main__":
    main()
