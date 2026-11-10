"""SettingsWidget: pets master switch, per-kind pet counts and per-species pixel sizes."""

from itertools import groupby

from PyQt6.QtCore import pyqtSignal, QRect, Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from components.button import create_icon_button
from helpers.fonts.fonts import FontType, get_font
from helpers.hold_repeater import HoldRepeater
from helpers.pets.catalog import (
    list_pet_kinds,
    MAXIMUM_PET_COUNT,
    DEFAULT_SIZE_MULTIPLIER,
    MAXIMUM_SIZE_MULTIPLIER,
    PREDATOR_VISIT_SECONDS,
    pet_counts,
    pet_size_multiplier,
    pets_enabled,
    pets_stepped,
    predator_visit_seconds,
)
from helpers.pets.relations import PREDATOR_SPECIES
from helpers.translate import tr
from ui.dialogs.pets_guide_dialog import PetsGuideDialog


_TILE_COLUMNS = 8
_TILE_SIZE = 40
_BADGE_HEIGHT = 14
_BADGE_PADDING = 6
_BADGE_FONT_PIXELS = 10
_BADGE_RADIUS = 4
_HINT_FONT_SCALE = 0.85


class _PetTile(QLabel):
    """Icon of one pet kind: left click adds a pet, right click removes one; holding the button repeats."""

    added = pyqtSignal()
    removed = pyqtSignal()

    def __init__(self, icon: QPixmap, tooltip: str):
        super().__init__()
        self._count = 0
        self._repeaters = {
            Qt.MouseButton.LeftButton: HoldRepeater(self.added.emit, self),
            Qt.MouseButton.RightButton: HoldRepeater(self.removed.emit, self),
        }
        self.setFixedSize(_TILE_SIZE, _TILE_SIZE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setPixmap(icon)

    def set_count(self, count: int) -> None:
        """Show how many pets of the kind are enabled."""
        self._count = count
        self.update()

    def mousePressEvent(self, event):
        if event.button() in self._repeaters:
            self._repeaters[event.button()].press()

    def mouseReleaseEvent(self, event):
        if event.button() in self._repeaters:
            self._repeaters[event.button()].release()

    def hideEvent(self, event):
        for repeater in self._repeaters.values():
            repeater.release()
        super().hideEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._count < 1:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(_BADGE_FONT_PIXELS)
        painter.setFont(font)
        text = str(self._count)
        width = max(_BADGE_HEIGHT, painter.fontMetrics().horizontalAdvance(text) + _BADGE_PADDING)
        badge = QRect(self.width() - width, self.height() - _BADGE_HEIGHT, width, _BADGE_HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().highlight())
        painter.drawRoundedRect(badge, _BADGE_RADIUS, _BADGE_RADIUS)
        painter.setPen(self.palette().highlightedText().color())
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)


class SettingsPetsMixin:
    """SettingsWidget: pets master switch, per-kind pet counts and per-species pixel sizes."""

    def build_pets_section(self):
        section = self.create_section(tr("🐾 Pets", "🐾 Питомцы"))
        self.pets_checkbox = self.add_checkbox(
            section, tr("Pets walk above the input line", "Питомцы гуляют над строкой ввода"), self._on_pets_toggled
        )
        self.pets_stepped_checkbox = self.add_checkbox(
            section, tr("Move in steps like real paws", "Двигаться шагами, как на настоящих лапах"), self._on_pets_stepped_toggled
        )
        hint = tr(
            "Left click: add a pet · Right click: remove one · Hold to repeat",
            "ЛКМ: добавить питомца · ПКМ: убрать · удерживайте для повтора",
        )
        hint_label = QLabel(hint)
        hint_font = get_font(FontType.UI)
        hint_font.setPointSizeF(hint_font.pointSizeF() * _HINT_FONT_SCALE)
        hint_label.setFont(hint_font)
        hint_label.setStyleSheet("color: palette(placeholder-text);")
        guide_tooltip = tr("How the pets behave", "Как ведут себя питомцы")
        guide_button = create_icon_button(self.icons_path, "line/information-line.svg", guide_tooltip, size_type="small", config=self.config)
        guide_button.clicked.connect(lambda: PetsGuideDialog(self).exec())
        hint_layout = QHBoxLayout()
        hint_layout.addWidget(hint_label, 1)
        hint_layout.addWidget(guide_button)
        section.addLayout(hint_layout)
        self.register_tr(hint_label.setText, hint)
        self.register_tr(guide_button.setToolTip, guide_tooltip)
        tiles_widget = QWidget()
        grid = QGridLayout(tiles_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._pet_tiles = {}
        self._pet_species_kinds = {}
        row = 0
        for species, species_kinds in groupby(list_pet_kinds(), key=lambda kind: kind.species):
            self._pet_species_kinds[species] = species_kinds = list(species_kinds)
            for index, kind in enumerate(species_kinds):
                tile = _PetTile(QPixmap(str(kind.icon_path)), kind.title)
                tile.added.connect(lambda key=kind.key: self._on_pet_added(key))
                tile.removed.connect(lambda key=kind.key: self._on_pet_removed(key))
                grid.addWidget(tile, row + index // _TILE_COLUMNS, index % _TILE_COLUMNS)
                self._pet_tiles[kind.key] = tile
            row += index // _TILE_COLUMNS + 1
        section.addWidget(tiles_widget)
        size_layout = QVBoxLayout()
        size_layout.setSpacing(self.element_spacing())
        section.addLayout(size_layout)
        self.pet_size_spins = {}
        for species in self._pet_species_kinds:
            spin = self.add_slider_spin_row(
                size_layout, species.title(), 1, MAXIMUM_SIZE_MULTIPLIER,
                lambda value, species=species: self._on_pet_size_changed(species, value), default=DEFAULT_SIZE_MULTIPLIER,
            )
            spin.setPrefix("×")
            self.pet_size_spins[species] = spin
        labels = [spin.parentWidget().findChild(QLabel) for spin in self.pet_size_spins.values()]
        label_width = max(label.sizeHint().width() for label in labels)
        for label in labels:
            label.setFixedWidth(label_width)
        default, minimum, maximum = PREDATOR_VISIT_SECONDS
        self.pet_visit_spin = self.add_slider_spin_row(
            section, tr("A predator comes every, seconds", "Хищник приходит раз в, сек"), minimum, maximum,
            self._on_predator_visit_changed, default=default,
        )

    def refresh_pets(self):
        self.pets_checkbox.setChecked(pets_enabled(self.config))
        self.pets_stepped_checkbox.setChecked(pets_stepped(self.config))
        counts = pet_counts(self.config)
        for key, tile in self._pet_tiles.items():
            tile.set_count(counts.get(key, 0))
        for species, spin in self.pet_size_spins.items():
            spin.parentWidget().setVisible(any(kind.key in counts for kind in self._pet_species_kinds[species]))
            multiplier = pet_size_multiplier(self.config, species)
            spin.setValue(multiplier)
            spin.linked_slider.setValue(multiplier)
        self.pet_visit_spin.parentWidget().setVisible(any(kind.species in PREDATOR_SPECIES and kind.key in counts for kind in list_pet_kinds()))
        seconds = predator_visit_seconds(self.config)
        self.pet_visit_spin.setValue(seconds)
        self.pet_visit_spin.linked_slider.setValue(seconds)

    def _on_pets_toggled(self, checked: bool):
        self.config.set("ui", "pets", "enabled", value=checked)
        self.pets_changed.emit()

    def _on_pets_stepped_toggled(self, checked: bool):
        self.config.set("ui", "pets", "stepped", value=checked)
        self.pets_changed.emit()

    def _on_predator_visit_changed(self, value: int):
        self.config.set("ui", "pets", "predator_visit", value=int(value))
        self.pets_changed.emit()

    def _on_pet_size_changed(self, species: str, value: int):
        sizes = dict(self.config.get("ui", "pets", "sizes") or {})
        sizes[species] = int(value)
        self.config.set("ui", "pets", "sizes", value=sizes)
        self.pets_changed.emit()

    def _on_pet_added(self, key: str):
        self._change_pet_count(key, 1)

    def _on_pet_removed(self, key: str):
        self._change_pet_count(key, -1)

    def _change_pet_count(self, key: str, step: int):
        counts = pet_counts(self.config)
        count = max(0, min(counts.get(key, 0) + step, MAXIMUM_PET_COUNT))
        if count == counts.get(key, 0):
            return
        if count:
            counts[key] = count
        else:
            counts.pop(key, None)
        self.config.set("ui", "pets", "counts", value=counts)
        self.refresh_pets()
        self.pets_changed.emit()
