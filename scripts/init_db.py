"""Initialize the SQLite database from schema.sql."""
from __future__ import annotations

import argparse
from pathlib import Path

from pattern_dataset.db import DB_PATH, init_db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    args = parser.parse_args()
    init_db(args.db_path)
    print(f"[ok] initialized {args.db_path}")


if __name__ == "__main__":
    main()
