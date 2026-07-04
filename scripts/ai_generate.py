"""Generate Chinese pattern images via openai-next.cn API (Gemini 3 Pro Image).

Four asset purposes:
  --purpose=element  : isolated motif on white bg, suitable for vectorization
  --purpose=tile     : seamless repeating background pattern
  --purpose=hero     : museum-quality hero shot for each pattern type

Outputs: data/patterns/ai-{purpose}/{type}-{NN}.png + .svg (auto-vectorized)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

# Make sibling scripts importable when run as `python scripts/ai_generate.py`
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pattern_dataset.db import DB_PATH, get_conn, insert_pattern, insert_source
from scripts.vectorize import png_to_svg

API_KEY = "sk-EHGrh8ZDedZv8UBt96B2Cd2678754c77Ae012c255311Fd59"
API_BASE = "https://api.openai-next.com/v1"
MODEL = "gemini-3-pro-image-preview"

DATASET_ROOT = Path("D:/desktop/pattern-dataset")

# 15 traditional pattern types with bilingual labels
PATTERN_TYPES = {
    "yun": ("云纹", "ruyi cloud"),
    "ruyi-cloud": ("如意云纹", "ruyi-head cloud"),
    "huiwen": ("回纹", "geometric fret / meander"),
    "juancao": ("卷草纹", "scrolling vine"),
    "interlocking-lotus": ("缠枝莲", "interlocking lotus"),
    "tuanlong": ("团龙", "coiled dragon roundel"),
    "baoxianghua": ("宝相花", "baoxiang rosette"),
    "lianhua": ("莲花纹", "lotus flower"),
    "mudan": ("牡丹纹", "peony"),
    "seawater-cliff": ("海水江崖", "sea water and cliffs"),
    "eight-treasures": ("八宝纹", "eight treasures"),
    "phoenix": ("凤纹", "phoenix"),
    "dragon": ("龙纹", "dragon"),
    "geometric-border": ("几何边饰", "geometric border"),
    "shanshui": ("山水纹", "landscape"),
}

# Purpose-specific prompt templates
PROMPT_TEMPLATES = {
    "element": (
        "A traditional Chinese {zh} ({en}) decorative element, isolated on pure white background, "
        "blue-and-white porcelain cobalt-blue line-art style, single complete motif, "
        "intricate hand-drawn linework, symmetrical, Ming dynasty aesthetic, "
        "no text, no watermark, no border, centered composition."
    ),
    "tile": (
        "A seamless repeating pattern of traditional Chinese {zh} ({en}), "
        "blue-and-white porcelain cobalt-blue on warm cream paper background, "
        "intricate hand-drawn linework, museum textile catalog style, "
        "fills entire frame edge-to-edge, Ming dynasty aesthetic, no text, no watermark."
    ),
    "hero": (
        "A museum-quality hero photograph of a traditional Chinese {zh} ({en}) on "
        "an imperial Ming-dynasty porcelain vase, dramatic soft studio lighting, "
        "deep cobalt-blue underglaze on white porcelain, ultra-detailed, "
        "shown at three-quarter angle, professional cultural heritage photography, "
        "warm gallery background, no text, no watermark."
    ),
}


def generate_one(client: httpx.Client, prompt: str, dest: Path) -> tuple[bool, str]:
    """Generate one image. Returns (success, msg)."""
    try:
        r = client.post(
            f"{API_BASE}/images/generations",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
            },
            timeout=180,
        )
    except Exception as e:
        return False, f"req error: {e}"

    if r.status_code != 200:
        return False, f"http {r.status_code}: {r.text[:200]}"

    items = r.json().get("data") or []
    if not items:
        return False, "no data"
    item = items[0]
    if "b64_json" in item:
        img = base64.b64decode(item["b64_json"])
    elif "url" in item:
        try:
            img = httpx.get(item["url"], timeout=60).content
        except Exception as e:
            return False, f"url dl err: {e}"
    else:
        return False, f"unknown format: {list(item.keys())}"

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(img)
    return True, f"{len(img)} bytes"


def compute_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--purpose",
        choices=["element", "tile", "hero"],
        required=True,
    )
    parser.add_argument(
        "--type",
        help="pattern type key (e.g. yun, juancao). If omitted, do all types.",
    )
    parser.add_argument("--count", type=int, default=1, help="how many per type")
    parser.add_argument("--vectorize", action="store_true", help="also vectorize to SVG")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    types = [args.type] if args.type else list(PATTERN_TYPES.keys())
    template = PROMPT_TEMPLATES[args.purpose]
    out_dir = DATASET_ROOT / f"data/patterns/ai-{args.purpose}"
    out_dir.mkdir(parents=True, exist_ok=True)
    source_id = f"ai-gemini3-{args.purpose}"

    client = httpx.Client(timeout=200)

    with get_conn(args.db_path) as conn:
        insert_source(
            conn,
            {
                "source_id": source_id,
                "source_type": "ai_generated",
                "license": "generated",
                "license_url": None,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "api_response": {
                    "endpoint": f"{API_BASE}/images/generations",
                    "model": MODEL,
                    "purpose": args.purpose,
                },
                "notes": f"AI-generated {args.purpose} via Gemini 3 Pro Image. Excluded from LoRA training set.",
            },
        )

    total = 0
    failed = 0
    for type_key in types:
        if type_key not in PATTERN_TYPES:
            print(f"[skip] unknown type: {type_key}")
            continue
        zh, en = PATTERN_TYPES[type_key]
        prompt = template.format(zh=zh, en=en)
        for i in range(args.count):
            short = hashlib.md5(f"{type_key}-{i}-{time.time()}".encode()).hexdigest()[:8]
            dest = out_dir / f"{type_key}-{i:02d}-{short}.png"
            print(f"[gen] {type_key}#{i} ({zh})...")
            ok, msg = generate_one(client, prompt, dest)
            if not ok:
                print(f"  [err] {msg}")
                failed += 1
                time.sleep(2)
                continue

            sha = compute_sha256(dest)
            try:
                with Image.open(dest) as img:
                    w, h = img.size
            except Exception:
                w, h = None, None

            vector_path = None
            if args.vectorize and args.purpose == "element":
                svg = dest.with_suffix(".svg")
                v_ok, _ = png_to_svg(dest, svg, threshold=180)
                if v_ok:
                    vector_path = str(svg.relative_to(DATASET_ROOT)).replace("\\", "/")

            pattern_id = f"ai-{args.purpose}-{type_key}-{i:02d}-{short}"
            with get_conn(args.db_path) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO patterns "
                    "(pattern_id, source_id, source_ref, file_path, file_format, "
                    "width_px, height_px, sha256, title, pattern_type, tags, "
                    "review_status, purpose, vector_path) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        pattern_id,
                        source_id,
                        f"{type_key}#{i}",
                        str(dest.relative_to(DATASET_ROOT)).replace("\\", "/"),
                        "png",
                        w,
                        h,
                        sha,
                        f"{zh} ({en})",
                        zh,
                        json.dumps(
                            [zh, en, "ai-generated", args.purpose], ensure_ascii=False
                        ),
                        "pending",
                        args.purpose,
                        vector_path,
                    ),
                )
            total += 1
            print(f"  [ok] {dest.name} {w}x{h}{' +svg' if vector_path else ''}")
            time.sleep(1)

    client.close()
    print(f"\n[summary] generated={total} failed={failed}")


if __name__ == "__main__":
    main()
