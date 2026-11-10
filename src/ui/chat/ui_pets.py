"""Transparent area above the input line where the enabled pets roam and can be picked up."""

import math

from PyQt6.QtCore import QElapsedTimer, QEvent, QPoint, QRect, QTimer, Qt
from PyQt6.QtGui import QPainter, QRegion
from PyQt6.QtWidgets import QWidget

from helpers.pets.animation import sprite_height
from helpers.pets.catalog import get_pet_kind, pet_counts, pet_pixel_size, pets_enabled, pets_stepped, predator_visit_ms
from helpers.pets.egg import Egg
from helpers.pets.meadow import Meadow
from helpers.pets.pet import Pet
from helpers.pets.relations import preys_on
from helpers.pets.throwable import Throwable


_TICK_MS = 33
_RESPAWN_SHARE = 0.5  # a carried-off pet is replaced after this share of the time between the visits of a predator
_MAXIMUM_STEP_MS = 100  # a stall (sleep, window drag) must not make pets jump across the line
_ANCHOR_EVENTS = (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Hide)


class PetOverlay(QWidget):
    """Area over everything down to the bottom of anchor, the strip kept free for the pets; the mask leaves only the pets themselves to the mouse."""

    def __init__(self, parent: QWidget, anchor: QWidget, config):
        super().__init__(parent)
        self._anchor = anchor
        self._config = config
        self._pets: list[Pet] = []
        self._eggs: list[Egg] = []
        self._meadow = Meadow()
        self._respawns: list[list] = []  # [kind, pixel size, ms left, edge it was carried off by] of every lost pet
        self._respawn_ms = 0
        self._grabbed: Throwable | None = None
        self._painted = QRegion()
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        anchor.installEventFilter(self)
        parent.installEventFilter(self)
        self.hide()
        self.reload()

    def shutdown(self) -> None:
        """Detach filters/parent so a deferred _place cannot mapTo after the room is gone."""
        self._timer.stop()
        if self._anchor is not None:
            self._anchor.removeEventFilter(self)
        parent = self.parentWidget()
        if parent is not None:
            parent.removeEventFilter(self)
        self.hide()
        self.setParent(None)
        self._anchor = None

    def reload(self) -> None:
        """Apply the pet options from the config, keeping pets that stay on."""
        if self._anchor is None:
            return
        counts = pet_counts(self._config) if pets_enabled(self._config) else {}
        spare: dict[tuple[str, int], list[Pet]] = {}
        for pet in self._pets:
            if pet.is_visible:
                spare.setdefault((pet.kind.key, pet.pixel_size), []).append(pet)
        line_width = round(self._anchor.width() * self.devicePixelRatioF())
        self._pets = []
        for key, count in counts.items():
            kind = get_pet_kind(key)
            if not kind:
                continue
            pixel_size = pet_pixel_size(self._config, kind)
            reusable = spare.get((key, pixel_size), [])
            self._pets.extend(reusable.pop() if reusable else Pet(kind, pixel_size, line_width) for _ in range(count))
        visit_ms = predator_visit_ms(self._config)
        self._respawn_ms = round(sum(visit_ms) / 2 * _RESPAWN_SHARE)
        for pet in self._pets:
            pet.stepped = pets_stepped(self._config)
            pet.away_ms = visit_ms
        self._respawns.clear()
        tallest = max((sprite_height(kind, pixel_size) for kind, pixel_size in {(pet.kind, pet.pixel_size) for pet in self._pets}), default=0)
        self._anchor.setFixedHeight(math.ceil(tallest / self.devicePixelRatioF()))
        self._anchor.setVisible(bool(self._pets))
        if not self._pets:
            self._eggs.clear()
        self._grabbed = None
        self._place()

    def eventFilter(self, watched, event):
        if watched is self._anchor and event.type() in _ANCHOR_EVENTS:
            self._place()
        elif watched is self.parentWidget() and event.type() == QEvent.Type.LayoutRequest:
            QTimer.singleShot(0, self._place)  # an ancestor of the anchor may have moved, which the anchor itself never reports
        return False

    def showEvent(self, event):
        super().showEvent(event)
        self._clock.restart()
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.scale(1 / self.devicePixelRatioF(), 1 / self.devicePixelRatioF())  # draw in device pixels
        area_height = self._device_size()[1]
        for body in self._bodies():
            painter.drawPixmap(body.position(area_height), body.pixmap)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point, area_height = self._device_point(event), self._device_size()[1]
        holdable = (body for body in reversed(self._bodies()) if body.can_be_held)
        self._grabbed = next((body for body in holdable if body.rect(area_height).contains(point)), None)
        if self._grabbed:
            self._grabbed.grab(point, area_height, event.timestamp())
        else:
            event.ignore()  # grass in the mask is not for the mouse; let the widget below take the click

    def mouseMoveEvent(self, event):
        if self._grabbed:
            self._grabbed.drag_to(self._device_point(event), self._device_size()[1], event.timestamp())

    def mouseReleaseEvent(self, event):
        if self._grabbed and event.button() == Qt.MouseButton.LeftButton:
            self._grabbed.release(event.timestamp())
            self._grabbed = None

    def _bodies(self) -> list[Throwable]:
        """Everything drawn on the line, back to front: grass, eggs, pets, so a laid egg lies behind its hen."""
        visible_pets = (pet for pet in self._pets if pet.is_visible)
        return [*self._meadow.grass, *self._eggs, *visible_pets]

    def _device_size(self) -> tuple[int, int]:
        ratio = self.devicePixelRatioF()
        return round(self.width() * ratio), round(self.height() * ratio)

    def _device_point(self, event) -> QPoint:
        ratio = self.devicePixelRatioF()
        return QPoint(round(event.position().x() * ratio), round(event.position().y() * ratio))

    def _logical_rect(self, rect: QRect) -> QRect:
        ratio = self.devicePixelRatioF()
        return QRect(
            math.floor(rect.x() / ratio), math.floor(rect.y() / ratio),
            math.ceil(rect.width() / ratio) + 1, math.ceil(rect.height() / ratio) + 1,
        )

    def _place(self) -> None:
        if self._anchor is None:
            return
        parent = self.parentWidget()
        if parent is None:
            return
        top_left = self._anchor.mapTo(parent, QPoint(0, 0))
        line_y = top_left.y() + self._anchor.height()
        if not self._pets or not self._anchor.isVisible() or line_y <= 0:
            self.hide()
            return
        self.setGeometry(top_left.x(), 0, self._anchor.width(), line_y)
        self.show()
        self.raise_()  # panes re-adopted by the window (room tabs opened or closed) land above the pets
        self._refresh_region()

    def _refresh_region(self) -> None:
        """Limit mouse input to the pets and repaint only where they were and are."""
        area_height = self._device_size()[1]
        region = QRegion()
        for body in self._bodies():
            region = region.united(self._logical_rect(body.rect(area_height)))
        self.setMask(region)
        self.update(self._painted.united(region))
        self._painted = region

    def _safer_edge_is_right(self, kind, exit_right: bool, line_width: int) -> bool:
        """Whether a newcomer should come in at the right edge: the one farthest from the predators in sight, else the one no raider left by."""
        predators = [pet.center_x for pet in self._pets if pet.is_visible and preys_on(pet.kind, kind)]
        if not predators:
            return not exit_right
        return min(line_width - x for x in predators) > min(predators)

    def _replace_carried_off(self, step_ms: int, line_width: int) -> None:
        """Drop the pets carried off the line and let new ones arrive at an edge after a while."""
        for pet in self._pets:
            if pet.is_gone:
                self._respawns.append([pet.kind, pet.pixel_size, self._respawn_ms, pet.exit_right])
        self._pets = [pet for pet in self._pets if not pet.is_gone]
        for respawn in self._respawns:
            respawn[2] -= step_ms
        for kind, pixel_size, _, exit_right in [respawn for respawn in self._respawns if respawn[2] <= 0]:
            newcomer = Pet(kind, pixel_size, line_width)
            newcomer.stepped = pets_stepped(self._config)
            newcomer.enter(line_width, self._safer_edge_is_right(kind, exit_right, line_width))
            self._pets.append(newcomer)
        self._respawns = [respawn for respawn in self._respawns if respawn[2] > 0]

    def _tick(self) -> None:
        step_ms = min(self._clock.restart(), _MAXIMUM_STEP_MS)
        line_width, area_height = self._device_size()
        visible = [pet for pet in self._pets if pet.is_visible]
        self._meadow.update(step_ms, visible, self._eggs, line_width, area_height)
        foods = [*self._eggs, *self._meadow.grass]
        for pet in self._pets:
            if pet.is_visible:
                pet.look_for_food(foods, visible, step_ms)
                pet.interact(visible, step_ms)
            pet.update(step_ms, line_width, area_height)
            egg = pet.take_egg()
            if egg:
                self._eggs.append(egg)
        self._replace_carried_off(step_ms, line_width)
        for egg in self._eggs:
            egg.update(step_ms, line_width, area_height)
        self._eggs = [egg for egg in self._eggs if not egg.expired]
        self._refresh_region()
