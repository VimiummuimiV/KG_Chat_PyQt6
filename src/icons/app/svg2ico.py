#!/usr/bin/env python3
"""
SVG → ICO converter
Usage:
    python svg2ico.py                  # all .svg files in the current folder
    python svg2ico.py icon.svg         # convert a specific file
    python svg2ico.py icon.svg out.ico # specify the output filename

Requires: pip install cairosvg pillow
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import cairosvg
    from PIL import Image
    from io import BytesIO
except ImportError:
    print("Required packages: pip install cairosvg pillow")
    sys.exit(1)

# ICO sizes (preferred by Windows)
SIZES = [16, 24, 32, 48, 64, 128, 256]


def svg_to_ico(svg_path: Path, ico_path: Path | None = None) -> Path:
    svg_path = svg_path.resolve()
    if not svg_path.exists():
        raise FileNotFoundError(f"SVG not found: {svg_path}")

    if ico_path is None:
        ico_path = svg_path.with_suffix(".ico")
    else:
        ico_path = ico_path.resolve()

    # Render the SVG to PNG images at different sizes.
    images = []
    for size in SIZES:
        png_data = cairosvg.svg2png(
            url=str(svg_path),
            output_width=size,
            output_height=size,
        )
        img = Image.open(BytesIO(png_data)).convert("RGBA")
        images.append(img)

    # Pillow assembles the multi-size ICO.
    images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[1:],
    )
    return ico_path


def main() -> None:
    args = sys.argv[1:]

    if not args:
        # Convert all .svg files in the current folder.
        svgs = sorted(Path(".").glob("*.svg"))
        if not svgs:
            print("No .svg files found in the current folder.")
            sys.exit(1)
        for svg in svgs:
            ico = svg.with_suffix(".ico")
            if ico.exists():
                print(f"  {svg.name} → {ico.name}  (already exists, overwriting)")
            else:
                print(f"  {svg.name} → {ico.name}")
            svg_to_ico(svg, ico)
        print("Done.")
        return

    svg = Path(args[0])
    ico = Path(args[1]) if len(args) > 1 else None

    try:
        out = svg_to_ico(svg, ico)
        print(f"Created: {out}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()