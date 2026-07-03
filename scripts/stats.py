"""Print dataset stats: counts by source/type/license/element-approval."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from pattern_dataset.db import DB_PATH


def report(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]
        by_source = conn.execute(
            "SELECT source_id, COUNT(*) FROM patterns GROUP BY source_id ORDER BY COUNT(*) DESC"
        ).fetchall()
        by_type = conn.execute(
            "SELECT COALESCE(pattern_type, '(unset)'), COUNT(*) FROM patterns "
            "GROUP BY pattern_type ORDER BY COUNT(*) DESC"
        ).fetchall()
        by_status = conn.execute(
            "SELECT review_status, COUNT(*) FROM patterns GROUP BY review_status"
        ).fetchall()
        elements = conn.execute("SELECT COUNT(*) FROM elements").fetchone()[0]
        approved = conn.execute(
            "SELECT COUNT(*) FROM elements WHERE approved = 1"
        ).fetchone()[0]
        sources_count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    return {
        "patterns_total": total,
        "by_source": by_source,
        "by_type": by_type,
        "by_status": by_status,
        "elements_total": elements,
        "elements_approved": approved,
        "sources_total": sources_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    args = parser.parse_args()

    s = report(args.db_path)
    print(f"sources:    {s['sources_total']}")
    print(f"patterns:   {s['patterns_total']}")
    print("\nby source:")
    for src, n in s["by_source"]:
        print(f"  {src:<24} {n}")
    print("\nby review_status:")
    for status, n in s["by_status"]:
        print(f"  {status:<12} {n}")
    print("\nby pattern_type (top 10):")
    for t, n in s["by_type"][:10]:
        print(f"  {t:<24} {n}")
    print(f"\nelements:   {s['elements_total']} (approved: {s['elements_approved']})")


if __name__ == "__main__":
    main()
