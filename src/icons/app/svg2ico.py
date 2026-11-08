#!/usr/bin/env python3

import struct
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


def create_multi_size_ico(images: dict[int, bytes], output_path: Path) -> None:
    """Pack individually rendered PNG images into one multi-size ICO file."""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)

    entries = []
    image_data = bytearray()
    offset = 6 + count * 16

    for size, png_data in images.items():
        dimension = 0 if size == 256 else size

        entries.append(
            struct.pack(
                "<BBBBHHII",
                dimension,       # Width (0 means 256)
                dimension,       # Height (0 means 256)
                0,               # Color palette
                0,               # Reserved
                1,               # Color planes
                32,              # Bits per pixel
                len(png_data),   # Image data size
                offset,          # Image data offset
            )
        )

        image_data.extend(png_data)
        offset += len(png_data)

    output_path.write_bytes(header + b"".join(entries) + image_data)


def export_svg(svg_path: Path) -> tuple[list[Path], list[Path], Path]:
    output_dir = svg_path.parent / svg_path.stem
    png_dir = output_dir / "png"
    ico_dir = output_dir / "ico"

    png_dir.mkdir(parents=True, exist_ok=True)
    ico_dir.mkdir(parents=True, exist_ok=True)

    png_files = []
    ico_files = []
    rendered_images = {}

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
            image.save(ico_path, format="ICO", sizes=[(size, size)])
            ico_files.append(ico_path)

        # Keep the original Resvg render for the combined multi-size ICO.
        rendered_images[size] = png_data

    combined_ico_path = ico_dir / f"{svg_path.stem}.ico"
    create_multi_size_ico(rendered_images, combined_ico_path)

    return png_files, ico_files, combined_ico_path


def main():
    script_dir = Path(__file__).resolve().parent
    svg_files = sorted(script_dir.glob("*.svg"))

    if not svg_files:
        print(f"No SVG files found in: {script_dir}")
        sys.exit(1)

    for svg in svg_files:
        try:
            png_files, ico_files, combined_ico = export_svg(svg)

            print(f"Exported: {svg.name}")
            print(f"  PNG files: {len(png_files)}")
            print(f"  Individual ICO files: {len(ico_files)}")
            print(f"  Multi-size ICO: {combined_ico}")
        except Exception as error:
            print(f"Error: {svg.name}: {error}")


if __name__ == "__main__":
    main()
