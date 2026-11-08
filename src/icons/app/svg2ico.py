#!/usr/bin/env python3
"""Convert SVG files to 256x256 ICO files."""

import sys
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image
    from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, Qt
    from PyQt6.QtGui import QGuiApplication, QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer
except ImportError:
    print("Install dependencies: pip install PyQt6 pillow")
    sys.exit(1)


SIZE = 256


def svg_to_ico(svg_path: Path, ico_path: Path | None = None) -> Path:
    svg_path = svg_path.resolve()
    if not svg_path.is_file():
        raise FileNotFoundError(f"SVG not found: {svg_path}")

    ico_path = (ico_path or svg_path.with_suffix(".ico")).resolve()
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise ValueError(f"Invalid SVG: {svg_path}")

    image = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    renderer.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
    renderer.render(painter)
    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(buffer, "PNG"):
        raise RuntimeError("Could not render SVG to PNG")
    buffer.close()

    with Image.open(BytesIO(bytes(data))) as rendered:
        rendered.convert("RGBA").save(ico_path, format="ICO", sizes=[(SIZE, SIZE)])

    return ico_path


def main() -> None:
    app = QGuiApplication([])
    args = sys.argv[1:]

    if len(args) > 2:
        print("Usage: python svg2ico.py [input.svg [output.ico]]")
        sys.exit(1)

    if args:
        files = [Path(args[0])]
        output = Path(args[1]) if len(args) == 2 else None
    else:
        files = sorted(Path.cwd().glob("*.svg"))
        output = None
        if not files:
            print("No SVG files found in the current folder.")
            sys.exit(1)

    try:
        for svg in files:
            print(f"Created: {svg_to_ico(svg, output)}")
    except Exception as error:
        print(f"Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
