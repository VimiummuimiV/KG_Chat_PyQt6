"""Guide to the pets: the role of every pet in the food chain and what happens depending on who is on the line."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from helpers.pets.catalog import list_pet_kinds
from helpers.translate import tr


_SCREEN_SHARE = 0.9
_MAX_WIDTH = 1500
_COLUMNS = 3
_ICON_SIZE = 32

# markdown-like palette: headings, text, muted text, links, green and red accents, code spans
_COLORS = {
    "dark": dict(background="#0d1117", card="#161b22", border="#30363d", heading="#e6edf3", text="#c9d1d9", muted="#8b949e",
                 accent="#58a6ff", positive="#3fb950", negative="#f85149", code_background="#343942", code_text="#e6edf3"),
    "light": dict(background="#ffffff", card="#f6f8fa", border="#d0d7de", heading="#1f2328", text="#1f2328", muted="#656d76",
                  accent="#0969da", positive="#1a7f37", negative="#cf222e", code_background="#e6eaef", code_text="#1f2328"),
}

# a chain is a list of items: a species key shows the pet icon, a pair of texts (English, Russian) shows words
_ARROW = ("→", "→")
_CHAINS = (
    (("grass", "трава"), _ARROW, "chicken", _ARROW, ("egg", "яйцо"), _ARROW, "rat"),
    ("fox", ("hunts", "охотится на"), "chicken", ("·", "·"), "dog", ("chases away", "прогоняет"), "fox"),
)

# row kinds: "eats" and "fears" get the green and the red label, "does" the accent one
_PET_CARDS = (
    ("chicken", ("Chicken", "Курица"), ("herbivore, prey of foxes, lays eggs", "травоядная, добыча лисы, несёт яйца"), (
        ("eats", ("Eats", "Ест"), ("grass", "траву")),
        ("fears", ("Afraid of", "Боится"), ("a hunting fox", "охотящейся лисы")),
        ("does", ("Does", "Делает"), ("pecks a clump of grass, which is enough for an egg, and lays eggs while walking: it sits down, lays and walks on; "
                                      "never runs for food past a fox",
                                      "клюёт пучок травы, которого хватает на яйцо, и несёт яйца на ходу: присядет, снесёт и пойдёт дальше; "
                                      "не побежит за кормом мимо лисы")),
    )),
    ("fox", ("Fox", "Лиса"), ("wild predator from around the corner", "дикий хищник из-за угла"), (
        ("eats", ("Eats", "Ест"), ("chickens", "кур")),
        ("fears", ("Afraid of", "Боится"), ("dogs", "собак")),
        ("does", ("Does", "Делает"), ("stalks the nearest chicken, pounces and carries it off, turning away from a dog in its path; the chicken is replaced later. "
                                      "With no chickens it explores the strip, lies down only if there is no dog, and leaves by a random edge",
                                      "подкрадывается к ближайшей курице, прыгает и уносит её, обходя собаку на пути; позже курица появляется снова. "
                                      "Без кур гуляет по полосе, ложится, только если нет собаки, и уходит через случайный край")),
    )),
    ("dog", ("Dog", "Собака"), ("guard against foxes", "сторож от лис"), (
        ("eats", ("Eats", "Ест"), ("nothing", "ничего")),
        ("fears", ("Afraid of", "Боится"), ("nobody", "никого")),
        ("does", ("Does", "Делает"), ("sees a fox in front of it from afar and hears one sneaking up from behind when it is near (a pack of foxes is heard from farther), then runs at it and barks in bursts. "
                                      "On catching it, the dog bites and the fox drops its prey and flees. "
                                      "Otherwise lies, stands or walks, and runs only after a fox",
                                      "видит лису перед собой издалека, а подкрадывающуюся сзади слышит вблизи (стаю лис слышно дальше), затем бежит к ней и лает сериями. "
                                      "Укушенная лиса бросает добычу и убегает. "
                                      "В остальное время лежит, стоит или ходит, а бегает только за лисой")),
    )),
    ("rat", ("Rat", "Крыса"), ("scavenger", "падальщик"), (
        ("eats", ("Eats", "Ест"), ("broken eggs", "разбитые яйца")),
        ("fears", ("Afraid of", "Боится"), ("nobody", "никого")),
        ("does", ("Does", "Делает"), ("runs to a broken egg it sees nearby and eats it; otherwise just wanders. Nobody bothers it",
                                      "бежит к разбитому яйцу, которое видит рядом, и ест его, а так просто гуляет. Её никто не трогает")),
    )),
    ("snail", ("Snail and Clippy", "Улитка и Скрепыш"), ("neutral, live on their own", "нейтральные, живут сами по себе"), (
        ("eats", ("Eats", "Едят"), ("nothing", "ничего")),
        ("fears", ("Afraid of", "Боятся"), ("nobody", "никого")),
        ("does", ("Do", "Делают"), ("wander, rest and react to the mouse; they are in nobody's food chain",
                                    "гуляют, отдыхают и реагируют на мышь; ни в чьей пищевой цепочке не участвуют")),
    )),
    (None, ("Grass and eggs", "Трава и яйца"), ("food, not pets", "еда, а не питомцы"), (
        ("does", ("Grass", "Трава"), ("grows only while there is a chicken, up to two clumps per chicken",
                                      "растёт, только пока есть курица, не больше двух пучков на курицу")),
        ("does", ("Eggs", "Яйца"), ("roll, break on a hard landing or with age, and evaporate; "
                                    "only rats eat them, and only broken ones",
                                    "катятся, разбиваются при жёстком падении или от старости и испаряются; "
                                    "их едят только крысы, и только разбитые")),
    )),
)

_WHO_IS_ON_THE_STRIP = (
    (("No chickens", "Нет кур"), ("foxes have nothing to hunt: they explore, then leave", "лисам некого ловить: они гуляют и уходят")),
    (("No dogs", "Нет собак"), ("foxes may lie down; nobody barks", "лисы могут лечь; никто не лает")),
    (("No foxes", "Нет лис"), ("dogs just roam and rest; chickens are safe", "собаки просто гуляют и отдыхают; курам ничего не грозит")),
    (("No rats", "Нет крыс"), ("eggs just break and evaporate", "яйца просто разбиваются и испаряются")),
)

_MOUSE = (
    (("On a pet", "По питомцу"), ("click to scare it, drag to throw it", "клик пугает, перетаскивание бросает")),
    (("Thrown pet", "Брошенный питомец"), (
        "a pixel board follows the cursor while the pet is above it, until the mouse picks up something else; each bounce adds to its badge",
        "за курсором следует пиксельная доска, пока питомец выше, и до тех пор, пока мышь не возьмёт что-то другое; отскок прибавляет к бейджу",
    )),
    (("On an egg", "По яйцу"), ("pick it up and roll it", "можно поднять и покатать")),
    (("In settings", "В настройках"), ("left click adds a pet, right click removes one, hold to repeat",
                                       "левый клик добавляет питомца, правый убирает, удержание повторяет")),
)


class PetsGuideDialog(QDialog):
    """Read-only guide to the behavior of every pet; closes with the window button, Esc or F1 like the help panel."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._colors = _COLORS.get(config.get("ui", "theme") or "dark", _COLORS["dark"])
        self._icons = {}
        for kind in list_pet_kinds():
            self._icons.setdefault(kind.species, kind.icon_path)
        self.setWindowTitle(tr("Pets guide", "Гайд по питомцам"))
        self.setStyleSheet(self._stylesheet())
        grid = QGridLayout(self)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setSpacing(12)
        grid.addWidget(self._chain_card(), 0, 0, 1, _COLUMNS)
        cards = [self._pet_card(*card) for card in _PET_CARDS]
        cards += [self._list_card(tr("Who is on the strip", "Кто на полосе"), _WHO_IS_ON_THE_STRIP, span=2),
                  self._list_card(tr("Mouse and settings", "Мышь и настройки"), _MOUSE)]
        row, column = 1, 0
        for card, span in cards:
            grid.addWidget(card, row, column, 1, span)
            column += span
            if column >= _COLUMNS:
                row, column = row + 1, 0
        for index in range(1, row + (1 if column else 0)):
            grid.setRowStretch(index, 1)
        self._fit_to_screen()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_F1, Qt.Key.Key_Escape):
            self.reject()
        else:
            super().keyPressEvent(event)

    def _fit_to_screen(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        width, height = min(round(screen.width() * _SCREEN_SHARE), _MAX_WIDTH), round(screen.height() * _SCREEN_SHARE)
        self.resize(width, height)
        self.move(screen.x() + (screen.width() - width) // 2, screen.y() + (screen.height() - height) // 2)

    def _stylesheet(self) -> str:
        colors = self._colors
        return (
            f"QDialog {{ background-color: {colors['background']}; }}"
            f"QFrame#card {{ background-color: {colors['card']}; border: 1px solid {colors['border']}; border-radius: 8px; }}"
            f"QFrame#rule {{ background-color: {colors['border']}; border: none; }}"
            f"QLabel {{ background: transparent; color: {colors['text']}; font-size: 14px; }}"
            f"QLabel#title {{ color: {colors['heading']}; font-size: 18px; font-weight: bold; }}"
        )

    def _code(self, text: str) -> str:
        colors = self._colors
        return (f"<span style=\"background-color: {colors['code_background']}; color: {colors['code_text']}; "
                f"font-family: Consolas, monospace;\">&nbsp;{text}&nbsp;</span>")

    def _label_html(self, color_key: str, label: str, text: str) -> str:
        return f"<b style=\"color: {self._colors[color_key]};\">{label}</b> {text}"

    def _icon(self, species: str, size: int) -> QLabel:
        label = QLabel()
        label.setPixmap(QPixmap(str(self._icons[species])).scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        return label

    def _card(self, title: str, species: str | None, body_html: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        if species in self._icons:
            header.addWidget(self._icon(species, _ICON_SIZE))
        title_label = QLabel(title)
        title_label.setObjectName("title")
        header.addWidget(title_label, 1)
        layout.addLayout(header)
        layout.addWidget(self._rule())
        body = QLabel(body_html)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(body, 1)
        return card

    def _rule(self) -> QFrame:
        rule = QFrame()
        rule.setObjectName("rule")
        rule.setFixedHeight(1)
        return rule

    def _pet_card(self, species, title, role, rows) -> tuple[QFrame, int]:
        colors = {"eats": "positive", "fears": "negative", "does": "accent"}
        lines = [f"<i style=\"color: {self._colors['muted']};\">{tr(*role)}</i>"]
        lines += [self._label_html(colors[kind], tr(*label), tr(*text)) for kind, label, text in rows]
        return self._card(tr(*title), species, "<br><br>".join(lines)), 1

    def _list_card(self, title: str, rows, span: int = 1) -> tuple[QFrame, int]:
        lines = [f"{self._code(tr(*label))} {tr(*text)}" for label, text in rows]
        return self._card(title, None, "<br><br>".join(lines)), span

    def _chain_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        title_label = QLabel(tr("Food chain", "Пищевая цепочка"))
        title_label.setObjectName("title")
        layout.addWidget(title_label)
        layout.addWidget(self._rule())
        for chain in _CHAINS:
            row = QHBoxLayout()
            row.setSpacing(10)
            for item in chain:
                if isinstance(item, str):
                    row.addWidget(self._icon(item, _ICON_SIZE))
                else:
                    word = QLabel(tr(*item))
                    word.setStyleSheet(f"font-size: 16px; color: {self._colors['accent']};")
                    row.addWidget(word)
            row.addStretch(1)
            layout.addLayout(row)
        return card
