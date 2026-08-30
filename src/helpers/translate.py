"""Minimal bilingual helper (en/ru). Strings stay next to call sites."""
from PyQt6.QtCore import QObject, pyqtSignal


class _Translator(QObject):
    language_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._lang = "en"

    def set_language(self, code: str) -> None:
        code = code if code in ("en", "ru") else "en"
        if code == self._lang:
            return
        self._lang = code
        self.language_changed.emit(code)

    @property
    def language(self) -> str:
        return self._lang

    def tr(self, en: str, ru: str) -> str:
        return ru if self._lang == "ru" else en


_tr = _Translator()


def set_language(code: str) -> None:
    _tr.set_language(code)


def get_language() -> str:
    return _tr.language


def tr(en: str, ru: str) -> str:
    return _tr.tr(en, ru)


def on_language_changed(slot):
    """Connect a callable that receives the new language code."""
    _tr.language_changed.connect(slot)
