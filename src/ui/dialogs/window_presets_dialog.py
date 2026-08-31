"""Dialog for managing window size and position presets"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QInputDialog, QMessageBox, QLabel, QListWidgetItem
)
from PyQt6.QtCore import Qt, QTimer
from helpers.config import Config
from helpers.translate import tr, on_language_changed, TranslatableMixin


class WindowPresetsDialog(TranslatableMixin, QDialog):
    """Dialog to manage window geometry presets"""
    
    def __init__(self, config: Config, chat_window, parent=None):
        super().__init__(parent)
        self._init_translatable()
        self.config = config
        self.chat_window = chat_window
        
        self._tr_set(self.setWindowTitle, "Window Presets", "Пресеты окна")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(250)
        self.resize(450, 350)
        
        self._init_ui()
        self._load_presets()
        on_language_changed(self._retranslate)
    
    @staticmethod
    def _unnamed_label():
        return tr("Unnamed", "Без имени")

    def _init_ui(self):
        """Initialize the dialog UI"""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        self.setLayout(layout)
        
        self.preset_list = QListWidget()
        self.preset_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.preset_list.itemDoubleClicked.connect(self._load_selected_preset)
        self.preset_list.itemSelectionChanged.connect(self._update_button_states)
        layout.addWidget(self.preset_list)
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        
        self.save_button = QPushButton()
        self._tr_set(self.save_button.setText, "Save", "Сохранить")
        self.save_button.clicked.connect(self._save_current_preset)
        button_layout.addWidget(self.save_button)
        
        self.load_button = QPushButton()
        self._tr_set(self.load_button.setText, "Load", "Загрузить")
        self.load_button.clicked.connect(self._load_selected_preset)
        button_layout.addWidget(self.load_button)
        
        self.delete_button = QPushButton()
        self._tr_set(self.delete_button.setText, "Delete", "Удалить")
        self.delete_button.clicked.connect(self._delete_selected_preset)
        button_layout.addWidget(self.delete_button)
        
        self.close_button = QPushButton()
        self._tr_set(self.close_button.setText, "Close", "Закрыть")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        self._update_button_states()
    
    def _retranslate(self, _code=None):
        self._retranslate_all()
        self._load_presets()
    
    def _load_presets(self):
        """Load presets from config and populate list"""
        self.preset_list.clear()
        
        presets = self.config.get("ui", "window_presets")
        if not presets:
            return
        
        for preset in presets:
            name = preset.get("name", self._unnamed_label())
            width = preset.get("width")
            height = preset.get("height")
            x = preset.get("x")
            y = preset.get("y")
            
            text = tr(
                f"{name} - {width}x{height} at ({x}, {y})",
                f"{name} — {width}x{height} в ({x}, {y})"
            )
            
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, preset)
            self.preset_list.addItem(item)
        
        self._update_button_states()
    
    def _update_button_states(self):
        """Update load/delete button states based on selection"""
        selected_count = len(self.preset_list.selectedItems())
        self.load_button.setEnabled(selected_count == 1)
        self.delete_button.setEnabled(selected_count > 0)
    
    def _save_current_preset(self):
        """Save current window geometry as a new preset"""
        width = self.chat_window.width()
        height = self.chat_window.height()
        x = self.chat_window.x()
        y = self.chat_window.y()
        
        name, ok = QInputDialog.getText(
            self,
            tr("Save Preset", "Сохранить пресет"),
            tr("Enter preset name:", "Введите имя пресета:"),
            text=tr(f"Preset {self.preset_list.count() + 1}", f"Пресет {self.preset_list.count() + 1}")
        )
        
        if not ok or not name.strip():
            return
        
        name = name.strip()
        
        presets = self.config.get("ui", "window_presets") or []
        for preset in presets:
            if preset.get("name") == name:
                reply = QMessageBox.question(
                    self,
                    tr("Overwrite?", "Перезаписать?"),
                    tr(
                        f"Preset '{name}' already exists. Overwrite?",
                        f"Пресет «{name}» уже существует. Перезаписать?"
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                presets = [p for p in presets if p.get("name") != name]
                break
        
        preset = {
            "name": name,
            "width": width,
            "height": height,
            "x": x,
            "y": y
        }
        presets.append(preset)
        
        self.config.set("ui", "window_presets", value=presets)
        self._load_presets()
    
    def _load_selected_preset(self):
        """Load the selected preset and apply geometry"""
        current_item = self.preset_list.currentItem()
        if not current_item:
            return
        
        preset = current_item.data(Qt.ItemDataRole.UserRole)
        if not preset:
            return
        
        width = preset.get("width")
        height = preset.get("height")
        x = preset.get("x")
        y = preset.get("y")
        
        if width and height:
            self.chat_window._resetting_geometry = True
            
            self.chat_window.resize(width, height)
            if x is not None and y is not None:
                self.chat_window.move(x, y)
            
            QTimer.singleShot(100, lambda: setattr(self.chat_window, '_resetting_geometry', False))
            
            self.chat_window.window_size_manager.update_geometry(width, height, x or 0, y or 0)
            
            self.accept()
    
    def _delete_selected_preset(self):
        """Delete the selected preset(s)"""
        selected_items = self.preset_list.selectedItems()
        if not selected_items:
            return
        
        presets_to_delete = []
        for item in selected_items:
            preset = item.data(Qt.ItemDataRole.UserRole)
            if preset:
                presets_to_delete.append(preset.get("name", self._unnamed_label()))
        
        if not presets_to_delete:
            return
        
        if len(presets_to_delete) == 1:
            message = tr(
                f"Delete preset '{presets_to_delete[0]}'?",
                f"Удалить пресет «{presets_to_delete[0]}»?"
            )
            title = tr("Delete Preset", "Удалить пресет")
        else:
            message = tr(
                f"Delete {len(presets_to_delete)} selected presets?",
                f"Удалить {len(presets_to_delete)} выбранных пресетов?"
            )
            title = tr("Delete Presets", "Удалить пресеты")
        
        reply = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        presets = self.config.get("ui", "window_presets") or []
        presets = [p for p in presets if p.get("name") not in presets_to_delete]
        self.config.set("ui", "window_presets", value=presets)
        
        self._load_presets()