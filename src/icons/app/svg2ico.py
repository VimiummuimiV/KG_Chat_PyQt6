#!/usr/bin/env python3

import sys
from io import BytesIO
from pathlib import Path

try:
    import resvg_py
    from PIL import Image
except ImportError:
    print("Install dependencies: pip install resvg_py pillow")
    sys.exit(1)


SIZE = 256


def svg_to_ico(svg_path: Path) -> Path:
    ico_path = svg_path.with_suffix(".ico")

    png_data = resvg_py.svg_to_bytes(
        svg_path=str(svg_path),
        width=SIZE,
        height=SIZE,
    )

    with Image.open(BytesIO(png_data)) as image:
        image.convert("RGBA").save(
            ico_path,
            format="ICO",
            sizes=[(SIZE, SIZE)],
        )

    return ico_path


def main():
    script_dir = Path(__file__).resolve().parent
    svg_files = sorted(script_dir.glob("*.svg"))

    if not svg_files:
        print(f"No SVG files found in: {script_dir}")
        sys.exit(1)

    for svg in svg_files:
        try:
            print(f"Created: {svg_to_ico(svg)}")
        except Exception as error:
            print(f"Error: {svg.name}: {error}")


if __name__ == "__main__":
    main()
