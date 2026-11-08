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


SIZES = [16, 24, 32, 48, 64, 96, 128, 256]


def export_svg(svg_path: Path) -> tuple[list[Path], list[Path]]:
    output_dir = svg_path.parent / svg_path.stem
    png_dir = output_dir / "png"
    ico_dir = output_dir / "ico"

    png_dir.mkdir(parents=True, exist_ok=True)
    ico_dir.mkdir(parents=True, exist_ok=True)

    png_files = []
    ico_files = []

    for size in SIZES:
        png_data = resvg_py.svg_to_bytes(
            svg_path=str(svg_path),
            width=size,
            height=size,
        )

        with Image.open(BytesIO(png_data)) as rendered:
            image = rendered.convert("RGBA")

            png_path = png_dir / f"{size}x{size}.png"
            image.save(png_path, format="PNG")
            png_files.append(png_path)

            ico_path = ico_dir / f"{size}x{size}.ico"
            image.save(
                ico_path,
                format="ICO",
                sizes=[(size, size)],
            )
            ico_files.append(ico_path)

    return png_files, ico_files


def main():
    script_dir = Path(__file__).resolve().parent
    svg_files = sorted(script_dir.glob("*.svg"))

    if not svg_files:
        print(f"No SVG files found in: {script_dir}")
        sys.exit(1)

    for svg in svg_files:
        try:
            png_files, ico_files = export_svg(svg)

            print(f"Exported: {svg.name}")
            print(f"  PNG: {len(png_files)} files")
            print(f"  ICO: {len(ico_files)} files")
            print(f"  Output: {svg.parent / svg.stem}")
        except Exception as error:
            print(f"Error: {svg.name}: {error}")


if __name__ == "__main__":
    main()
