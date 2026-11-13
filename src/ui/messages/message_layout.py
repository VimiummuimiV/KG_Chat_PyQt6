"""Word-wrap layout of a message body: one pass gives both the height and the positions the painter draws."""

import re
from dataclasses import dataclass, replace
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


@dataclass(frozen=True)
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
    """Placed fragments with the total height and the spot right after the last one."""
    fragments: List[Fragment]
    height: int
    content_end: Tuple[float, float]


Measure = Callable[[str, bool], float]  # (text, bold) -> advance width


def _chunks(atoms: List[Atom]) -> Iterator[Optional[List[Atom]]]:
    """Yield None for a break opportunity (a space) and a list of atoms for every unbreakable run."""
    run: List[Atom] = []
    for atom in atoms:
        if atom.kind != KIND_TEXT:
            if run:
                yield run
                run = []
            yield [atom]
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
                run.append(replace(atom, text=part))
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
        self._open_text = False  # the last fragment is a text fragment that a following word of the same role extends

    def place(self, run: List[Atom]):
        widths = [self._measure(atom.text, atom.bold) if atom.kind != KIND_EMOTICON else atom.size[0]
                  for atom in run]
        total = sum(widths)
        if self._x > 0 and not self._fits(total):
            self._break_line()
        for atom, width in zip(run, widths):
            if atom.kind == KIND_EMOTICON:
                self._add_emoticon(atom)
            elif total <= self._width + _EPSILON:
                self._add_text(atom, width)
            else:
                self._add_cut_text(atom)

    def finish(self) -> TextLayout:
        return TextLayout(self._fragments, self._line_top + self._line_height, (self._x, self._line_top))

    def mark_space(self):
        self._has_space = True

    def _fits(self, width: float) -> bool:
        gap = self._space if self._has_space else 0.0
        return self._x + gap + width <= self._width + _EPSILON

    def _break_line(self):
        self._line_top += self._line_height
        self._line_height = self._base_height
        self._x = 0.0
        self._has_space = False
        self._open_text = False

    def _add_text(self, atom: Atom, width: float):
        gap = self._space if self._has_space and self._x > 0 else 0.0
        if self._open_text and atom.kind == KIND_TEXT and self._fragments[-1].role == atom.role and self._fragments[-1].bold == atom.bold:
            last = self._fragments[-1]
            text = last.text + (" " if gap else "") + atom.text
            self._fragments[-1] = replace(last, text=text, width=last.width + gap + width)
        else:
            self._fragments.append(Fragment(
                atom.kind, atom.text, atom.role, atom.bold, self._x + gap, self._line_top, width,
                self._base_height, atom.url, atom.is_media,
            ))
        self._x += gap + width
        self._has_space = False
        self._open_text = atom.kind == KIND_TEXT

    def _add_cut_text(self, atom: Atom):
        """Place a run wider than a line: as many characters as fit, then continue on the next line."""
        bold = atom.bold
        remaining = atom.text
        while remaining:
            available = self._width - self._x - (self._space if self._has_space and self._x > 0 else 0.0)
            if self._x > 0 and available < self._measure(remaining[0], bold):
                self._break_line()
                continue
            chunk = self._fit(remaining, available, bold)
            self._add_text(replace(atom, text=chunk), self._measure(chunk, bold))
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
            self._break_line()
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
