#!/usr/bin/env python3
"""
SVG → ICO converter
Usage:
    python svg2ico.py                  # все .svg в текущей папке
    python svg2ico.py icon.svg         # конкретный файл
    python svg2ico.py icon.svg out.ico # с указанием имени выхода

Требует: pip install cairosvg pillow
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import cairosvg
    from PIL import Image
    from io import BytesIO
except ImportError:
    print("Нужны пакеты:  pip install cairosvg pillow")
    sys.exit(1)

# Размеры для ICO (Windows любит эти)
SIZES = [16, 24, 32, 48, 64, 128, 256]


def svg_to_ico(svg_path: Path, ico_path: Path | None = None) -> Path:
    svg_path = svg_path.resolve()
    if not svg_path.exists():
        raise FileNotFoundError(f"SVG не найден: {svg_path}")

    if ico_path is None:
        ico_path = svg_path.with_suffix(".ico")
    else:
        ico_path = ico_path.resolve()

    # Рендерим SVG в PNG разных размеров
    images = []
    for size in SIZES:
        png_data = cairosvg.svg2png(
            url=str(svg_path),
            output_width=size,
            output_height=size,
        )
        img = Image.open(BytesIO(png_data)).convert("RGBA")
        images.append(img)

    # Pillow сам собирает multi-size ICO
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
        # Все .svg в текущей папке
        svgs = sorted(Path(".").glob("*.svg"))
        if not svgs:
            print("В текущей папке нет .svg файлов")
            sys.exit(1)
        for svg in svgs:
            ico = svg.with_suffix(".ico")
            if ico.exists():
                print(f"  {svg.name} → {ico.name}  (уже есть, перезаписываю)")
            else:
                print(f"  {svg.name} → {ico.name}")
            svg_to_ico(svg, ico)
        print("Готово.")
        return

    svg = Path(args[0])
    ico = Path(args[1]) if len(args) > 1 else None

    try:
        out = svg_to_ico(svg, ico)
        print(f"Создан: {out}")
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()