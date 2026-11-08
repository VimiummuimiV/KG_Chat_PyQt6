"""Reusable duration dialog for ban periods"""

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from helpers.translate import on_language_changed, tr, TranslatableMixin


class DurationDialog(TranslatableMixin, QDialog):
    """Unified dialog for selecting ban duration with multiple time units"""

    _UNITS = {
        'minutes': 60,
        'hours': 3600,
        'days': 86400,
        'weeks': 604800
    }
    _UNIT_KEYS = ['minutes', 'hours', 'days', 'weeks']
    _UNIT_LABELS = {
        'minutes': ("minutes", "минуты"),
        'hours':   ("hours",   "часы"),
        'days':    ("days",    "дни"),
        'weeks':   ("weeks",   "недели"),
    }

    def __init__(self, parent=None, default_seconds: int = 3600):
        super().__init__(parent)
        self.init_translatable()
        self.tr_set(self.setWindowTitle, "Ban Duration", "Длительность бана")
        self.setFixedWidth(320)

        # Auto-select best unit for default
        self.value, self.unit = self._seconds_to_best_unit(default_seconds)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self._lbl = QLabel()
        self.tr_set(self._lbl.setText, "Select duration:", "Выберите длительность:")
        layout.addWidget(self._lbl)

        # Input row
        row = QHBoxLayout()
        row.setSpacing(8)

        self.spin = QSpinBox()
        self.spin.setRange(1, 999)
        self.spin.setValue(self.value)
        row.addWidget(self.spin, stretch=1)

        self.combo = QComboBox()
        for key in self._UNIT_KEYS:
            en, ru = self._UNIT_LABELS[key]
            self.combo.addItem(tr(en, ru), key)
        # select by data key
        idx = self._UNIT_KEYS.index(self.unit) if self.unit in self._UNIT_KEYS else 0
        self.combo.setCurrentIndex(idx)
        row.addWidget(self.combo, stretch=1)

        layout.addLayout(row)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        on_language_changed(self._retranslate)

    def _retranslate(self, _code=None):
        self.retranslate_all()
        current = self.combo.currentData() or self.unit
        for i, key in enumerate(self._UNIT_KEYS):
            en, ru = self._UNIT_LABELS[key]
            self.combo.setItemText(i, tr(en, ru))
        if current in self._UNIT_KEYS:
            self.combo.setCurrentIndex(self._UNIT_KEYS.index(current))

    def _seconds_to_best_unit(self, seconds):
        """Convert seconds to most appropriate unit based on magnitude"""
        weeks = seconds / 604800
        if weeks >= 1:
            return max(1, round(weeks)), 'weeks'

        days = seconds / 86400
        if days >= 1:
            return max(1, round(days)), 'days'

        hours = seconds / 3600
        if hours >= 1:
            return max(1, round(hours)), 'hours'

        return max(1, seconds // 60), 'minutes'

    def _get_seconds(self) -> int:
        """Get duration in seconds"""
        key = self.combo.currentData() or self.combo.currentText()
        return self.spin.value() * self._UNITS[key]

    @staticmethod
    def get_duration(parent=None, default_seconds: int = 3600):
        """Show dialog and return (seconds, accepted)"""
        dlg = DurationDialog(parent, default_seconds)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        return (dlg._get_seconds() if ok else default_seconds, ok)
