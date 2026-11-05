"""SettingsWidget: global hotkey row and capture."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout

from components.button import create_icon_button
from helpers.colors.color_utils import tinted_chip_colors
from helpers.fonts.fonts import FontType, get_font
from helpers.system import hotkey_manager as hotkey
from helpers.translate import tr
from ui.settings.settings_widgets import ClickableLabel, SettingsRow


class SettingsHotkeyMixin:
    """SettingsWidget: global hotkey row and capture."""

    def _add_hotkey_row(self, section_layout: QVBoxLayout, label_text: str):
        row_widget = SettingsRow(spacing=self._spacing())
        row = row_widget.layout()

        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        row.addWidget(label, stretch=1)
        self.register_tr(label.setText, label_text)

        self.hotkey_status_dot = ClickableLabel()
        self.hotkey_status_dot.setObjectName("hotkeyStatusDot")
        self.hotkey_status_dot.setFixedSize(10, 10)
        self.hotkey_status_dot.clicked.connect(self._on_hotkey_status_clicked)
        row.addWidget(self.hotkey_status_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addSpacing(4)

        self.hotkey_button = QPushButton()
        self.hotkey_button.setFont(get_font(FontType.UI))
        self.hotkey_button.setFixedWidth(180)
        self.hotkey_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hotkey_button.clicked.connect(self._on_hotkey_record_clicked)
        row.addWidget(self.hotkey_button)

        hotkey_reset_tooltip = tr("Reset to default", "Сбросить по умолчанию")
        self.hotkey_reset_button = create_icon_button(
            self.icons_path, "reload.svg", hotkey_reset_tooltip, size_type="small", config=self.config
        )
        self.hotkey_reset_button.clicked.connect(self._on_hotkey_reset_clicked)
        row.addWidget(self.hotkey_reset_button)
        self.register_tr(self.hotkey_reset_button.setToolTip, hotkey_reset_tooltip)

        section_layout.addWidget(row_widget)

    def _current_hotkey(self) -> str:
        return self.config.get("hotkey", "combo") or hotkey.DEFAULT_HOTKEY

    def _refresh_hotkey_row(self):
        combo = self._current_hotkey()
        self.hotkey_button.setText(hotkey.display_hotkey(combo))
        self.hotkey_reset_button.setEnabled(combo != hotkey.DEFAULT_HOTKEY)
        self._on_hotkey_status_changed(hotkey.hotkey_manager.status, "")

    def _on_hotkey_record_clicked(self):
        if self._hotkey_capture is not None:
            return
        self.hotkey_button.setText(tr("Press keys…", "Нажмите клавиши…"))
        self.hotkey_button.setEnabled(False)
        self.hotkey_reset_button.setEnabled(False)
        self._hotkey_capture = hotkey.HotkeyCapture()
        self._hotkey_capture.captured.connect(self._on_hotkey_captured)
        self._hotkey_capture.cancelled.connect(self._on_hotkey_capture_cancelled)
        self._hotkey_capture.start()

    def _on_hotkey_captured(self, combo: str):
        self._hotkey_capture = None
        self.hotkey_button.setEnabled(True)
        self.config.set("hotkey", "combo", value=combo)
        hotkey.hotkey_manager.register(combo)
        self._refresh_hotkey_row()

    def _on_hotkey_capture_cancelled(self):
        self._hotkey_capture = None
        self.hotkey_button.setEnabled(True)
        self._refresh_hotkey_row()

    def _on_hotkey_reset_clicked(self):
        self.config.set("hotkey", "combo", value=hotkey.DEFAULT_HOTKEY)
        hotkey.hotkey_manager.register(hotkey.DEFAULT_HOTKEY)
        self._refresh_hotkey_row()

    def _on_hotkey_status_changed(self, status: str, detail: str):
        color = hotkey.STATUS_COLORS.get(status, hotkey.STATUS_COLORS[hotkey.STATUS_DISABLED])
        tooltip = detail or hotkey.get_status_tooltip(status)
        can_retry = status != hotkey.STATUS_ACTIVE
        is_dark = (self.config.get("ui", "theme") or "dark") == "dark"
        tooltip_bg, tooltip_fg, tooltip_border = tinted_chip_colors(color, is_dark)
        self.hotkey_status_dot.setStyleSheet(
            f"#hotkeyStatusDot {{ background-color: {color}; border-radius: 5px; }}"
            f"QToolTip {{ background-color: {tooltip_bg}; color: {tooltip_fg}; border: 1px solid {tooltip_border}; }}"
        )
        self.hotkey_status_dot.setToolTip(tooltip + tr(" (click to retry)", " (нажмите для повтора)") if can_retry else tooltip)
        self.hotkey_status_dot.setCursor(
            Qt.CursorShape.PointingHandCursor if can_retry else Qt.CursorShape.ArrowCursor
        )

    def _on_hotkey_status_clicked(self):
        if hotkey.hotkey_manager.status == hotkey.STATUS_ACTIVE:
            return
        hotkey.hotkey_manager.register(self._current_hotkey())
