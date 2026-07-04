"""Vectorize PNG patterns to SVG using potrace."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from potrace import potrace as pt

DATASET_ROOT = Path("D:/desktop/pattern-dataset")


def png_to_svg(png_path: Path, svg_path: Path, threshold: int = 180) -> tuple[bool, str]:
    """Convert a PNG to SVG via potrace.

    threshold: 0-255 luminance cutoff. Pixels DARKER than threshold = ink.
    Returns (success, message).
    """
    try:
        with Image.open(png_path) as img:
            arr = np.array(img.convert("RGB"))
    except Exception as e:
        return False, f"open error: {e}"

    # Compute luminance; ink = dark pixels
    lum = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2])
    # potracer.Bitmap auto-thresholds: data > 127 = "ink". Invert so dark
    # pixels become "ink" after thresholding.
    inv = 255 - lum
    inv_bin = np.where(lum < threshold, 255, 0).astype(np.uint8)

    if inv_bin.sum() == 0:
        return False, "no ink pixels (image is all-white)"

    bm = pt.Bitmap(inv_bin)
    paths = bm.trace()

    h, w = inv_bin.shape
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="no"?>']
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}">'
    )
    out.append('<g fill="currentColor" stroke="none" fill-rule="evenodd">')

    # Skip paths that look like the image border (start at corner)
    n_curves = 0
    for path in paths:
        sp = path.start_point
        # Skip paths starting near image border (likely the outer rectangle)
        if (sp.x < 5 or sp.x > w - 5) and (sp.y < 5 or sp.y > h - 5):
            continue
        if len(path.segments) < 5:  # skip tiny noise paths
            continue
        d_parts = [f"M {sp.x:.2f} {sp.y:.2f}"]
        for seg in path.segments:
            ep = seg.end_point
            if seg.is_corner:
                c = seg.c
                d_parts.append(f"L {c.x:.2f} {c.y:.2f}")
                d_parts.append(f"L {ep.x:.2f} {ep.y:.2f}")
            else:
                c1 = seg.c1
                c2 = seg.c2
                d_parts.append(
                    f"C {c1.x:.2f} {c1.y:.2f} {c2.x:.2f} {c2.y:.2f} {ep.x:.2f} {ep.y:.2f}"
                )
        d_parts.append("Z")
        out.append(f'<path d="{" ".join(d_parts)}"/>')
        n_curves += 1
    out.append("</g></svg>")

    if n_curves == 0:
        return False, "no curves after filtering"
    svg_path.write_text("\n".join(out), encoding="utf-8")
    return True, f"{n_curves} paths"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="PNG/WebP file (or directory)")
    parser.add_argument("--threshold", type=int, default=180)
    args = parser.parse_args()

    if args.input.is_dir():
        files = sorted(args.input.rglob("*.png")) + sorted(args.input.rglob("*.webp"))
    else:
        files = [args.input]

    ok = 0
    failed = 0
    for png in files:
        svg = png.with_suffix(".svg")
        if svg.exists():
            continue
        success, msg = png_to_svg(png, svg, threshold=args.threshold)
        if success:
            ok += 1
            print(f"  [ok] {png.name} -> {svg.name} ({msg})")
        else:
            failed += 1
            print(f"  [err] {png.name}: {msg}")
    print(f"\n[summary] ok={ok} failed={failed}")


if __name__ == "__main__":
    main()
