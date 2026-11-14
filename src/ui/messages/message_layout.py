"""Word-wrap layout of a message body: one pass gives both the height and the positions the painter draws."""

import math
import re
from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional, Tuple

ROLE_TEXT = "text"
KIND_TEXT = "text"
KIND_LINK = "link"
KIND_EMOTICON = "emoticon"

_EPSILON = 0.01
_SPACES = re.compile(r"( +)")


@dataclass(frozen=True)
class Atom:
    """One piece of a message body in reading order: a text run, a link or an emoticon."""
    kind: str
    text: str
    role: str = ROLE_TEXT  # colour role: plain text, a mention kind or a competition value kind
    bold: bool = False
    url: str = ""
    is_media: bool = False
    size: Tuple[int, int] = (0, 0)  # emoticon pixmap size


@dataclass(slots=True)
class Fragment:
    """A piece of an Atom placed on one line; x and y are relative to the layout origin."""
    kind: str
    text: str
    role: str
    bold: bool
    x: float
    y: float
    width: float
    height: int
    url: str = ""
    is_media: bool = False


@dataclass(frozen=True)
class TextLayout:
    """Placed fragments with the total height and the spot right after the last one.

    The same placement holds for every width in [min_width, max_width): no line grows past the width
    and no word that moved to the next line would fit on the previous one.
    """
    fragments: List[Fragment]
    height: int
    content_end: Tuple[float, float]
    min_width: float
    max_width: float


Measure = Callable[[str, bool], float]  # (text, bold) -> advance width
Piece = Tuple[str, Atom]  # the text of a word and the Atom it comes from


def _chunks(atoms: List[Atom]) -> Iterator[Optional[List[Piece]]]:
    """Yield None for a break opportunity (a space) and a list of pieces for every unbreakable run."""
    run: List[Piece] = []
    for atom in atoms:
        if atom.kind != KIND_TEXT:
            if run:
                yield run
                run = []
            yield [(atom.text, atom)]
            continue
        for part in _SPACES.split(atom.text):
            if not part:
                continue
            if part[0] == " ":
                if run:
                    yield run
                    run = []
                yield None
            else:
                run.append((part, atom))
    if run:
        yield run


class _Flow:
    """Greedy line filling: a run moves to the next line when it does not fit, a run wider than a line is cut by characters."""

    def __init__(self, width: float, line_height: int, measure: Measure):
        self._width = max(float(width), 1.0)
        self._base_height = line_height
        self._measure = measure
        self._space = measure(" ", False)
        self._fragments: List[Fragment] = []
        self._line_top = 0
        self._line_height = line_height
        self._x = 0.0
        self._has_space = False
        self._open_text = False  # the last fragment is a text fragment that a following word of the same style extends
        self._min_width = 0.0
        self._max_width = math.inf
        self._is_cut = False  # a word was cut by characters: the placement is valid for this width only

    def place(self, run: List[Piece]):
        widths = [atom.size[0] if atom.kind == KIND_EMOTICON else self._measure(text, atom.bold) for text, atom in run]
        total = sum(widths)
        if self._x > 0 and not self._fits(total):
            self._break_line(total)
        for (text, atom), width in zip(run, widths):
            if atom.kind == KIND_EMOTICON:
                self._add_emoticon(atom)
            elif total <= self._width + _EPSILON:
                self._add_text(atom, text, width)
            else:
                self._add_cut_text(atom, text)

    def finish(self) -> TextLayout:
        self._min_width = max(self._min_width, self._x - _EPSILON)
        if self._is_cut:
            self._min_width, self._max_width = self._width, math.nextafter(self._width, math.inf)
        return TextLayout(
            self._fragments, self._line_top + self._line_height, (self._x, self._line_top),
            self._min_width, self._max_width,
        )

    def mark_space(self):
        self._has_space = True

    def _fits(self, width: float) -> bool:
        gap = self._space if self._has_space else 0.0
        return self._x + gap + width <= self._width + _EPSILON

    def _break_line(self, moved_width: float = 0.0):
        """Start the next line; moved_width is the run that did not fit, the line would take it from that width on."""
        self._min_width = max(self._min_width, self._x - _EPSILON)
        if moved_width:
            gap = self._space if self._has_space else 0.0
            self._max_width = min(self._max_width, self._x + gap + moved_width - _EPSILON)
        self._line_top += self._line_height
        self._line_height = self._base_height
        self._x = 0.0
        self._has_space = False
        self._open_text = False

    def _add_text(self, atom: Atom, text: str, width: float):
        gap = self._space if self._has_space and self._x > 0 else 0.0
        if self._open_text and atom.kind == KIND_TEXT:
            last = self._fragments[-1]
            if last.role == atom.role and last.bold == atom.bold:
                last.text += (" " if gap else "") + text
                last.width += gap + width
                self._x += gap + width
                self._has_space = False
                return
        self._fragments.append(Fragment(
            atom.kind, text, atom.role, atom.bold, self._x + gap, self._line_top, width,
            self._base_height, atom.url, atom.is_media,
        ))
        self._x += gap + width
        self._has_space = False
        self._open_text = atom.kind == KIND_TEXT

    def _add_cut_text(self, atom: Atom, text: str):
        """Place a run wider than a line: as many characters as fit, then continue on the next line."""
        self._is_cut = True
        remaining = text
        while remaining:
            available = self._width - self._x - (self._space if self._has_space and self._x > 0 else 0.0)
            if self._x > 0 and available < self._measure(remaining[0], atom.bold):
                self._break_line()
                continue
            chunk = self._fit(remaining, available, atom.bold)
            self._add_text(atom, chunk, self._measure(chunk, atom.bold))
            remaining = remaining[len(chunk):]
            if remaining:
                self._break_line()

    def _fit(self, text: str, available: float, bold: bool) -> str:
        """The longest prefix that fits into the available width, at least one character."""
        low, high, best = 1, len(text), 1
        while low <= high:
            middle = (low + high) // 2
            if self._measure(text[:middle], bold) <= available + _EPSILON:
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        return text[:best]

    def _add_emoticon(self, atom: Atom):
        width, height = atom.size
        if self._x > 0 and not self._fits(width):
            self._break_line(width)
        gap = self._space if self._has_space and self._x > 0 else 0.0
        self._fragments.append(Fragment(
            KIND_EMOTICON, atom.text, atom.role, False, self._x + gap, self._line_top, width, height,
        ))
        self._line_height = max(self._line_height, height)
        self._x += gap + width
        self._has_space = False
        self._open_text = False


def layout_atoms(atoms: List[Atom], width: float, line_height: int, measure: Measure) -> TextLayout:
    """Wrap the atoms to the width: breaks only at spaces, a run wider than a line is cut by characters."""
    flow = _Flow(width, line_height, measure)
    for chunk in _chunks(atoms):
        if chunk is None:
            flow.mark_space()
        else:
            flow.place(chunk)
    return flow.finish()
