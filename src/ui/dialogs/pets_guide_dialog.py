"""Guide to the pets: the role of every pet in the food chain and what happens depending on who is on the line."""

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from helpers.translate import tr


_DIALOG_SIZE = (560, 640)

# (title, text) pairs; the text is HTML, English first and Russian second
_SECTIONS = (
    (
        ("Food chain", "Пищевая цепочка"),
        (
            "<p>grass → chicken → egg → rat<br>fox hunts chickens · dog chases foxes away</p>"
            "<p>Grass and eggs are not pets: they are food on the strip. Snails and Clippy live on their own.</p>",
            "<p>трава → курица → яйцо → крыса<br>лиса охотится на кур · собака прогоняет лис</p>"
            "<p>Трава и яйца — не питомцы, а еда на полосе. Улитки и Скрепыш живут сами по себе.</p>",
        ),
    ),
    (
        ("Chicken", "Курица"),
        (
            "<p>Pecks at grass (a clump gives food for an egg) and lays eggs while walking. "
            "Runs from a fox that is hunting and will not run for food past one.</p>",
            "<p>Клюёт траву (одного пучка хватает на яйцо) и несёт яйца на ходу. "
            "Убегает от охотящейся лисы и не побежит за кормом мимо неё.</p>",
        ),
    ),
    (
        ("Fox", "Лиса"),
        (
            "<p>A wild predator that comes from around the corner. It stalks the nearest chicken, pounces and carries it off; "
            "the chicken is replaced later. With no chickens on the strip it explores the territory, may lie down "
            "(only if there is no dog), and leaves through a random edge. It runs away from dogs.</p>",
            "<p>Дикий хищник, приходит из-за угла. Подкрадывается к ближайшей курице, прыгает и уносит её; "
            "позже курица появляется снова. Если кур на полосе нет, лиса изучает территорию, может прилечь "
            "(только если нет собаки) и уходит через случайный край. От собак убегает.</p>",
        ),
    ),
    (
        ("Dog", "Собака"),
        (
            "<p>A guard. It notices a fox only when the fox is in front of it, then runs at it and barks now and then. "
            "On catching the fox it bites, and the fox drops its prey and flees. The rest of the time it mostly lies, "
            "stands or walks; it runs only to chase a fox. It does not touch anyone else.</p>",
            "<p>Сторож. Замечает лису, только если она перед ним, затем бежит к ней и время от времени лает. "
            "Догнав лису, кусает её, и та бросает добычу и убегает. Остальное время в основном лежит, "
            "стоит или ходит; бегает только за лисой. Остальных не трогает.</p>",
        ),
    ),
    (
        ("Rat", "Крыса"),
        (
            "<p>A scavenger. Runs to a broken egg and eats it; otherwise it just wanders. Nobody bothers it and it bothers nobody.</p>",
            "<p>Падальщик. Бежит к разбитому яйцу и съедает его, в остальное время просто гуляет. Её никто не трогает, и она никого.</p>",
        ),
    ),
    (
        ("Snail and Clippy", "Улитка и Скрепыш"),
        (
            "<p>Neutral. They wander, rest and react to the mouse; they are in nobody's food chain.</p>",
            "<p>Нейтральные. Гуляют, отдыхают и реагируют на мышь; ни в чьей пищевой цепочке не участвуют.</p>",
        ),
    ),
    (
        ("Grass and eggs", "Трава и яйца"),
        (
            "<p>Grass grows only while there is a chicken. Eggs roll, break on a hard landing or when old, and evaporate "
            "after a while. Only rats eat eggs, and only broken ones.</p>",
            "<p>Трава растёт, только пока есть курица. Яйца катятся, разбиваются при жёстком падении или от старости "
            "и через некоторое время испаряются. Едят яйца только крысы, и только разбитые.</p>",
        ),
    ),
    (
        ("Who is on the strip", "Кто на полосе"),
        (
            "<ul>"
            "<li>No chickens: foxes have nothing to hunt and just explore, then leave.</li>"
            "<li>No dogs: foxes may lie down; nobody barks.</li>"
            "<li>No foxes: dogs just roam and rest, and chickens are never in danger.</li>"
            "<li>No rats: eggs just break and evaporate.</li>"
            "</ul>",
            "<ul>"
            "<li>Нет кур: лисам не на кого охотиться, они гуляют и уходят.</li>"
            "<li>Нет собак: лисы могут лечь; никто не лает.</li>"
            "<li>Нет лис: собаки просто гуляют и отдыхают, а курам ничего не грозит.</li>"
            "<li>Нет крыс: яйца просто разбиваются и испаряются.</li>"
            "</ul>",
        ),
    ),
    (
        ("Mouse", "Мышь"),
        (
            "<p>Click a pet to scare it; drag to throw it. Eggs can be picked up and rolled.</p>",
            "<p>Клик по питомцу пугает его; перетащите, чтобы бросить. Яйца можно поднимать и катать.</p>",
        ),
    ),
)


def _guide_html() -> str:
    return "".join(f"<h3>{tr(*title)}</h3>{tr(*text)}" for title, text in _SECTIONS)


class PetsGuideDialog(QDialog):
    """Read-only guide to the behavior of every pet."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Pets guide", "Гайд по питомцам"))
        self.resize(*_DIALOG_SIZE)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setHtml(_guide_html())
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
