"""Transparent area above the input line where the enabled pets roam and can be picked up."""

import math

from PyQt6.QtCore import QElapsedTimer, QEvent, QPoint, QRect, QTimer, Qt
from PyQt6.QtGui import QColor, QCursor, QPainter, QPixmap, QRegion
from PyQt6.QtWidgets import QWidget

from components.badge import counter_pixmap
from components.button import get_accent_color
from components.fade import WidgetFader
from helpers.pets.animation import sprite_height
from helpers.pets.bounce import CollisionBoard, CursorMotion
from helpers.pets.catalog import (
    action_frame_rate,
    get_pet_kind,
    ground_frame_rate,
    pet_counts,
    pet_pixel_size,
    pets_enabled,
    pets_hide_messages,
    pets_stepped,
    predator_visit_ms,
)
from helpers.pets.egg import Egg
from helpers.pets.meadow import Meadow
from helpers.pets.pet import Pet
from helpers.pets.relations import preys_on
from helpers.pets.throwable import Throwable


_MILLISECONDS = 1000
_MESSAGES_FADE_OUT_MS = 250
_MESSAGES_FADE_IN_MS = 450
_MESSAGES_HIDDEN_OPACITY = 0.0
_RESPAWN_SHARE = 0.5  # a carried-off pet is replaced after this share of the time between the visits of a predator
_MAXIMUM_STEP_MS = 100  # a stall (sleep, window drag) must not make pets jump across the line
_BADGE_FONT_SIZE = 10
_BADGE_GAP = 1  # logical pixels between the badge and the top of the pet
_BOARD_SHADE = 150  # percent; the lower row of the board is the accent color darkened by this much
_ANCHOR_EVENTS = (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Hide)


def _tick_ms(frame_rate: int) -> int:
    return round(_MILLISECONDS / frame_rate)


class PetOverlay(QWidget):
    """Area over everything down to the bottom of anchor, the strip kept free for the pets; the mask leaves only the pets themselves to the mouse."""

    def __init__(self, parent: QWidget, anchor: QWidget, messages: QWidget, config):
        super().__init__(parent)
        self._anchor = anchor
        self._config = config
        self._messages_fader = WidgetFader(messages)
        self._is_hiding_messages = False  # the option is on
        self._are_messages_hidden = False
        self._pets: list[Pet] = []
        self._eggs: list[Egg] = []
        self._meadow = Meadow()
        self._respawns: list[list] = []  # [kind, pixel size, ms left, edge it was carried off by] of every lost pet
        self._respawn_ms = 0
        self._grabbed: Throwable | None = None
        self._cursor_point: QPoint | None = None  # where the cursor was on the previous tick
        self._board = CollisionBoard.for_pets(())
        self._painted = QRegion()
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)  # the coarse default is uneven
        self._ground_tick_ms = _tick_ms(ground_frame_rate(config))
        self._action_tick_ms = _tick_ms(action_frame_rate(config))
        self._timer.timeout.connect(self._tick)
        anchor.installEventFilter(self)
        parent.installEventFilter(self)
        self.hide()
        self.reload()

    def shutdown(self) -> None:
        """Detach filters/parent so a deferred _place cannot mapTo after the room is gone."""
        self._timer.stop()
        self._show_messages()
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
        self._ground_tick_ms = _tick_ms(ground_frame_rate(self._config))
        self._action_tick_ms = _tick_ms(action_frame_rate(self._config))
        self._adjust_tick_rate()
        self._is_hiding_messages = pets_hide_messages(self._config)
        self._grabbed = None
        self._cursor_point = None
        self._board = CollisionBoard.for_pets(self._pets)
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
        self._show_messages()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.scale(1 / self.devicePixelRatioF(), 1 / self.devicePixelRatioF())  # draw in device pixels
        area_height = self._device_size()[1]
        for body in self._bodies():
            painter.drawPixmap(body.position(area_height), body.pixmap)
        board = self._board_rect()
        if board:
            self._paint_board(painter, board)
        for pixmap, position in self._badges():
            painter.drawPixmap(position, pixmap)

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
            self._refresh_region()  # the held body follows the mouse at once, not at the next tick

    def mouseReleaseEvent(self, event):
        if self._grabbed and event.button() == Qt.MouseButton.LeftButton:
            self._grabbed.release(event.timestamp())
            self._grabbed = None

    def _bodies(self) -> list[Throwable]:
        """Everything drawn on the line, back to front: grass, eggs, pets, so a laid egg lies behind its hen."""
        visible_pets = (pet for pet in self._pets if pet.is_visible)
        return [*self._meadow.grass, *self._eggs, *visible_pets]

    def _board_rect(self) -> QRect | None:
        """Return the board at the cursor while a thrown pet is above it, otherwise None."""
        if self._cursor_point is None:
            return None
        board, area_height = self._board.at(self._cursor_point), self._device_size()[1]
        is_needed = any(pet.is_visible and pet.is_over(board, area_height) for pet in self._pets)
        return board if is_needed else None

    def _paint_board(self, painter: QPainter, board: QRect) -> None:
        """Draw the board: a light top row with notched ends over a darker full bottom row."""
        cell = self._board.cell
        light = QColor(get_accent_color())
        painter.fillRect(board.adjusted(cell, 0, -cell, -cell), light)
        painter.fillRect(board.adjusted(0, cell, 0, 0), light.darker(_BOARD_SHADE))

    def _badges(self) -> list[tuple[QPixmap, QPoint]]:
        """Return the bounce counters with their top left corners, each centered above its pet."""
        line_width, area_height = self._device_size()
        badges = []
        for pet in self._pets:
            if not (pet.is_visible and pet.badge_text):
                continue
            pixmap = counter_pixmap(pet.badge_text, _BADGE_FONT_SIZE, self.devicePixelRatioF())
            body = pet.rect(area_height)
            gap = round(_BADGE_GAP * self.devicePixelRatioF())
            x = min(body.center().x() - pixmap.width() // 2, line_width - pixmap.width())
            badges.append((pixmap, QPoint(max(0, x), max(0, body.top() - pixmap.height() - gap))))
        return badges

    def _cursor_motion(self, step_ms: int) -> CursorMotion:
        """Return the cursor over the last tick in device pixels, with its speed right and up."""
        ratio = self.devicePixelRatioF()
        local = self.mapFromGlobal(QCursor.pos())
        current = QPoint(round(local.x() * ratio), round(local.y() * ratio))
        previous = self._cursor_point or current
        self._cursor_point = current
        seconds = max(step_ms, 1) / 1000
        velocity = ((current.x() - previous.x()) / seconds, (previous.y() - current.y()) / seconds)
        return CursorMotion(self._board, previous, current, velocity)

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
        for pixmap, position in self._badges():
            region = region.united(self._logical_rect(QRect(position, pixmap.size())))
        board = self._board_rect()
        if board:
            region = region.united(self._logical_rect(board))
        if region != self._painted:
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
        cursor = self._cursor_motion(step_ms)
        for pet in self._pets:
            if pet.is_visible:
                pet.look_for_food(foods, visible, step_ms)
                pet.interact(visible, step_ms)
            pet.update(step_ms, line_width, area_height, cursor)
            egg = pet.take_egg()
            if egg:
                self._eggs.append(egg)
        self._replace_carried_off(step_ms, line_width)
        for egg in self._eggs:
            egg.update(step_ms, line_width, area_height)
        self._eggs = [egg for egg in self._eggs if not egg.expired]
        self._refresh_region()
        self._adjust_tick_rate()
        self._fade_messages()

    def _fade_messages(self) -> None:
        """Fade the messages out at the first bounce and back in when the counters are gone."""
        is_hidden = self._is_hiding_messages and any(pet.bounces for pet in self._pets)
        if is_hidden == self._are_messages_hidden:
            return
        self._are_messages_hidden = is_hidden
        if is_hidden:
            self._messages_fader.fade_to(_MESSAGES_HIDDEN_OPACITY, _MESSAGES_FADE_OUT_MS)
        else:
            self._messages_fader.fade_to(1.0, _MESSAGES_FADE_IN_MS)

    def _show_messages(self) -> None:
        """Show the messages again at once, when the pets stop or go away during a fade."""
        self._are_messages_hidden = False
        self._messages_fader.restore()

    def _adjust_tick_rate(self) -> None:
        """Tick fast while a body is held or in the air, slowly otherwise."""
        is_action = any(body.is_flying or body.is_held for body in self._bodies())
        interval = self._action_tick_ms if is_action else self._ground_tick_ms
        if interval != self._timer.interval():
            self._timer.setInterval(interval)
