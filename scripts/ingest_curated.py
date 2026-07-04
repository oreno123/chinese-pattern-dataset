"""Ingest manually-collected artifact images into the dataset.

Workflow:
    1. You download images from anywhere (browser, museum site, Pinterest, etc.)
    2. Drop them into a watch folder (default: D:/desktop/文物图/)
    3. Run this script: it copies them to data/patterns/curated/, computes
       SHA256 + dimensions, inserts into patterns table (review_status='pending')
    4. (Later) run vision_annotate.py to auto-tag pattern_type/dynasty/title

Usage:
    python scripts/ingest_curated.py                              # default folder
    python scripts/ingest_curated.py --watch D:/some/other/dir
    python scripts/ingest_curated.py --resume                     # skip already-ingested SHA
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
from pathlib import Path

from PIL import Image

from pattern_dataset.db import DB_PATH, get_conn, insert_pattern, insert_source

DATASET_ROOT = Path("D:/desktop/pattern-dataset")
DEFAULT_WATCH = Path("D:/desktop/文物图")
DEST_DIR = DATASET_ROOT / "data/patterns/curated"
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


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
    parser.add_argument("--watch", type=Path, default=DEFAULT_WATCH, help="folder to scan")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--resume", action="store_true", help="skip files already ingested (by SHA)")
    parser.add_argument("--move", action="store_true", help="move instead of copy (default: copy)")
    args = parser.parse_args()

    if not args.watch.exists():
        sys_exit_with_msg(f"watch folder not found: {args.watch}")
    if not args.watch.is_dir():
        sys_exit_with_msg(f"watch path is not a directory: {args.watch}")

    DEST_DIR.mkdir(parents=True, exist_ok=True)

    files = [
        p
        for p in sorted(args.watch.rglob("*"))
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    ]
    print(f"[scan] {args.watch}: {len(files)} image files")

    if not files:
        print("[info] nothing to ingest")
        return

    ingested = 0
    skipped_dup = 0
    skipped_err = 0

    with get_conn(args.db_path) as conn:
        insert_source(
            conn,
            {
                "source_id": "curated-manual",
                "source_type": "manual",
                "license": "unknown",
                "license_url": None,
                "fetched_at": "2026-07-04T00:00:00Z",
                "api_response": {"watch_folder": str(args.watch)},
                "notes": "Manually curated artifact images. License per-image — verify before commercial use.",
            },
        )

        for src in files:
            try:
                sha = compute_sha256(src)
            except Exception as e:
                print(f"  [err] sha {src.name}: {e}")
                skipped_err += 1
                continue

            if args.resume and already_have_sha256(conn, sha):
                skipped_dup += 1
                continue

            # New short ID = first 12 hex chars of sha
            short = sha[:12]
            ext = src.suffix.lower()
            new_name = f"curated-{short}{ext}"
            dest = DEST_DIR / new_name

            if dest.exists():
                skipped_dup += 1
                continue

            try:
                if args.move:
                    shutil.move(str(src), str(dest))
                else:
                    shutil.copy2(src, dest)
            except Exception as e:
                print(f"  [err] copy {src.name}: {e}")
                skipped_err += 1
                continue

            try:
                with Image.open(dest) as img:
                    size = img.size
            except Exception:
                size = None

            insert_pattern(
                conn,
                {
                    "pattern_id": f"curated-{short}",
                    "source_id": "curated-manual",
                    "source_ref": src.name,
                    "file_path": str(dest.relative_to(DATASET_ROOT)).replace("\\", "/"),
                    "file_format": ext.lstrip("."),
                    "width_px": size[0] if size else None,
                    "height_px": size[1] if size else None,
                    "sha256": sha,
                    "title": src.stem,  # filename as placeholder title
                    "review_status": "pending",
                    "notes": "Original filename: " + src.name,
                },
            )
            ingested += 1
            print(f"  [ok] {src.name} -> {new_name} ({size[0]}x{size[1] if size else '?'})")

    print(
        f"\n[summary] ingested={ingested} skipped_dup={skipped_dup} skipped_err={skipped_err}"
    )


def sys_exit_with_msg(msg: str) -> None:
    import sys

    print(f"[error] {msg}")
    sys.exit(1)


if __name__ == "__main__":
    main()
