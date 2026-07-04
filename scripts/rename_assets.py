"""Rename AI-generated pattern files from {type}-{i}-{hash}.{ext} to {type}-{purpose_short}-{NN}.{ext}.

purpose_short map:
  element           -> standalone
  element-corner    -> corner
  element-filler    -> filler
  element-border    -> border
  tile              -> tile
  hero              -> hero

Also updates patterns.file_path, patterns.vector_path, patterns.pattern_id in DB.
Idempotent: skips files already in new format.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from pattern_dataset.db import DB_PATH

DATASET_ROOT = Path("D:/desktop/pattern-dataset")

PURPOSE_SHORT = {
    "element": "standalone",
    "element-corner": "corner",
    "element-filler": "filler",
    "element-border": "border",
    "tile": "tile",
    "hero": "hero",
}

# old pattern: {type}-{NN}-{hash8}.{ext}
OLD_RE = re.compile(r"^([a-z-]+)-(\d{2})-[a-f0-9]{8}\.(png|svg|webp)$")


def new_stem(type_key: str, purpose: str, idx: int) -> str:
    short = PURPOSE_SHORT.get(purpose, purpose)
    return f"{type_key}-{short}-{idx:02d}"


def main():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT pattern_id, source_id, source_ref, file_path, vector_path, purpose "
            "FROM patterns WHERE source_id LIKE 'ai-%'"
        ).fetchall()

        renamed_files = 0
        renamed_rows = 0

        for pattern_id, source_id, source_ref, file_path, vector_path, purpose in rows:
            if not file_path:
                continue
            fp = DATASET_ROOT / file_path
            if not fp.exists():
                continue

            # extract type_key from source_ref (e.g. "yun#0" -> "yun")
            if "#" not in (source_ref or ""):
                continue
            type_key, idx_str = source_ref.split("#", 1)
            try:
                idx = int(idx_str)
            except ValueError:
                continue

            new_name = new_stem(type_key, purpose, idx)
            old_name = fp.stem  # e.g. "yun-00-debcf98b"

            # skip if already renamed
            if not OLD_RE.match(fp.name):
                continue

            new_fp = fp.with_name(f"{new_name}{fp.suffix}")
            if new_fp.exists() and new_fp != fp:
                # avoid clobber when same type+purpose+idx exists (collision from prior runs)
                new_fp = fp.with_name(f"{new_name}-{pattern_id[-4:]}{fp.suffix}")
            try:
                fp.rename(new_fp)
                renamed_files += 1
            except Exception as e:
                print(f"  [err] rename {fp.name}: {e}")
                continue

            new_rel = str(new_fp.relative_to(DATASET_ROOT)).replace("\\", "/")
            new_vector = None
            if vector_path:
                vp = DATASET_ROOT / vector_path
                if vp.exists():
                    new_vp = vp.with_name(f"{new_name}{vp.suffix}")
                    if new_vp != vp and not new_vp.exists():
                        try:
                            vp.rename(new_vp)
                            new_vector = str(new_vp.relative_to(DATASET_ROOT)).replace("\\", "/")
                        except Exception:
                            new_vector = vector_path
                    else:
                        new_vector = vector_path
                else:
                    new_vector = vector_path

            # also rename pattern_id for consistency
            new_pid = f"ai-{purpose}-{type_key}-{idx:02d}"
            # ensure uniqueness
            existing = conn.execute(
                "SELECT 1 FROM patterns WHERE pattern_id = ? AND pattern_id != ?",
                (new_pid, pattern_id),
            ).fetchone()
            if existing:
                new_pid = f"{new_pid}-{pattern_id[-4:]}"

            conn.execute(
                "UPDATE patterns SET file_path = ?, vector_path = ?, pattern_id = ? "
                "WHERE pattern_id = ?",
                (new_rel, new_vector, new_pid, pattern_id),
            )
            renamed_rows += 1

        print(f"[done] renamed {renamed_files} files, updated {renamed_rows} DB rows")


if __name__ == "__main__":
    main()
