"""Builds the application stylesheet: qdarktheme base + templates from styles/ filled with palette tokens."""

from functools import lru_cache
from pathlib import Path
from string import Template

import qdarktheme
from PyQt6.QtWidgets import QWidget

from themes.palette import PALETTES

_STYLES_DIR = Path(__file__).parent / "styles"
_FIELD_BORDER = 1  # qdarktheme field border; min-height excludes it


@lru_cache(maxsize=None)
def build_stylesheet(theme: str, input_height: int) -> str:
    """Return the full application stylesheet of a theme; built once per theme and input height."""
    palette = {**PALETTES[theme], "input_height": input_height - 2 * _FIELD_BORDER}
    templates = (Template(path.read_text(encoding="utf-8")) for path in sorted(_STYLES_DIR.glob("*.qss")))
    return qdarktheme.load_stylesheet(theme) + "\n" + "\n".join(t.substitute(palette) for t in templates)


def repolish(widget: QWidget):
    """Re-evaluate the stylesheet of one widget after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def set_style_property(widget: QWidget, name: str, value):
    """Switch a state the stylesheet selects on, e.g. QLineEdit[validation="invalid"]."""
    if widget.property(name) != value:
        widget.setProperty(name, value)
        repolish(widget)
