"""Sound picker widget for one alert kind."""

import shutil
from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QWidget

from components.button import create_icon_button, set_visual_active
from helpers.data import get_resource_dir
from helpers.fonts.fonts import FontType, get_font
from helpers.sounds import (
    get_merged_sound_files,
    get_sound_name,
    get_system_sound_dir,
    get_user_sound_dir,
    is_sound_frozen,
    resolve_sound_file,
    set_sound_frozen,
)
from helpers.translate import on_language_changed, tr, TranslatableMixin
from helpers.voice.voice_engine import play_sound
from ui.settings.settings_widgets import NoWheelComboBox


class SoundSelectorWidget(TranslatableMixin, QWidget):
    """Selector for one notification sound type.

    System sounds (project/sounds/...) are listed but cannot be deleted or renamed.
    User sounds live in KG_Chat_Data/sounds/<kind>/ and can be added, renamed, deleted.
    """

    def __init__(self, config, sound_root: Path, kind: str, label_text: str):
        super().__init__()
        self.init_translatable()
        self.config = config
        self._sound_root = sound_root
        self.kind = kind
        self.config_key = (kind or '').strip().lower()
        self._system_dir = get_system_sound_dir(sound_root, kind)
        self._user_dir = get_user_sound_dir(kind)
        self.icons_path = get_resource_dir("icons")

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.setLayout(layout)

        label = QLabel(label_text)
        label.setFont(get_font(FontType.UI))
        layout.addWidget(label)
        self.register_tr(label.setText, label_text)

        def _nav_button(icon_name, tooltip, on_click):
            button = create_icon_button(self.icons_path, icon_name, tooltip, size_type="small", config=self.config)
            button.clicked.connect(on_click)
            layout.addWidget(button)
            self.register_tr(button.setToolTip, tooltip)
            return button

        self._prev_button = _nav_button("line/arrow-left-s-line.svg", tr("Previous sound", "Предыдущий звук"), self._on_prev)

        self.combo = NoWheelComboBox()
        self.combo.setFont(get_font(FontType.UI))
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        self.combo.setMinimumWidth(180)
        layout.addWidget(self.combo, stretch=1)

        self._next_button = _nav_button("line/arrow-right-s-line.svg", tr("Next sound", "Следующий звук"), self._on_next)
        self._play_button = _nav_button("fill/play-large-fill.svg", tr("Play sound", "Воспроизвести звук"), self._on_play)
        self._freeze_button = _nav_button(
            "line/snowflake-line.svg", self._freeze_tooltip(), self._on_freeze
        )
        self._add_button = _nav_button("line/add-large-line.svg", tr("Add sound from file", "Добавить звук из файла"), self._on_add)
        self._delete_button = _nav_button("fill/delete-bin-fill.svg", tr("Delete sound", "Удалить звук"), self._on_delete)
        self._rename_button = _nav_button("fill/pencil-fill.svg", tr("Rename sound", "Переименовать звук"), self._on_rename)

        self.refresh()
        on_language_changed(self.retranslate_all)

    def _freeze_tooltip(self) -> str:
        return (
            tr("Unfreeze sound", "Разморозить звук")
            if is_sound_frozen(self.config, self.config_key) else
            tr("Freeze sound", "Заморозить звук")
        )

    def _on_freeze(self):
        set_sound_frozen(self.config, self.config_key, not is_sound_frozen(self.config, self.config_key))
        self._update_freeze_button()

    def _update_freeze_button(self):
        frozen = is_sound_frozen(self.config, self.config_key)
        set_visual_active(self._freeze_button, not frozen)
        self._freeze_button.setToolTip(self._freeze_tooltip())

    def retranslate_all(self, _code=None):
        super().retranslate_all(_code)
        self._update_freeze_button()

    def _safe_name(self) -> str | None:
        return self.combo.currentData()

    def _is_user_owned(self, file_name: str | None) -> bool:
        if not file_name:
            return False
        return (self._user_dir / file_name).is_file()

    def _resolve_path(self, file_name: str | None) -> Path | None:
        if not file_name:
            return None
        return resolve_sound_file(file_name, self._system_dir, self._user_dir)

    def _update_edit_buttons(self):
        """Delete/Rename only for user-owned files."""
        user_owned = self._is_user_owned(self._safe_name())
        self._delete_button.setEnabled(user_owned)
        self._rename_button.setEnabled(user_owned)

    def _update_button_states(self):
        self._update_edit_buttons()
        self._update_freeze_button()

    def _persist_selection(self, name: str | None):
        if not self.config:
            return
        selected = self.config.get("sound", "selected") or {}
        if not isinstance(selected, dict):
            selected = {}
        selected = dict(selected)

        if name:
            selected[self.config_key] = name
        else:
            selected.pop(self.config_key, None)

        self.config.set(
            "sound",
            "selected",
            value={k: v for k, v in selected.items() if v is not None},
        )

    def _confirm(self, title: str, text: str) -> bool:
        reply = QMessageBox.question(
            self, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _require_user_owned(self, title: str, message: str) -> str | None:
        """Return the selected file name if it's user-owned, else show why not and return None."""
        file_name = self._safe_name()
        if file_name and self._is_user_owned(file_name):
            return file_name
        QMessageBox.information(self, title, message)
        return None

    def _play_file(self, file_name: str | None):
        """Stop any current effect and play the chosen file (preview ignores mute)."""
        path = self._resolve_path(file_name)
        if not path:
            return
        # force=True so preview works even when effects are muted;
        # play_sound already cancels the previous sound.
        play_sound(str(path), config=self.config, force=True)

    @staticmethod
    def _display_name(file_name: str) -> str:
        """Combo label without the extension - only .mp3 is supported, so it's just noise."""
        return file_name[:-4] if file_name.lower().endswith(".mp3") else file_name

    def refresh(self, select_name: str | None = None):
        files = get_merged_sound_files(self._system_dir, self._user_dir)
        self.combo.blockSignals(True)
        self.combo.clear()

        if not files:
            self.combo.addItem(tr("No sound", "Нет звука"), None)
            self.combo.setEnabled(False)
            self._persist_selection(None)
            self.combo.blockSignals(False)
            self._update_button_states()
            return

        self.combo.setEnabled(True)
        for file_name in files:
            self.combo.addItem(self._display_name(file_name), file_name)

        preferred = select_name or get_sound_name(self._sound_root, self.kind, self.config)
        index = self.combo.findData(preferred) if preferred else -1
        self.combo.setCurrentIndex(index if index >= 0 else 0)

        self._persist_selection(self.combo.currentData())
        self.combo.blockSignals(False)
        self._update_button_states()

    def _on_combo_changed(self, _index: int):
        name = self.combo.currentData()
        if name is None:
            self._persist_selection(None)
            self._update_button_states()
            return
        self._persist_selection(name)
        self._update_edit_buttons()
        self._play_file(name)

    def _on_prev(self):
        if self.combo.count() <= 1:
            return
        self.combo.setCurrentIndex((self.combo.currentIndex() - 1) % self.combo.count())

    def _on_next(self):
        if self.combo.count() <= 1:
            return
        self.combo.setCurrentIndex((self.combo.currentIndex() + 1) % self.combo.count())

    def _on_play(self):
        self._play_file(self._safe_name())

    def _on_add(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Select sound file", "Выберите файл со звуком"),
            "",
            tr("Audio (*.mp3);;All files (*)", "Аудио (*.mp3);;Все файлы (*)"),
        )
        if not path:
            return

        src = Path(path)
        if not src.is_file():
            return

        self._user_dir.mkdir(parents=True, exist_ok=True)

        stem = src.stem
        dest_name = f"{stem}.mp3"
        dest = self._user_dir / dest_name

        if dest.exists() and not self._confirm(
            tr("File exists", "Файл уже существует"),
            tr(f"'{dest_name}' already exists in your sounds. Overwrite?",
               f"«{dest_name}» уже есть в ваших звуках. Перезаписать?"),
        ):
            return

        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            QMessageBox.warning(self, tr("Add sound", "Добавить звук"),
                                 tr(f"Failed to copy file: {exc}", f"Не удалось скопировать файл: {exc}"))
            return

        self.refresh(select_name=dest_name)
        self._play_file(dest_name)

    def _on_delete(self):
        title = tr("Delete sound", "Удалить звук")
        file_name = self._require_user_owned(
            title, tr("System sounds cannot be deleted. Only sounds you added can be deleted.",
                      "Системные звуки нельзя удалить. Можно удалять только добавленные вами звуки.")
        )
        if not file_name:
            return

        path = self._user_dir / file_name
        if not self._confirm(title, tr(f"Delete '{file_name}'?", f"Удалить «{file_name}»?")):
            return

        try:
            path.unlink()
        except OSError as exc:
            QMessageBox.warning(self, title, tr(f"Failed to delete sound: {exc}", f"Не удалось удалить звук: {exc}"))
            return

        self.refresh()

    def _on_rename(self):
        title = tr("Rename sound", "Переименовать звук")
        file_name = self._require_user_owned(
            title, tr("System sounds cannot be renamed. Only sounds you added can be renamed.",
                      "Системные звуки нельзя переименовать. Можно переименовывать только добавленные вами звуки.")
        )
        if not file_name:
            return

        current_path = self._user_dir / file_name
        dialog = QInputDialog(self)
        dialog.setWindowTitle(title)
        dialog.setLabelText(tr("New file name:", "Новое имя файла:"))
        dialog.setTextValue(self._display_name(file_name))
        dialog.resize(400, dialog.sizeHint().height())
        if not dialog.exec():
            return
        new_stem = dialog.textValue()
        if not new_stem.strip():
            return

        clean_name = new_stem.strip().strip("\\/")
        if clean_name.lower().endswith(".mp3"):
            clean_name = clean_name[:-4]  # in case the user typed it anyway
        clean_name = f"{clean_name}.mp3"

        if any(ch in clean_name for ch in ("/", "\\")):
            QMessageBox.warning(self, title, tr("The name cannot contain path separators.",
                                                 "Имя не может содержать разделители пути."))
            return

        target_path = self._user_dir / clean_name
        if target_path.exists() and target_path.name.lower() != current_path.name.lower():
            QMessageBox.warning(self, title, tr("A sound with that name already exists.",
                                                 "Звук с таким именем уже существует."))
            return

        try:
            current_path.rename(target_path)
        except OSError as exc:
            QMessageBox.warning(self, title, tr(f"Failed to rename sound: {exc}", f"Не удалось переименовать звук: {exc}"))
            return

        self.refresh(select_name=clean_name)
