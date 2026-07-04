"""Generate an HTML preview of patterns grouped by source + purpose."""
from __future__ import annotations

import sqlite3
import html
from pathlib import Path
from pattern_dataset.db import DB_PATH

DATASET_ROOT = Path("D:/desktop/pattern-dataset")
OUT_HTML = DATASET_ROOT / "docs" / "preview.html"

PER_SOURCE = 30

CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, "Microsoft YaHei", sans-serif; margin: 0; padding: 24px; background: #f5f5f7; color: #222; }
h1 { margin: 0 0 8px; font-size: 24px; }
h2 { margin: 32px 0 12px; font-size: 18px; border-bottom: 2px solid #ddd; padding-bottom: 4px; }
h3 { margin: 16px 0 8px; font-size: 14px; color: #666; font-weight: 600; }
.summary { color: #666; margin-bottom: 16px; font-size: 14px; }
.section { background: white; padding: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin-bottom: 24px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.card { background: #fafafa; border-radius: 6px; overflow: hidden; font-size: 12px; border: 1px solid #eee; }
.card img, .card .svg-wrap { width: 100%; height: 200px; display: block; background: repeating-conic-gradient(#fff 0 25%, #f0f0f0 0 50%) 50% / 16px 16px; object-fit: contain; }
.card .svg-wrap { padding: 0; display: flex; align-items: center; justify-content: center; background: #fff; }
.card .svg-wrap svg { width: 90%; height: 90%; }
.card .meta { padding: 8px; background: white; border-top: 1px solid #eee; }
.card .title { font-weight: 600; color: #333; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card .sub { color: #888; font-size: 11px; }
.card .badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; background: #eef; color: #336; margin-right: 4px; }
.card .badge.purpose-element { background: #fef; color: #636; }
.card .badge.purpose-tile { background: #efe; color: #363; }
.card .badge.purpose-hero { background: #fee; color: #633; }
.card .badge.purpose-reference { background: #eef; color: #336; }
.card .svg-toggle { font-size: 10px; padding: 4px 8px; background: #007bff; color: white; border-radius: 3px; cursor: pointer; display: inline-block; margin-top: 4px; }
.color-picker-row { display: flex; gap: 4px; margin-top: 6px; }
.color-swatch { width: 16px; height: 16px; border-radius: 50%; border: 1px solid #ccc; cursor: pointer; }
.color-swatch.active { box-shadow: 0 0 0 2px #333; }
.footer { margin-top: 40px; padding: 16px; background: #fff; border-radius: 8px; color: #666; font-size: 12px; }
.tabs { display: flex; gap: 4px; margin-bottom: 12px; }
.tab { padding: 6px 12px; border: 1px solid #ddd; border-radius: 4px; cursor: pointer; background: white; font-size: 13px; }
.tab.active { background: #333; color: white; border-color: #333; }
"""


def img_tag(abs_path: str) -> str:
    return f'<img src="file:///{abs_path}" loading="lazy" onerror="this.style.background=\'#fcc\';this.alt=\'err\'">'


def svg_tag(abs_path: str) -> str:
    """Inline SVG content for color theming."""
    try:
        content = Path(abs_path).read_text(encoding="utf-8")
        # Strip XML declaration
        content = content.split("?>", 1)[-1] if "<?" in content else content
        return f'<div class="svg-wrap" data-svg-path="{abs_path}">{content}</div>'
    except Exception:
        return '<div class="svg-wrap">[svg load err]</div>'


def main():
    with sqlite3.connect(DB_PATH) as c:
        sources = c.execute(
            "SELECT source_id, COUNT(*) FROM patterns GROUP BY source_id ORDER BY COUNT(*) DESC"
        ).fetchall()

        body = [f"<h1>Chinese Pattern Dataset Preview</h1>"]
        total = sum(s[1] for s in sources)
        body.append(
            f'<div class="summary">Total <b>{total}</b> patterns across <b>{len(sources)}</b> sources. '
            f'Showing up to {PER_SOURCE} per source. SVG assets inline + color-themeable.</div>'
        )

        for source_id, count in sources:
            rows = c.execute(
                "SELECT pattern_id, title, file_path, dynasty, pattern_type, width_px, height_px, purpose, vector_path "
                "FROM patterns WHERE source_id = ? ORDER BY RANDOM() LIMIT ?",
                (source_id, PER_SOURCE),
            ).fetchall()
            body.append(f'<div class="section">')
            body.append(
                f"<h2>{html.escape(source_id)} <span style='color:#888;font-weight:normal;font-size:14px'>({count} total)</span></h2>"
            )
            body.append('<div class="grid">')
            for r in rows:
                pid, title, fp, dynasty, ptype, w, h, purpose, vector = r
                title_disp = title or "(no title)"
                sub_parts = []
                if dynasty:
                    sub_parts.append(dynasty[:30])
                if ptype:
                    sub_parts.append(ptype)
                if w and h:
                    sub_parts.append(f"{w}×{h}")
                sub = " · ".join(sub_parts) or pid

                abs_path = (DATASET_ROOT / fp).resolve().as_posix()
                has_vector = bool(vector)
                badge = f'<span class="badge purpose-{purpose or "reference"}">{purpose or "reference"}</span>'
                vec_badge = '<span class="badge" style="background:#0f0;color:#060">svg</span>' if has_vector else ''
                svg_btn = (
                    f'<div class="svg-toggle" onclick="toggleSvg(this,\'{abs_path}\')">view svg</div>'
                    if has_vector
                    else ""
                )

                body.append(
                    f'<div class="card">{img_tag(abs_path)}'
                    f'<div class="meta">{badge}{vec_badge}'
                    f'<div class="title">{html.escape(title_disp[:40])}</div>'
                    f'<div class="sub">{html.escape(sub[:60])}</div>'
                    f'{svg_btn}</div></div>'
                )
            body.append("</div></div>")

        # Stories section
        body.append('<div class="section">')
        body.append("<h2>Cultural Stories <span style='color:#888;font-weight:normal;font-size:14px'>文化讲解</span></h2>")
        stories = c.execute("SELECT pattern_type, title, dynasty_origin FROM stories ORDER BY pattern_type").fetchall()
        if stories:
            body.append('<div class="grid">')
            for st_type, st_title, st_dyn in stories:
                md_path = (DATASET_ROOT / "docs" / "stories" / f"{st_type}.md").resolve().as_posix()
                body.append(
                    f'<div class="card" style="padding:12px">'
                    f'<div class="title">{html.escape(st_title)} ({st_type})</div>'
                    f'<div class="sub">{html.escape((st_dyn or "")[:80])}</div>'
                    f'<div class="svg-toggle" style="margin-top:8px" onclick="openStory(\'file:///{md_path}\')">open</div>'
                    f'</div>'
                )
            body.append("</div>")
        else:
            body.append("<p style='color:#888'>No stories yet — run scripts/ai_story.py</p>")
        body.append("</div>")

    body.append(
        """<script>
function toggleSvg(btn, pngPath) {
    const card = btn.closest('.card');
    const img = card.querySelector('img');
    if (img.dataset.svgShown === '1') {
        img.style.display = 'block';
        img.src = pngPath;
        img.dataset.svgShown = '0';
        btn.textContent = 'view svg';
        return;
    }
    const svgPath = pngPath.replace(/\\.png$/, '.svg').replace(/\\.webp$/, '.svg');
    fetch('file:///' + svgPath).then(r => r.text()).then(t => {
        img.style.display = 'none';
        const wrap = document.createElement('div');
        wrap.className = 'svg-wrap';
        wrap.innerHTML = t;
        img.parentNode.appendChild(wrap);
        img.dataset.svgShown = '1';
        btn.textContent = 'view png';
        // color picker
        if (!card.querySelector('.color-picker-row')) {
            const colors = ['#1e3a8a', '#dc2626', '#059669', '#d97706', '#7c3aed', '#111827'];
            const row = document.createElement('div');
            row.className = 'color-picker-row';
            colors.forEach(c => {
                const sw = document.createElement('div');
                sw.className = 'color-swatch';
                sw.style.background = c;
                sw.onclick = () => {
                    wrap.style.color = c;
                    row.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
                    sw.classList.add('active');
                };
                row.appendChild(sw);
            });
            card.querySelector('.meta').appendChild(row);
        }
    });
}
function openStory(url) { window.open(url, '_blank'); }
</script>"""
    )

    body.append('<div class="footer">Generated by scripts/preview_html.py · Click "view svg" to see vectorized version + theme colors</div>')

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(
        f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>Pattern Dataset Preview</title><style>{CSS}</style></head><body>"
        + "".join(body)
        + "</body></html>",
        encoding="utf-8",
    )
    print(f"[ok] wrote {OUT_HTML}")


if __name__ == "__main__":
    main()
