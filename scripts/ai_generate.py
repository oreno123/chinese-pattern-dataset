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

# Multiple working models for diversity + fault tolerance
MODELS = [
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image-preview",
]

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

# Purpose-specific prompt templates — multiple variants per purpose for diversity
PROMPT_TEMPLATES = {
    "element": [
        "A traditional Chinese {zh} ({en}) decorative element, isolated on pure white background, "
        "blue-and-white porcelain cobalt-blue line-art style, single complete motif, "
        "intricate hand-drawn linework, symmetrical, Ming dynasty aesthetic, "
        "no text, no watermark, no border, centered composition, line art only.",

        "A single Chinese {zh} ({en}) motif, court-art style, Yuan dynasty aesthetic, "
        "thick confident brushstrokes, pure cobalt-blue on warm cream paper, "
        "isolated and centered, museum specimen plate quality, line art only, no fill, no text.",

        "A delicate Chinese {zh} ({en}) pattern, Qing dynasty imperial porcelain style, "
        "fine elegant linework, soft underglaze blue on rice-paper white background, "
        "asymmetric naturalistic composition, intricate detail, line art only, no fill.",

        "A bold geometric Chinese {zh} ({en}) design, Song dynasty minimalist aesthetic, "
        "strong contrast, pure indigo-blue linework on pure white, "
        "centered single motif, museum catalog specimen, line art only.",
    ],
    "element-corner": [
        "A traditional Chinese {zh} ({en}) corner ornament, L-shaped quarter design filling "
        "the top-left corner, mirror-symmetric along the diagonal, cobalt-blue line-art "
        "on pure white background, Ming dynasty, line art only, no fill, no text.",

        "An ornate Chinese {zh} ({en}) corner flourish, baroque Qing-dynasty style, "
        "densely detailed, fills upper-left quadrant with diagonal symmetry, "
        "warm gold-outline variant on cream paper, line art only.",

        "A minimalist Chinese {zh} ({en}) corner bracket, Song-dynasty geometric, "
        "clean L-shaped, mirror-symmetric on diagonal, cobalt blue line on white, "
        "line art only.",
    ],
    "element-filler": [
        "A small Chinese {zh} ({en}) filler motif for tessellation, single small square unit, "
        "simple but elegant, blue-and-white cobalt line-art on pure white background, "
        "Ming dynasty, line art only, no fill, no text.",

        "A tiny repeatable Chinese {zh} ({en}) tile, embroidered silk textile style, "
        "Qing dynasty, single small unit, fine thread-like linework, "
        "line art only on cream paper background.",

        "A geometric Chinese {zh} ({en}) filler unit, Song-dynasty ceramic tile style, "
        "small square, bold cobalt linework on white, perfectly tessellates, line art only.",
    ],
    "element-border": [
        "A horizontal Chinese {zh} ({en}) border strip, repeating along the long axis, "
        "thin ribbon (height = 1/4 width), cobalt-blue line-art on pure white background, "
        "Ming dynasty, line art only, no fill, no text.",

        "A vertical-edge Chinese {zh} ({en}) border, Qing dynasty intricate style, "
        "tall thin column (width = 1/4 height), fine linework, line art only.",

        "A wraparound Chinese {zh} ({en}) frieze, Yuan dynasty bold style, "
        "horizontal strip with central repeating unit, strong contrast cobalt-on-cream, "
        "line art only.",
    ],
    "tile": [
        "A seamless repeating pattern of Chinese {zh} ({en}), blue-and-white porcelain cobalt "
        "line-art on warm cream paper, museum textile catalog style, fills entire frame, "
        "Ming dynasty, line art only, no text.",

        "An all-over Chinese {zh} ({en}) textile pattern, silk embroidery style, Qing dynasty, "
        "fine detailed thread-work in cobalt blue on cream, fills entire frame edge-to-edge, "
        "no border, no text.",

        "A geometric tessellation of Chinese {zh} ({en}), Song dynasty ceramic-tile aesthetic, "
        "bold indigo linework on white, perfectly seamless repeat, fills entire frame.",
    ],
    "hero": [
        "A museum-quality hero photograph of a Chinese {zh} ({en}) on an imperial Ming-dynasty "
        "porcelain vase, dramatic soft studio lighting, deep cobalt-blue underglaze on white "
        "porcelain, ultra-detailed, three-quarter angle, professional cultural heritage photography, "
        "warm gallery background, no text.",

        "A close-up hero shot of a Chinese {zh} ({en}) on a Qing imperial silk panel, "
        "soft museum lighting, golden thread on imperial yellow silk, intricate detail, "
        "professional cultural heritage photography, no text.",

        "A hero photograph of a Chinese {zh} ({en}) on a Tang-dynasty bronze mirror, "
        "polished metal surface with patina, dramatic side lighting, museum specimen quality, "
        "dark background, no text.",
    ],
}


def generate_one(client: httpx.Client, prompt: str, dest: Path, model: str | None = None) -> tuple[bool, str, str | None]:
    """Generate one image. Returns (success, msg, model_used)."""
    # Try specified model first, then fallback through the rest
    models_to_try = [model] if model else []
    models_to_try += [m for m in MODELS if m not in models_to_try]
    last_err = ""
    for m in models_to_try:
        try:
            r = client.post(
                f"{API_BASE}/images/generations",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": m,
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1024",
                },
                timeout=180,
            )
        except Exception as e:
            last_err = f"{m}: req {e}"
            continue

        if r.status_code != 200:
            last_err = f"{m}: http {r.status_code}"
            continue

        items = r.json().get("data") or []
        if not items:
            last_err = f"{m}: no data"
            continue
        item = items[0]
        if "b64_json" in item:
            img = base64.b64decode(item["b64_json"])
        elif "url" in item:
            try:
                img = httpx.get(item["url"], timeout=60).content
            except Exception as e:
                last_err = f"{m}: url dl {e}"
                continue
        else:
            last_err = f"{m}: unknown format"
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(img)
        return True, f"{len(img)} bytes", m
    return False, last_err, None


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
        choices=["element", "element-corner", "element-filler", "element-border", "tile", "hero"],
        required=True,
    )
    parser.add_argument(
        "--type",
        help="pattern type key (e.g. yun, juancao). If omitted, do all types.",
    )
    parser.add_argument("--count", type=int, default=1, help="how many per type")
    parser.add_argument("--vectorize", action="store_true", help="also vectorize to SVG")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--model", help="pin to specific model (default: rotate)")
    parser.add_argument("--concurrency", type=int, default=1, help="parallel workers (default 1; safe=3)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    types = [args.type] if args.type else list(PATTERN_TYPES.keys())
    templates = PROMPT_TEMPLATES[args.purpose]
    out_dir = DATASET_ROOT / f"data/patterns/ai-{args.purpose}"
    out_dir.mkdir(parents=True, exist_ok=True)
    source_id = f"ai-multi-{args.purpose}"

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
                    "models": MODELS,
                    "purpose": args.purpose,
                },
                "notes": f"AI-generated {args.purpose} via multi-model rotation. Excluded from LoRA training set.",
            },
        )

    # Build task list: (type_key, i, prompt, model_hint, dest)
    # File naming: {type}-{purpose_short}-{NN}.png (no hash, human-readable)
    PURPOSE_SHORT = {
        "element": "standalone",
        "element-corner": "corner",
        "element-filler": "filler",
        "element-border": "border",
        "tile": "tile",
        "hero": "hero",
    }
    short_purpose = PURPOSE_SHORT.get(args.purpose, args.purpose)

    tasks: list[tuple[str, int, str, str, Path]] = []
    for type_key in types:
        if type_key not in PATTERN_TYPES:
            print(f"[skip] unknown type: {type_key}")
            continue
        zh, en = PATTERN_TYPES[type_key]
        for i in range(args.count):
            template = templates[i % len(templates)]
            prompt = template.format(zh=zh, en=en)
            model_hint = MODELS[i % len(MODELS)] if not args.model else args.model
            dest = out_dir / f"{type_key}-{short_purpose}-{i:02d}.png"
            # If exists, append pid-suffix to avoid clobber
            if dest.exists():
                dest = out_dir / f"{type_key}-{short_purpose}-{i:02d}-{os.getpid()%1000:03d}.png"
            tasks.append((type_key, i, prompt, model_hint, dest))

    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    lock = threading.Lock()
    total = 0
    failed = 0

    def process(task):
        nonlocal total, failed
        type_key, i, prompt, model_hint, dest = task
        zh, en = PATTERN_TYPES[type_key]
        print(f"[gen] {type_key}#{i} ({zh}) [model={model_hint}]...")
        ok, msg, model_used = generate_one(client, prompt, dest, model=model_hint)
        if not ok:
            print(f"  [err] {type_key}#{i} {msg}")
            with lock:
                failed += 1
            return
        # Vectorize + DB insert under lock (potrace + sqlite are not thread-safe)
        with lock:
            sha = compute_sha256(dest)
            try:
                with Image.open(dest) as img:
                    w, h = img.size
            except Exception:
                w, h = None, None
            vector_path = None
            if args.vectorize and args.purpose.startswith("element"):
                svg = dest.with_suffix(".svg")
                v_ok, _ = png_to_svg(dest, svg, threshold=180)
                if v_ok:
                    vector_path = str(svg.relative_to(DATASET_ROOT)).replace("\\", "/")
            short = dest.stem  # e.g. "yun-standalone-00" or "yun-standalone-00-123"
            pattern_id = f"ai-{args.purpose}-{short}"
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
            print(f"  [ok] {dest.name} {w}x{h}{' +svg' if vector_path else ''} ({model_used})")

    if args.concurrency > 1:
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            list(ex.map(process, tasks))
    else:
        for t in tasks:
            process(t)

    client.close()
    print(f"\n[summary] generated={total} failed={failed}")


if __name__ == "__main__":
    main()
