"""SQLite connection and CRUD helpers."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"
DB_PATH = Path(__file__).resolve().parents[2] / "db" / "patterns.db"


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    """Create all tables from schema.sql. Idempotent."""
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def insert_source(conn: sqlite3.Connection, src: dict) -> None:
    api_response = src.get("api_response")
    params = {
        "source_id": src.get("source_id"),
        "source_type": src.get("source_type"),
        "license": src.get("license"),
        "license_url": src.get("license_url"),
        "fetched_at": src.get("fetched_at"),
        "api_response": (
            json.dumps(api_response, ensure_ascii=False) if api_response else None
        ),
        "notes": src.get("notes"),
    }
    conn.execute(
        """
        INSERT OR IGNORE INTO sources
        (source_id, source_type, license, license_url, fetched_at, api_response, notes)
        VALUES (:source_id, :source_type, :license, :license_url, :fetched_at, :api_response, :notes)
        """,
        params,
    )


def insert_pattern(conn: sqlite3.Connection, p: dict) -> None:
    main_colors = p.get("main_colors")
    tags = p.get("tags")
    params = {
        "pattern_id": p.get("pattern_id"),
        "source_id": p.get("source_id"),
        "source_ref": p.get("source_ref"),
        "file_path": p.get("file_path"),
        "file_format": p.get("file_format"),
        "width_px": p.get("width_px"),
        "height_px": p.get("height_px"),
        "sha256": p.get("sha256"),
        "title": p.get("title"),
        "dynasty": p.get("dynasty"),
        "pattern_type": p.get("pattern_type"),
        "pattern_subtype": p.get("pattern_subtype"),
        "main_colors": (
            json.dumps(main_colors, ensure_ascii=False) if main_colors else None
        ),
        "complexity": p.get("complexity"),
        "caption": p.get("caption"),
        "caption_short": p.get("caption_short"),
        "tags": json.dumps(tags, ensure_ascii=False) if tags else None,
        "review_status": p.get("review_status", "pending"),
    }
    conn.execute(
        """
        INSERT OR IGNORE INTO patterns
        (pattern_id, source_id, source_ref, file_path, file_format,
         width_px, height_px, sha256, title, dynasty, pattern_type,
         pattern_subtype, main_colors, complexity, caption, caption_short,
         tags, review_status)
        VALUES (:pattern_id, :source_id, :source_ref, :file_path, :file_format,
                :width_px, :height_px, :sha256, :title, :dynasty, :pattern_type,
                :pattern_subtype, :main_colors, :complexity, :caption, :caption_short,
                :tags, :review_status)
        """,
        params,
    )


def insert_element(conn: sqlite3.Connection, e: dict) -> None:
    bbox = e.get("bbox")
    params = {
        "element_id": e.get("element_id"),
        "pattern_id": e.get("pattern_id"),
        "file_path": e.get("file_path"),
        "bbox": json.dumps(bbox) if bbox else None,
        "extractor": e.get("extractor"),
        "approved": e.get("approved", 0),
        "element_type": e.get("element_type"),
    }
    conn.execute(
        """
        INSERT OR IGNORE INTO elements
        (element_id, pattern_id, file_path, bbox, extractor, approved, element_type)
        VALUES (:element_id, :pattern_id, :file_path, :bbox, :extractor, :approved, :element_type)
        """,
        params,
    )
