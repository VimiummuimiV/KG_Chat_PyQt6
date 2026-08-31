"""Reusable duration dialog for ban periods"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QComboBox, QDialogButtonBox
from PyQt6.QtCore import Qt

from helpers.translate import tr, on_language_changed, TranslatableMixin


class DurationDialog(TranslatableMixin, QDialog):
    """Unified dialog for selecting ban duration with multiple time units"""
    
    UNITS = {
        'minutes': 60,
        'hours': 3600,
        'days': 86400,
        'weeks': 604800
    }
    UNIT_KEYS = ['minutes', 'hours', 'days', 'weeks']
    UNIT_LABELS = {
        'minutes': ("minutes", "минуты"),
        'hours':   ("hours",   "часы"),
        'days':    ("days",    "дни"),
        'weeks':   ("weeks",   "недели"),
    }
    
    def __init__(self, parent=None, default_seconds: int = 3600):
        super().__init__(parent)
        self._init_translatable()
        self._tr_set(self.setWindowTitle, "Ban Duration", "Длительность бана")
        self.setFixedWidth(320)
        
        # Auto-select best unit for default
        self.value, self.unit = self._seconds_to_best_unit(default_seconds)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        self._lbl = QLabel()
        self._tr_set(self._lbl.setText, "Select duration:", "Выберите длительность:")
        layout.addWidget(self._lbl)
        
        # Input row
        row = QHBoxLayout()
        row.setSpacing(8)
        
        self.spin = QSpinBox()
        self.spin.setRange(1, 999)
        self.spin.setValue(self.value)
        row.addWidget(self.spin, stretch=1)
        
        self.combo = QComboBox()
        for key in self.UNIT_KEYS:
            en, ru = self.UNIT_LABELS[key]
            self.combo.addItem(tr(en, ru), key)
        # select by data key
        idx = self.UNIT_KEYS.index(self.unit) if self.unit in self.UNIT_KEYS else 0
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
        self._retranslate_all()
        current = self.combo.currentData() or self.unit
        for i, key in enumerate(self.UNIT_KEYS):
            en, ru = self.UNIT_LABELS[key]
            self.combo.setItemText(i, tr(en, ru))
        if current in self.UNIT_KEYS:
            self.combo.setCurrentIndex(self.UNIT_KEYS.index(current))
    
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
    
    def get_seconds(self) -> int:
        """Get duration in seconds"""
        key = self.combo.currentData() or self.combo.currentText()
        return self.spin.value() * self.UNITS[key]
    
    @staticmethod
    def get_duration(parent=None, default_seconds: int = 3600):
        """Show dialog and return (seconds, accepted)"""
        dlg = DurationDialog(parent, default_seconds)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        return (dlg.get_seconds() if ok else default_seconds, ok)