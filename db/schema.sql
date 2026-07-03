-- Chinese Traditional Pattern Dataset - SQLite schema
-- Version: 0.1.0

PRAGMA foreign_keys = ON;

-- sources: one row per acquisition batch
CREATE TABLE IF NOT EXISTS sources (
    source_id      TEXT PRIMARY KEY,
    source_type    TEXT NOT NULL CHECK (source_type IN ('api', 'scan', 'ai_generated', 'manual')),
    license        TEXT,
    license_url    TEXT,
    fetched_at     TEXT NOT NULL,
    api_response   TEXT,
    notes          TEXT
);

-- patterns: main pattern records
CREATE TABLE IF NOT EXISTS patterns (
    pattern_id      TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    source_ref      TEXT,
    file_path       TEXT NOT NULL,
    file_format     TEXT NOT NULL,
    width_px        INTEGER,
    height_px       INTEGER,
    sha256          TEXT NOT NULL UNIQUE,
    title           TEXT,
    dynasty         TEXT,
    pattern_type    TEXT,
    pattern_subtype TEXT,
    main_colors     TEXT,
    complexity      INTEGER CHECK (complexity IS NULL OR (complexity BETWEEN 1 AND 5)),
    caption         TEXT,
    caption_short   TEXT,
    tags            TEXT,
    vision_model    TEXT,
    vision_version  TEXT,
    annotated_at    TEXT,
    review_status   TEXT NOT NULL DEFAULT 'pending'
                    CHECK (review_status IN ('pending', 'auto', 'approved', 'rejected')),
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_patterns_type    ON patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_patterns_dynasty ON patterns(dynasty);
CREATE INDEX IF NOT EXISTS idx_patterns_source  ON patterns(source_id);
CREATE INDEX IF NOT EXISTS idx_patterns_status  ON patterns(review_status);

-- elements: extracted standalone motifs
CREATE TABLE IF NOT EXISTS elements (
    element_id     TEXT PRIMARY KEY,
    pattern_id     TEXT NOT NULL REFERENCES patterns(pattern_id) ON DELETE CASCADE,
    file_path      TEXT NOT NULL,
    bbox           TEXT,
    extractor      TEXT,
    approved       INTEGER NOT NULL DEFAULT 0,
    element_type   TEXT
);
CREATE INDEX IF NOT EXISTS idx_elements_pattern ON elements(pattern_id);

-- tags: controlled vocabulary
CREATE TABLE IF NOT EXISTS tags (
    tag_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT UNIQUE NOT NULL,
    category  TEXT
);

-- annotations: audit log for re-annotations
CREATE TABLE IF NOT EXISTS annotations (
    annotation_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id     TEXT NOT NULL REFERENCES patterns(pattern_id) ON DELETE CASCADE,
    model_version  TEXT NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    confidence     REAL
);
CREATE INDEX IF NOT EXISTS idx_annotations_pattern ON annotations(pattern_id);
