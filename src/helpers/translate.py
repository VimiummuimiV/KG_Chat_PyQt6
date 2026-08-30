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


class TrStr(str):
    """A str that remembers the (en, ru) pair it was built from.

    Lets a widget built with tr(en, ru) be retranslated later - via
    setter(tr(text.en, text.ru)) - without the caller having to keep the
    original strings around separately.
    """
    __slots__ = ("en", "ru")

    def __new__(cls, en: str, ru: str, value: str):
        obj = str.__new__(cls, value)
        obj.en = en
        obj.ru = ru
        return obj


def set_language(code: str) -> None:
    _tr.set_language(code)


def get_language() -> str:
    return _tr.language


def tr(en: str, ru: str) -> str:
    return TrStr(en, ru, _tr.tr(en, ru))


def on_language_changed(slot):
    """Connect a callable that receives the new language code."""
    _tr.language_changed.connect(slot)


class TranslatableMixin:
    """Opt-in real-time retranslation for widgets built with tr()."""
    def _init_translatable(self):
        self._translatable = []

    def _register_tr(self, setter, text):
        if isinstance(text, TrStr):
            self._translatable.append((setter, text))

    def _retranslate_all(self, _code=None):
        for setter, text in self._translatable:
            setter(tr(text.en, text.ru))