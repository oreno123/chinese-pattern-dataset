"""Schema tests - verify tables/columns/indexes exist and constraints fire."""
from __future__ import annotations

import sqlite3

import pytest

from pattern_dataset.db import SCHEMA_PATH, init_db


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def conn(tmp_db):
    c = sqlite3.connect(tmp_db)
    c.execute("PRAGMA foreign_keys = ON;")
    yield c
    c.close()


def _seed_source(conn, source_id="s1"):
    conn.execute(
        "INSERT INTO sources (source_id, source_type, fetched_at) "
        "VALUES (?, 'manual', '2026-07-04T00:00:00Z')",
        (source_id,),
    )
    conn.commit()


def test_schema_file_exists():
    assert SCHEMA_PATH.exists(), f"schema.sql missing at {SCHEMA_PATH}"


def test_all_tables_created(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {"sources", "patterns", "elements", "tags", "annotations"} <= names


def test_review_status_check_constraint(conn):
    _seed_source(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO patterns (pattern_id, source_id, file_path, file_format,
                                  sha256, review_status)
            VALUES ('p1', 's1', 'p.png', 'png', 'abc', 'INVALID_STATUS')
            """
        )


def test_complexity_check_constraint(conn):
    _seed_source(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO patterns (pattern_id, source_id, file_path, file_format,
                                  sha256, complexity)
            VALUES ('p1', 's1', 'p.png', 'png', 'abc', 99)
            """
        )


def test_complexity_null_allowed(conn):
    _seed_source(conn)
    conn.execute(
        """
        INSERT INTO patterns (pattern_id, source_id, file_path, file_format,
                              sha256, complexity)
        VALUES ('p1', 's1', 'p.png', 'png', 'abc', NULL)
        """
    )
    row = conn.execute(
        "SELECT complexity FROM patterns WHERE pattern_id = 'p1'"
    ).fetchone()
    assert row[0] is None


def test_foreign_key_cascade(conn):
    """Deleting a source cascades to its patterns."""
    _seed_source(conn)
    conn.execute(
        """
        INSERT INTO patterns (pattern_id, source_id, file_path, file_format, sha256)
        VALUES ('p1', 's1', 'p.png', 'png', 'abc')
        """
    )
    conn.execute("DELETE FROM sources WHERE source_id = 's1'")
    row = conn.execute(
        "SELECT COUNT(*) FROM patterns WHERE pattern_id = 'p1'"
    ).fetchone()
    assert row[0] == 0


def test_sha256_unique(conn):
    """Duplicate sha256 should be rejected."""
    _seed_source(conn)
    conn.execute(
        """
        INSERT INTO patterns (pattern_id, source_id, file_path, file_format, sha256)
        VALUES ('p1', 's1', 'p.png', 'png', 'samehashographical')
        """
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO patterns (pattern_id, source_id, file_path, file_format, sha256)
            VALUES ('p2', 's1', 'p2.png', 'png', 'samehashographical')
            """
        )
