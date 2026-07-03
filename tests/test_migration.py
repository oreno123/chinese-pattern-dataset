"""Migration tests."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pattern_dataset.db import init_db
from scripts.migrate_from_wenmai import (
    BASICS_TYPE_MAP,
    compute_sha256,
    migrate_basics,
    migrate_elements,
    migrate_qinghua,
    migrate_shanjing,
    parse_qinghua_ts,
    _pad_int,
)

WENMAI_ROOT = Path("D:/desktop/纹脉/wenmai")
QINGHUA_TS = WENMAI_ROOT / "src/data/qinghuaPatterns.ts"
QINGHUA_IMG_DIR = WENMAI_ROOT / "public/patterns/qinghua"
ELEMENTS_MANIFEST = WENMAI_ROOT / "public/elements/manifest.json"

wenmai_available = pytest.mark.skipif(
    not WENMAI_ROOT.exists(), reason="wenmai project not available"
)


@pytest.fixture
def empty_db(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    return db


def test_pad_int_helper():
    assert _pad_int("qh-1") == "qh-001"
    assert _pad_int("qh-42") == "qh-042"
    assert _pad_int("qh-335") == "qh-335"
    assert _pad_int("no-numbers-here") == "no-numbers-here"


def test_compute_sha256_known():
    """sha256('hello') is a known constant."""
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        f.write(b"hello")
        path = Path(f.name)
    try:
        h = compute_sha256(path)
        assert h == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    finally:
        path.unlink()


def test_basics_type_map_covers_all_expected_files():
    """Every basics filename in wenmai should map to a known type."""
    if not (WENMAI_ROOT / "public/patterns").exists():
        pytest.skip("wenmai project not available")
    expected_keys = {p.stem for p in (WENMAI_ROOT / "public/patterns").glob("*.webp")}
    missing = expected_keys - set(BASICS_TYPE_MAP.keys())
    assert not missing, f"basics files missing from BASICS_TYPE_MAP: {missing}"


@wenmai_available
def test_parse_qinghua_ts_returns_335_records():
    records = parse_qinghua_ts(QINGHUA_TS)
    assert len(records) == 335, f"expected 335 records, got {len(records)}"
    first = records[0]
    assert "id" in first
    assert first["id"].startswith("qh-")
    assert "name" in first
    assert "type" in first
    assert isinstance(first.get("tags"), list)


@wenmai_available
def test_migrate_qinghua_inserts_335(empty_db):
    count = migrate_qinghua(empty_db)
    assert count == 335, f"expected 335 qinghua migrated, got {count}"
    with sqlite3.connect(empty_db) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM patterns WHERE source_id = 'wenmai-qinghua'"
        ).fetchone()
        assert row[0] == 335
        # spot-check one
        sample = conn.execute(
            "SELECT pattern_id, source_ref, title, pattern_type, tags FROM patterns "
            "WHERE source_id = 'wenmai-qinghua' LIMIT 1"
        ).fetchone()
        assert sample[0].startswith("qh-")
        assert sample[1] == "qh-1"  # first source_ref
        assert sample[2]  # title non-empty
        # file_path exists on disk
        path_row = conn.execute(
            "SELECT file_path FROM patterns WHERE pattern_id = ?", (sample[0],)
        ).fetchone()
        assert Path("D:/desktop/pattern-dataset", path_row[0]).exists()


@wenmai_available
def test_migrate_basics_inserts_21(empty_db):
    count = migrate_basics(empty_db)
    assert count >= 17, f"expected at least 17 basics, got {count}"


@wenmai_available
def test_migrate_shanjing_inserts_25(empty_db):
    count = migrate_shanjing(empty_db)
    assert count == 25, f"expected 25 shanjing, got {count}"


@wenmai_available
def test_migrate_elements_inserts_60(empty_db):
    # elements reference parent patterns, so seed parents first
    migrate_qinghua(empty_db)
    migrate_basics(empty_db)
    migrate_shanjing(empty_db)
    count = migrate_elements(empty_db)
    assert count == 60, f"expected 60 elements, got {count}"
    with sqlite3.connect(empty_db) as conn:
        approved = conn.execute(
            "SELECT COUNT(*) FROM elements WHERE approved = 1"
        ).fetchone()[0]
        assert approved == 60, f"all 60 elements should be approved, got {approved}"
