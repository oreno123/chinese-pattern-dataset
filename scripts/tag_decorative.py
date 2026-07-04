"""Tag FSG/CHNDM records as 'decorative' vs 'painting' based on topic keywords.

Updates patterns.review_status='rejected' for non-decorative categories
(paintings, landscapes, scrolls) so they don't go into LoRA training.
Decorative categories (ceramic, textile, bronze, jade, lacquer, wallpaper,
metalwork, glass) keep review_status='pending' for Vision annotation.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pattern_dataset.db import DB_PATH

# Keywords that signal "decorative art with patterns" (keep)
DECORATIVE_KEYWORDS = [
    "porcelain", "ceramic", "stoneware", "pottery", "ware",
    "silk", "embroider", "tapestry", "textile", "fabric", "velvet",
    "bronze", "metalwork", "silver", "iron",
    "jade",
    "lacquer",
    "wallpaper",
    "glass",
    "vase", "bowl", "plate", "jar", "bottle", "cup", "dish",
    "fragment", "panel", "textile",
]

# Keywords that signal "fine art painting" (reject)
PAINTING_KEYWORDS = [
    # explicit painting formats
    "painting", "paintings", "scroll painting", "hanging scroll",
    "handscroll", "album leaf", "fan painting",
    # landscapes
    "landscape", "mountains and water", "mountain", "river", "lake",
    "waterfall", "snowscape",
    # figures & portraits
    "calligraphy", "calligrap", "poem", "poetry",
    "scholar", "literati", "sage",
    "portrait", "figure painting", "figure on horseback", "lady by",
    "standing figure", "seated figure", "figure of a",
    "luohan", "arhat", "buddha", "bodhisattva", "attendant",
    "monk", "priest", "immortal",
    # narrative scene markers (specific actions = paintings, not motifs)
    "awaiting", "ferry", "clearing snow", "under tree", "in landscape",
    "in reeds", "by the water", "water's edge", "orchid cliff",
    # bird-and-flower / nature scenes
    "magpies under", "ducks in", "ducks among", "ducks at", "mandarin ducks",
    "butterflies and", "birds and flowers", "birds among", "birds in",
    "quail", "peach branches", "flowering peach", "ears of grain",
    "rocks and", "rocks,", "prunus", "chrysanthemum",
    # narrative dragon/horse scenes (multi-animal in nature = painting, not motif)
    "dragons in clouds", "dragons in waters", "dragons in the",
    "dragons and clouds", "dragons and waters", "dragons and waves",
    "dragons among", "dragon and clouds", "dragon among clouds",
    "dragons contending", "nine dragons",
    # single-subject nature studies = bird-and-flower paintings
    "bird on", "bird and", "bird perched", "leafless branch",
    "hollyhocks", "peonies,", "peonies and", "peonies in",
    "peonies,", "lotuses and", "lotuses in",
    "cabbage", "gourds", "grapes", " melon", "chestnut", "walnut",
    "insects and", "cicada", "cricket", "grasshopper",
    # figure scenes
    "girl seated", "girl standing", "girl by", "boy on", "boy and",
    "woman seated", "woman by", "woman holding", "woman reading",
    "man seated", "man reading", "man standing",
    "embroidery frame", "at a desk", "at a table", "at the window",
    "weaving", "spinning", "sewing",
    # landscape / marine
    "royal barge", "barge at", "at sea", "boat on", "boats on",
    "ship on", "ships at", "fleet",
    "palace", "temple", "garden", "courtyard",
    # bird-and-flower classic subjects
    "pheasant", "kingfisher", "oriole", "egret",
    # narrative / story subjects ( paintings of figures in action)
    "parting from", "presenting tribute", "crossing the",
    "enjoying a meal", "studious woodcutter", "under autumn",
    "under a willow", "under a pine", "under trees", "under a tree",
    "rider and", "rider on",
    "taming the", "five pestilences", "zhong kui",
    # single-animal nature studies
    "water buffalo", "water-buffalo", "buffalo and",
    "drake and", "drake in", "horse and groom",
    "tatar,", "tatar and",
    # single plant / still life
    "eggplant", "birds and fruit", "birds and pines",
    "a breath of spring", "scenic", "in a garden",
    # religious narrative
    "bodhidharma", "buddha,", "laozi",
]


def classify(text: str) -> str:
    text_lower = text.lower()
    for kw in PAINTING_KEYWORDS:
        if kw in text_lower:
            return "painting"
    for kw in DECORATIVE_KEYWORDS:
        if kw in text_lower:
            return "decorative"
    return "unknown"


def main():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT pattern_id, title, tags, source_id FROM patterns "
            "WHERE source_id IN ('smithsonian-fsg', 'smithsonian-chndm')"
        ).fetchall()

        counts = {"decorative": 0, "painting": 0, "unknown": 0}
        for pid, title, tags_json, source_id in rows:
            tags = json.loads(tags_json) if tags_json else []
            text = " ".join([title or ""] + tags)
            cat = classify(text)
            counts[cat] += 1

            new_status = "rejected" if cat == "painting" else "pending"
            conn.execute(
                "UPDATE patterns SET review_status = ?, notes = COALESCE(notes, '') || "
                "'\\nclassified_as: ' || ? WHERE pattern_id = ?",
                (new_status, cat, pid),
            )

        print(f"classified {len(rows)} records:")
        for cat, n in counts.items():
            print(f"  {cat}: {n}")
        print(f"\npainting records set to review_status='rejected'")


if __name__ == "__main__":
    main()
