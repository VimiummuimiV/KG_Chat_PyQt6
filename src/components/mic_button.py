"""Microphone button with hold-to-talk, click-to-latch, VU meter and device menu."""
from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QTimer, QRectF, QLineF, pyqtSignal, QElapsedTimer
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QPen, QPaintEvent, QMouseEvent, QActionGroup, QCursor
from PyQt6.QtWidgets import QApplication, QPushButton, QMenu

from helpers.button import _render_svg_icon, _icon_registry
from helpers.translate import tr
from helpers.voice.voice_input import (
    InputDevice,
    list_input_devices,
)


# How long a press may last and still count as a click (latch toggle).
CLICK_MAX_MS = 280

# VU zone thresholds (0..1 of painted height, from the bottom).
ZONE_GREEN = 0.55
ZONE_YELLOW = 0.80


class MicButton(QPushButton):
    """Icon button that does not steal focus from the message field.

    Left press/hold  → hold_started / hold_stopped  (push-to-talk)
    Short left click → latch_toggled(bool)          (keep listening after send)
    Right click      → device + language menu
    """

    hold_started = pyqtSignal()
    hold_stopped = pyqtSignal()
    latch_toggled = pyqtSignal(bool)
    device_chosen = pyqtSignal(object)   # InputDevice | None (None = system default)

    def __init__(
        self,
        icons_path: Path,
        icon_size: int = 30,
        button_size: int = 48,
        parent=None,
    ):
        super().__init__(parent)
        self._icons_path = Path(icons_path)
        self._icon_size = icon_size
        self._level = 0.0
        self._display_level = 0.0
        self._peak = 0.0
        self._listening = False
        self._latched = False
        self._pressing = False
        self._press_timer = QElapsedTimer()
        self._ignore_release = False
        self._device_name: str | None = None
        self._device_index: int | None = None
        self._status_hint = ""

        # So Enter still sends: this button never takes the focus.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoDefault(False)
        self.setDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setFixedSize(button_size, button_size)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        self._peak_decay = QTimer(self)
        self._peak_decay.setInterval(40)
        self._peak_decay.timeout.connect(self._tick_meters)
        self._peak_decay.start()

        self._icon_path = self._icons_path
        self._icon_name = "mic-off.svg"
        _icon_registry.append(self)
        self.refresh_icon()
        self._refresh_tooltip()

    # ── public API ──────────────────────────────────────────────────────────

    def set_listening(self, listening: bool):
        if self._listening == listening:
            return
        self._listening = listening
        if not listening:
            self._level = 0.0
        self.refresh_icon()
        self._refresh_tooltip()
        self.update()

    def set_latched(self, latched: bool):
        self._latched = bool(latched)
        self._refresh_tooltip()
        self.update()

    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, float(level)))
        if self._level > self._peak:
            self._peak = self._level

    def set_device(self, name: str | None, index: int | None):
        self._device_name = name
        self._device_index = index
        self._refresh_tooltip()

    def set_status_hint(self, hint: str):
        self._status_hint = hint or ""
        self._refresh_tooltip()

    def refresh_icon(self):
        """Called from update_all_icons() on theme change."""
        name = "mic-on.svg" if self._listening else "mic-off.svg"
        icon_path = self._icons_path / name
        if not icon_path.exists():
            icon_path = self._icons_path / "mic-off.svg"
        self._icon_name = icon_path.name
        self.setIcon(_render_svg_icon(icon_path, self._icon_size))

    # ── events ──────────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressing = True
            self._ignore_release = False
            self._press_timer.start()
            # PTT starts immediately so the meter reacts with no delay.
            # A short click will convert this into latch on release.
            if not self._latched and not self._listening:
                self.hold_started.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        self._pressing = False
        elapsed = self._press_timer.elapsed() if self._press_timer.isValid() else 0
        if self._ignore_release:
            event.accept()
            return
        if elapsed <= CLICK_MAX_MS:
            # Click: toggle latch. If we just auto-started PTT, keep it
            # running and mark latched; if it was already latched, stop.
            new_state = not self._latched
            self._latched = new_state
            self.latch_toggled.emit(new_state)
        else:
            # Hold-to-talk release.
            if self._latched:
                # Holding while latched does nothing extra on release.
                pass
            else:
                self.hold_stopped.emit()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        # Treat as two clicks would be noisy; ignore extras.
        event.accept()

    # ── paint: safety meter behind the icon ─────────────────────────────────

    def _button_radius(self) -> float:
        """Read border-radius from the widget / app stylesheet (same as the outline)."""
        chunks: list[str] = []
        if self.styleSheet():
            chunks.append(self.styleSheet())
        app = QApplication.instance()
        if app and app.styleSheet():
            chunks.append(app.styleSheet())
        text = "\n".join(chunks)
        radii: list[float] = []
        for block in re.finditer(r"QPushButton[^{]*\{([^}]+)\}", text, re.I):
            found = re.search(r"border-radius\s*:\s*(\d+(?:\.\d+)?)(?:px)?", block.group(1), re.I)
            if found:
                radii.append(float(found.group(1)))
        if radii:
            return radii[-1]
        found = re.search(r"border-radius\s*:\s*(\d+(?:\.\d+)?)(?:px)?", text, re.I)
        if found:
            return float(found.group(1))
        return 8.0

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        if not self._listening and not self._latched:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Sit just inside the 1px theme border so the outline stays visible
        # and the fill follows the same corner curve (inner r = outer r - inset).
        inset = 1.0
        rect = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        radius = max(0.0, self._button_radius() - inset)
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip)

        if self._listening:
            self._fill_band(p, rect, 0.0, ZONE_GREEN, QColor(46, 160, 67, 50))
            self._fill_band(p, rect, ZONE_GREEN, ZONE_YELLOW, QColor(212, 168, 28, 50))
            self._fill_band(p, rect, ZONE_YELLOW, 1.0, QColor(196, 62, 62, 50))

            level = self._display_level
            if level > 0.001:
                self._fill_band(p, rect, 0.0, min(level, ZONE_GREEN), QColor(46, 160, 67, 160))
                if level > ZONE_GREEN:
                    self._fill_band(p, rect, ZONE_GREEN, min(level, ZONE_YELLOW), QColor(212, 168, 28, 160))
                if level > ZONE_YELLOW:
                    self._fill_band(p, rect, ZONE_YELLOW, level, QColor(196, 62, 62, 160))

            if self._peak > 0.02:
                peak_y = rect.bottom() - rect.height() * self._peak
                zone = self._zone_color(self._peak, filled=True)
                zone.setAlpha(220)
                pen = QPen(zone)
                pen.setWidthF(1.5)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                p.setPen(pen)
                p.drawLine(QLineF(rect.left(), peak_y, rect.right(), peak_y))

        icon = self.icon()
        if not icon.isNull():
            pix = icon.pixmap(self.iconSize())
            p.drawPixmap(
                int((self.width() - pix.width()) / 2),
                int((self.height() - pix.height()) / 2),
                pix,
            )

        if self._latched:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(226, 135, 67))
            p.drawEllipse(int(rect.right() - 10), int(rect.top() + 4), 6, 6)

        p.end()

    def _fill_band(self, p: QPainter, rect: QRectF, lo: float, hi: float, color: QColor):
        lo = max(0.0, min(1.0, lo))
        hi = max(0.0, min(1.0, hi))
        if hi <= lo:
            return
        top = rect.bottom() - rect.height() * hi
        bot = rect.bottom() - rect.height() * lo
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRect(QRectF(rect.left(), top, rect.width(), max(1.0, bot - top)))

    def _zone_color(self, level: float, filled: bool) -> QColor:
        return self._color_for_level(level, filled)

    @staticmethod
    def _round_rect(rect: QRectF, tl: float, tr: float, br: float, bl: float) -> QPainterPath:
        cap = min(rect.width(), rect.height()) / 2.0
        tl, tr, br, bl = (min(v, cap) for v in (tl, tr, br, bl))
        path = QPainterPath()
        path.moveTo(rect.left() + tl, rect.top())
        path.lineTo(rect.right() - tr, rect.top())
        if tr:
            path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + tr)
        else:
            path.lineTo(rect.right(), rect.top())
        path.lineTo(rect.right(), rect.bottom() - br)
        if br:
            path.quadTo(rect.right(), rect.bottom(), rect.right() - br, rect.bottom())
        else:
            path.lineTo(rect.right(), rect.bottom())
        path.lineTo(rect.left() + bl, rect.bottom())
        if bl:
            path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - bl)
        else:
            path.lineTo(rect.left(), rect.bottom())
        path.lineTo(rect.left(), rect.top() + tl)
        if tl:
            path.quadTo(rect.left(), rect.top(), rect.left() + tl, rect.top())
        else:
            path.lineTo(rect.left(), rect.top())
        path.closeSubpath()
        return path

    def _color_for_level(self, level: float, filled: bool) -> QColor:
        alpha = 150 if filled else 38
        if level < ZONE_GREEN:
            return QColor(46, 160, 67, alpha)
        if level < ZONE_YELLOW:
            return QColor(212, 168, 28, alpha)
        return QColor(196, 62, 62, alpha)

    def _tick_meters(self):
        target = self._level if self._listening else 0.0
        self._display_level += (target - self._display_level) * 0.35
        if self._peak > self._display_level:
            self._peak = max(self._display_level, self._peak - 0.012)
        if self._listening or self._display_level > 0.002 or self._peak > 0.002:
            self.update()

    # ── menu ────────────────────────────────────────────────────────────────

    def _show_menu(self, _pos):
        # Opening the menu should not count as a PTT release/start.
        self._ignore_release = True
        if self._pressing and not self._latched:
            self.hold_stopped.emit()
        self._pressing = False

        menu = QMenu(self)
        devices = list_input_devices()

        default_act = menu.addAction(tr("Default device", "Устройство по умолчанию"))
        default_act.setCheckable(True)
        default_act.setChecked(self._device_name is None)
        default_act.triggered.connect(lambda: self.device_chosen.emit(None))

        if devices:
            menu.addSeparator()
            group = QActionGroup(menu)
            group.setExclusive(True)
            for dev in devices:
                act = menu.addAction(dev.label())
                act.setCheckable(True)
                act.setActionGroup(group)
                if self._device_name and dev.name == self._device_name:
                    act.setChecked(True)
                    default_act.setChecked(False)
                act.triggered.connect(lambda _=False, d=dev: self.device_chosen.emit(d))
        else:
            menu.addSeparator()
            dummy = menu.addAction(
                tr("No input devices / sounddevice missing",
                   "Нет устройств / не установлен sounddevice")
            )
            dummy.setEnabled(False)

        menu.exec(QCursor.pos())

    def _refresh_tooltip(self):
        if self._latched:
            mode = tr("Listening (click to stop)", "Слушаю (клик — стоп)")
        elif self._listening:
            mode = tr("Hold to talk", "Удерживайте для записи")
        else:
            mode = tr(
                "Hold to talk · Click to keep listening",
                "Удерживайте для записи · Клик — непрерывный ввод",
            )
        dev = self._device_name or tr("Default device", "Устройство по умолчанию")
        parts = [
            tr("Voice input", "Голосовой ввод"),
            mode,
            dev,
        ]
        if self._status_hint:
            parts.append(self._status_hint)
        self.setToolTip("\n".join(parts))
