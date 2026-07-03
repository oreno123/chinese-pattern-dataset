"""Dataclass models for the pattern dataset."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Source:
    source_id: str
    source_type: str
    license: str | None = None
    license_url: str | None = None
    fetched_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )
    api_response: dict | None = None
    notes: str | None = None


@dataclass
class Pattern:
    pattern_id: str
    source_id: str
    source_ref: str | None
    file_path: str
    file_format: str
    sha256: str
    width_px: int | None = None
    height_px: int | None = None
    title: str | None = None
    dynasty: str | None = None
    pattern_type: str | None = None
    pattern_subtype: str | None = None
    main_colors: list[str] | None = None
    complexity: int | None = None
    caption: str | None = None
    caption_short: str | None = None
    tags: list[str] | None = None
    review_status: str = "pending"


@dataclass
class Element:
    element_id: str
    pattern_id: str
    file_path: str
    bbox: list[int] | None = None
    extractor: str | None = None
    approved: int = 0
    element_type: str | None = None
