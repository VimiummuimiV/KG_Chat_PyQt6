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


SIZES = [16, 24, 32, 48, 64, 96, 128, 256, 512]


def svg_to_pngs(svg_path: Path) -> list[Path]:
    output_dir = svg_path.parent / svg_path.stem
    output_dir.mkdir(exist_ok=True)

    created_files = []

    for size in SIZES:
        png_data = resvg_py.svg_to_bytes(
            svg_path=str(svg_path),
            width=size,
            height=size,
        )

        output_path = output_dir / f"{size}x{size}.png"

        with Image.open(BytesIO(png_data)) as image:
            image.convert("RGBA").save(output_path, format="PNG")

        created_files.append(output_path)

    return created_files


def main():
    script_dir = Path(__file__).resolve().parent
    svg_files = sorted(script_dir.glob("*.svg"))

    if not svg_files:
        print(f"No SVG files found in: {script_dir}")
        sys.exit(1)

    for svg in svg_files:
        try:
            created_files = svg_to_pngs(svg)
            print(f"Exported {svg.name}:")
            for path in created_files:
                print(f"  {path}")
        except Exception as error:
            print(f"Error: {svg.name}: {error}")


if __name__ == "__main__":
    main()
