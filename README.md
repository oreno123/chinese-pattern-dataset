# Chinese Traditional Pattern Dataset

A structured dataset of Chinese traditional decorative patterns, curated for cultural research, generative model training (LoRA / DreamBooth), and creative applications.

```yaml
# HF Dataset Card Metadata
license: cc-by-nc-sa-4.0
language: zh
tags:
  - chinese-traditional
  - pattern
  - cultural-heritage
  - lora-training
size_categories:
  - 1K<n<10K
task_categories:
  - text-to-image
  - image-classification
```

## Status

**v0.1 (in development)** — Schema + 377 seed patterns (335 qinghua + 17 basics + 25 shanjing) migrated from the wenmai project. Smithsonian Open Access ingestion, Vision auto-annotation, and LoRA export pipeline are tracked in subsequent phases.

## Directory Structure

```
pattern-dataset/
├── data/
│   ├── patterns/         # main pattern images (1024px target)
│   │   └── qinghua/      # qh-001.png ... qh-335.png
│   ├── elements/         # extracted standalone motifs
│   └── raw/              # original downloads (gitignored)
├── db/
│   ├── patterns.db       # main SQLite database (committed)
│   ├── schema.sql        # DDL (versioned)
│   └── seed/
│       └── taxonomy.json # controlled vocabulary
├── scripts/              # operational scripts
├── src/pattern_dataset/  # internal Python package
├── tests/
└── docs/
```

## Quick Start

```bash
# install
pip install -e ".[dev]"

# initialize database
python scripts/init_db.py

# migrate seed patterns from wenmai
python scripts/migrate_from_wenmai.py

# stats
python scripts/stats.py
```

## Schema (5 tables)

- `sources` — provenance: one row per acquisition batch (e.g. `wenmai-qinghua`, `smithsonian`)
- `patterns` — main pattern records: file path, SHA256, type, dynasty, colors, caption
- `elements` — extracted motifs derived from a parent pattern
- `tags` — controlled vocabulary (pattern_type / dynasty / shape / color)
- `annotations` — annotation audit log (re-annotations append, never overwrite)

See `db/schema.sql` for full DDL.

## License

Dataset code: see `LICENSE` (CC-BY-NC-SA-4.0).

Individual pattern images retain their source license (recorded in `sources.license` and per-row `notes`). Commercial LoRA training subsets filter to CC0 + CC-BY + public_domain + generated sources only.

## Acknowledgements

- 纹脉 (wenmai) project — seed patterns and element extraction pipeline
- Smithsonian Open Access — public-domain 3D and 2D cultural heritage data
- Sketchfab — Creative Commons 3D models
