"""Migrate patterns and elements from the wenmai project into SQLite.

Sources:
  - wenmai-qinghua: 335 qinghua patterns from src/data/qinghuaPatterns.ts
  - wenmai-basics:  21 standalone patterns from public/patterns/*.webp
  - wenmai-shanjing: 25 shanjing patterns from public/patterns/shanjing/*.webp
  - wenmai-elements: 60 extracted motifs from public/elements/manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
from pathlib import Path

from PIL import Image

from pattern_dataset.db import (
    DB_PATH,
    get_conn,
    insert_element,
    insert_pattern,
    insert_source,
)

WENMAI_ROOT = Path("D:/desktop/纹脉/wenmai")
DATASET_ROOT = Path("D:/desktop/pattern-dataset")

QINGHUA_TS = WENMAI_ROOT / "src/data/qinghuaPatterns.ts"
QINGHUA_IMG_DIR = WENMAI_ROOT / "public/patterns/qinghua"
BASICS_IMG_DIR = WENMAI_ROOT / "public/patterns"
SHANJING_IMG_DIR = WENMAI_ROOT / "public/patterns/shanjing"
ELEMENTS_DIR = WENMAI_ROOT / "public/elements"
MANIFEST_JSON = ELEMENTS_DIR / "manifest.json"
APPROVED_JSON = ELEMENTS_DIR / "approved.json"

# basics filename -> pattern_type mapping
BASICS_TYPE_MAP = {
    "baoxiang": "宝相花",
    "lianhua": "宝相花",
    "huiwen": "回纹",
    "wanzi_endless": "回纹",
    "juancao": "卷草纹",
    "juancao-fixed": "卷草纹",
    "yunlei": "云雷纹",
    "duoyun": "云纹",
    "xiangyun": "云纹",
    "liuyun": "云纹",
    "ruyi_cloud": "云纹",
    "tuanlong": "团龙",
    "panlong": "龙纹",
    "shenglong": "龙纹",
    "xinglong": "龙纹",
    "kuilong_taotie": "饕餮纹",
    "taotie_shang": "饕餮纹",
    "taotie_zhou": "饕餮纹",
    "binglie": "几何纹",
    "ruyi_corner": "几何纹",
    "fengniao_corner": "凤纹",
}


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _pad_int(raw_id: str, width: int = 3) -> str:
    """'qh-1' -> 'qh-001', 'qh-42' -> 'qh-042'."""
    m = re.match(r"^(.*?)(\d+)$", raw_id)
    if not m:
        return raw_id
    return f"{m.group(1)}{int(m.group(2)):0{width}d}"


def parse_qinghua_ts(ts_path: Path) -> list[dict]:
    """Parse qinghuaPatterns.ts into a list of records.

    Each record is on its own line in the form:
      { id: "qh-1", name: "...", type: "...", series: ..., rarity: ..., tags: [...], image: "..." },

    We regex-extract each brace block and parse key-by-key to avoid JSON strictness
    issues with TypeScript `as SeriesId` casts.
    """
    text = ts_path.read_text(encoding="utf-8")
    pattern = re.compile(r"\{[^{}]*?\bid:\s*[^{}]*\}(?=\s*,|\s*\])")
    records: list[dict] = []
    for block in pattern.findall(text):
        rec = _parse_ts_block(block)
        if rec:
            records.append(rec)
    return records


_STRING_RE = re.compile(r'"([^"]*)"')
_ARRAY_RE = re.compile(r"\[([^\[\]]*)\]")


def _parse_ts_block(block: str) -> dict | None:
    """Extract fields from a single TS record block."""
    fields: dict = {}

    for key in ("id", "name", "type", "image"):
        m = re.search(rf'\b{key}:\s*"([^"]*)"', block)
        if m:
            fields[key] = m.group(1)

    raw_id = fields.get("id")
    if not raw_id or not raw_id.startswith("qh-"):
        return None

    tags_match = _ARRAY_RE.search(block)
    if tags_match:
        inner = tags_match.group(1)
        fields["tags"] = _STRING_RE.findall(inner)

    return fields


def _copy_image(src: Path, dest_dir: Path, new_stem: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{new_stem}{src.suffix.lower()}"
    shutil.copy2(src, dest)
    return dest


def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size


def _relative_to_dataset(path: Path) -> str:
    return str(path.relative_to(DATASET_ROOT)).replace("\\", "/")


def migrate_qinghua(db_path: Path) -> int:
    """Migrate 335 qinghua patterns."""
    records = parse_qinghua_ts(QINGHUA_TS)
    count = 0
    with get_conn(db_path) as conn:
        insert_source(
            conn,
            {
                "source_id": "wenmai-qinghua",
                "source_type": "manual",
                "license": "CC-BY-NC",
                "license_url": None,
                "fetched_at": "2026-07-04T00:00:00Z",
                "api_response": {
                    "ts_file": str(QINGHUA_TS),
                    "record_count": len(records),
                },
                "notes": "Migrated from wenmai qinghuaPatterns.ts (v5 Opus classification)",
            },
        )
        for src_rec in records:
            raw_id = src_rec.get("id")
            if not raw_id:
                continue
            n_match = re.search(r"\d+", raw_id)
            if not n_match:
                continue
            n = int(n_match.group())
            src_file = None
            for ext in (".webp", ".png"):
                cand = QINGHUA_IMG_DIR / f"qh-{n}{ext}"
                if cand.exists():
                    src_file = cand
                    break
            if not src_file:
                continue
            new_stem = f"qh-{n:03d}"
            dest = _copy_image(src_file, DATASET_ROOT / "data/patterns/qinghua", new_stem)
            sha = compute_sha256(dest)
            w, h = _image_size(dest)
            tags = list(src_rec.get("tags") or [])
            if src_rec.get("type") and src_rec["type"] not in tags:
                tags.insert(0, src_rec["type"])
            insert_pattern(
                conn,
                {
                    "pattern_id": new_stem,
                    "source_id": "wenmai-qinghua",
                    "source_ref": raw_id,
                    "file_path": _relative_to_dataset(dest),
                    "file_format": dest.suffix.lstrip("."),
                    "width_px": w,
                    "height_px": h,
                    "sha256": sha,
                    "title": src_rec.get("name"),
                    "pattern_type": src_rec.get("name") if src_rec.get("name", "").endswith("纹") else None,
                    "tags": tags,
                    "review_status": "approved",
                },
            )
            count += 1
    return count


def migrate_basics(db_path: Path) -> int:
    """Migrate 21 basics patterns."""
    count = 0
    with get_conn(db_path) as conn:
        insert_source(
            conn,
            {
                "source_id": "wenmai-basics",
                "source_type": "manual",
                "license": "CC-BY-NC",
                "license_url": None,
                "fetched_at": "2026-07-04T00:00:00Z",
                "api_response": {"dir": str(BASICS_IMG_DIR)},
                "notes": "Standalone traditional pattern images from wenmai public/patterns/",
            },
        )
        for src_file in sorted(BASICS_IMG_DIR.glob("*.webp")):
            stem = src_file.stem
            new_stem = f"basics-{stem}"
            dest = _copy_image(src_file, DATASET_ROOT / "data/patterns/basics", new_stem)
            sha = compute_sha256(dest)
            w, h = _image_size(dest)
            pattern_type = BASICS_TYPE_MAP.get(stem, "other")
            insert_pattern(
                conn,
                {
                    "pattern_id": new_stem,
                    "source_id": "wenmai-basics",
                    "source_ref": stem,
                    "file_path": _relative_to_dataset(dest),
                    "file_format": "webp",
                    "width_px": w,
                    "height_px": h,
                    "sha256": sha,
                    "title": stem,
                    "pattern_type": pattern_type,
                    "tags": [pattern_type],
                    "review_status": "approved",
                },
            )
            count += 1
    return count


def migrate_shanjing(db_path: Path) -> int:
    """Migrate 25 shanjing patterns."""
    count = 0
    with get_conn(db_path) as conn:
        insert_source(
            conn,
            {
                "source_id": "wenmai-shanjing",
                "source_type": "manual",
                "license": "CC-BY-NC",
                "license_url": None,
                "fetched_at": "2026-07-04T00:00:00Z",
                "api_response": {"dir": str(SHANJING_IMG_DIR)},
                "notes": "Shanhaijing mythical creature patterns",
            },
        )
        for idx, src_file in enumerate(sorted(SHANJING_IMG_DIR.glob("*.webp")), start=1):
            new_stem = f"shanjing-{idx:03d}"
            dest = _copy_image(src_file, DATASET_ROOT / "data/patterns/shanjing", new_stem)
            sha = compute_sha256(dest)
            w, h = _image_size(dest)
            insert_pattern(
                conn,
                {
                    "pattern_id": new_stem,
                    "source_id": "wenmai-shanjing",
                    "source_ref": src_file.stem,
                    "file_path": _relative_to_dataset(dest),
                    "file_format": "webp",
                    "width_px": w,
                    "height_px": h,
                    "sha256": sha,
                    "title": src_file.stem,
                    "pattern_type": "山海经",
                    "tags": ["山海经", "瑞兽"],
                    "review_status": "approved",
                },
            )
            count += 1
    return count


# Map element source prefix -> parent pattern_id in this dataset
ELEMENT_TO_PATTERN = {
    "huiwen": "basics-huiwen",
    "juanco2": "basics-juancao",
    "tuanlong": "basics-tuanlong",
    "yunlei": "basics-yunlei",
    "shanjing": "shanjing-001",  # 25 elements belong to shanjing series; attach to first as placeholder
}


def migrate_elements(db_path: Path) -> int:
    """Migrate 60 elements from manifest.json.

    Elements are derived from parent patterns, so no separate source row is added;
    their provenance traces through elements.pattern_id -> patterns.source_id.
    """
    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    approved = json.loads(APPROVED_JSON.read_text(encoding="utf-8"))
    approved_set = set(approved) if isinstance(approved, list) else set()

    count = 0
    with get_conn(db_path) as conn:
        for source_name, items in manifest.get("bySource", {}).items():
            for entry in items:
                elem_id = entry["id"]
                file_name = entry.get("file") or f"{elem_id}.png"
                src_file = ELEMENTS_DIR / file_name
                if not src_file.exists():
                    continue
                parent_pattern_id = ELEMENT_TO_PATTERN.get(source_name)
                if not parent_pattern_id:
                    continue
                dest_dir = DATASET_ROOT / "data/elements"
                dest = _copy_image(src_file, dest_dir, elem_id)
                insert_element(
                    conn,
                    {
                        "element_id": elem_id,
                        "pattern_id": parent_pattern_id,
                        "file_path": _relative_to_dataset(dest),
                        "bbox": None,
                        "extractor": "dbscan-v1",
                        "approved": 1 if elem_id in approved_set else 0,
                        "element_type": "motif",
                    },
                )
                count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument(
        "--only",
        choices=["qinghua", "basics", "shanjing", "elements", "all"],
        default="all",
    )
    args = parser.parse_args()

    counts: dict[str, int] = {}
    if args.only in ("qinghua", "all"):
        counts["qinghua"] = migrate_qinghua(args.db_path)
    if args.only in ("basics", "all"):
        counts["basics"] = migrate_basics(args.db_path)
    if args.only in ("shanjing", "all"):
        counts["shanjing"] = migrate_shanjing(args.db_path)
    if args.only in ("elements", "all"):
        counts["elements"] = migrate_elements(args.db_path)
    print(f"[ok] migration complete: {counts}")


if __name__ == "__main__":
    main()
