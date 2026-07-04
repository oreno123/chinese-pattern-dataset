"""Generate cultural stories for pattern types via chat completions.

Writes markdown story (origins, meaning, craft context, applications) into
the stories table. One story per pattern_type.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import httpx

from pattern_dataset.db import DB_PATH, get_conn

API_KEY = "sk-EHGrh8ZDedZv8UBt96B2Cd2678754c77Ae012c255311Fd59"
API_BASE = "https://api.openai-next.com/v1"
MODEL = "claude-sonnet-4-5-20250929"

DATASET_ROOT = Path("D:/desktop/pattern-dataset")

PATTERN_TYPES = {
    "yun": "云纹",
    "ruyi-cloud": "如意云纹",
    "huiwen": "回纹",
    "juancao": "卷草纹",
    "interlocking-lotus": "缠枝莲",
    "tuanlong": "团龙",
    "baoxianghua": "宝相花",
    "lianhua": "莲花纹",
    "mudan": "牡丹纹",
    "seawater-cliff": "海水江崖",
    "eight-treasures": "八宝纹",
    "phoenix": "凤纹",
    "dragon": "龙纹",
    "geometric-border": "几何边饰",
    "shanshui": "山水纹",
}

SYSTEM_PROMPT = """你是一名中国传统纹样文化研究者，擅长用生动准确的语言讲解纹样的历史与文化。
你的回答必须用中文，结构清晰，包含具体朝代、工艺细节、文化寓意。不要堆砌形容词。"""

USER_TEMPLATE = """请为「{zh}」这种中国传统纹样写一篇 400-600 字的文化讲解，按以下结构：

## 起源与演变
（最早出现在什么朝代？哪个工艺门类？如何演变？）

## 文化寓意
（古人为什么用它？象征什么？）

## 工艺背景
（在瓷器/织物/漆器/建筑里各自怎么实现？有什么技术特点？）

## 经典应用
（举 2-3 个具体文物或建筑案例，含朝代）

## 现代启示
（当代设计师如何重新诠释？）

请严格用 markdown 格式，不要加 emoji，不要写"答："之类前缀。"""


def fetch_story(client: httpx.Client, zh: str) -> str:
    r = client.post(
        f"{API_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_TEMPLATE.format(zh=zh)},
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
        },
        timeout=120,
    )
    if r.status_code != 200:
        raise RuntimeError(f"http {r.status_code}: {r.text[:300]}")
    data = r.json()
    return data["choices"][0]["message"]["content"]


def extract_section(md: str, header: str) -> str:
    """Extract first paragraph after a '## header' line."""
    lines = md.split("\n")
    capturing = False
    out = []
    for line in lines:
        if line.strip().startswith("##"):
            if capturing:
                break
            if header in line:
                capturing = True
        elif capturing and line.strip():
            out.append(line.strip())
    return " ".join(out)[:500]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", help="specific pattern type key (default: all)")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    args = parser.parse_args()

    types = [args.type] if args.type else list(PATTERN_TYPES.keys())
    client = httpx.Client(timeout=180)

    n_ok = 0
    n_fail = 0
    for k in types:
        if k not in PATTERN_TYPES:
            print(f"[skip] {k}")
            continue
        zh = PATTERN_TYPES[k]
        print(f"[story] {k} ({zh})...")
        try:
            md = fetch_story(client, zh)
        except Exception as e:
            print(f"  [err] {e}")
            n_fail += 1
            time.sleep(2)
            continue

        dynasty = extract_section(md, "起源")
        meaning = extract_section(md, "寓意")
        craft = extract_section(md, "工艺")
        application = extract_section(md, "应用")

        # Save markdown to docs/stories/
        story_path = DATASET_ROOT / "docs" / "stories" / f"{k}.md"
        story_path.parent.mkdir(parents=True, exist_ok=True)
        story_path.write_text(md, encoding="utf-8")

        with get_conn(args.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO stories "
                "(pattern_type, title, content_md, dynasty_origin, cultural_meaning, "
                "craft_context, application, model, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    k,
                    zh,
                    md,
                    dynasty,
                    meaning,
                    craft,
                    application,
                    MODEL,
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                ),
            )
        n_ok += 1
        print(f"  [ok] {story_path.name} ({len(md)} chars)")
        time.sleep(1)

    client.close()
    print(f"\n[summary] stories={n_ok} failed={n_fail}")


if __name__ == "__main__":
    main()
