#!/usr/bin/env python3

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


def svg_to_ico(svg_path: Path) -> Path:
    ico_path = svg_path.with_suffix(".ico")

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
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()

    with Image.open(BytesIO(bytes(data))) as rendered:
        rendered.convert("RGBA").save(
            ico_path,
            format="ICO",
            sizes=[(SIZE, SIZE)]
        )

    return ico_path


def main():
    app = QGuiApplication([])

    script_dir = Path(__file__).resolve().parent
    files = sorted(script_dir.glob("*.svg"))

    if not files:
        print(f"No SVG files found in: {script_dir}")
        sys.exit(1)

    for svg in files:
        try:
            print(f"Created: {svg_to_ico(svg)}")
        except Exception as error:
            print(f"Error: {svg.name}: {error}")


if __name__ == "__main__":
    main()
