"""ChatWindow: toolbar toggles and sound/notification/always-on-top state."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from helpers.data import get_resource_dir
from helpers.deferred import call_later
from helpers.sounds import get_sound_path, is_sound_frozen
from helpers.translate import tr
from helpers.users.username_color_manager import change_username_color, reset_username_color
from helpers.voice.voice_engine import play_sound
from ui.notification.popup_manager import popup_manager


class ChatControlsMixin:
    """ChatWindow: toolbar toggles and sound/notification/always-on-top state."""

    def set_tray_mode(self, enabled: bool):

        self.tray_mode = enabled

    def on_change_username_color(self):
        """Called from ButtonPanel to change own username color."""
        if not self.app_controller:
            QMessageBox.warning(self, tr("Unavailable", "Недоступно"), tr("This action requires the application controller.", "Это действие требует контроллер приложения."))
            return
        self.app_controller.refresh_own_username_color(change_username_color)

    def on_reset_username_color(self):
        """Called from ButtonPanel to reset own username color."""
        if not self.app_controller:
            QMessageBox.warning(self, tr("Unavailable", "Недоступно"), tr("This action requires the application controller.", "Это действие требует контроллер приложения."))
            return
        self.app_controller.refresh_own_username_color(reset_username_color)

    def on_toggle_voice_sound(self):
        """Toggle TTS (Voice Sound) from the panel button."""
        current = self.config.get("sound", "tts_enabled") or False
        self._apply_voice_sound(not current)

    def _apply_voice_sound(self, new: bool):
        """Set TTS (Voice Sound) to an explicit state. Shared by the panel button and Settings."""
        # Persist centrally via app controller so tray stays in sync
        config = self.app_controller.config if self.app_controller else self.config
        config.set("sound", "tts_enabled", value=new)
        # Also update local config data to keep in sync
        if self.app_controller:
            self.config.data = self.app_controller.config.data

        # update tray menu state immediately
        if self.app_controller and hasattr(self.app_controller, 'update_sound_menu'):
            self.app_controller.update_sound_menu()

        # Update engine and visual
        self.voice_engine.set_enabled(new)
        self.button_panel.set_button_state(self.button_panel.voice_button, new)

    def update_voice_button_state(self):
        """Sync voice button visual and engine state with config."""
        enabled = self.config.get("sound", "tts_enabled") or False
        self.voice_engine.set_enabled(enabled)

        # Defensive: button may not exist yet in some tests
        if getattr(self, 'button_panel', None) and getattr(self.button_panel, 'voice_button', None):
            self.button_panel.set_button_state(self.button_panel.voice_button, enabled)

    def on_toggle_effects_sound(self):
        """Toggle effects sound on/off from the panel button."""
        current = self.config.get("sound", "effects_enabled")
        if current is None:
            current = True
        self._apply_effects_sound(not current)

    def _apply_effects_sound(self, new: bool):
        """Set effects sound to an explicit state. Shared by the panel button and Settings."""
        # Persist centrally via app controller so tray stays in sync
        config = self.app_controller.config if self.app_controller else self.config
        config.set("sound", "effects_enabled", value=new)
        # Also update local config data to keep in sync
        if self.app_controller:
            self.config.data = self.app_controller.config.data

        # update tray menu state immediately
        if self.app_controller and hasattr(self.app_controller, 'update_sound_menu'):
            self.app_controller.update_sound_menu()

        # Update visual and icon
        if getattr(self, 'button_panel', None) and getattr(self.button_panel, 'effects_button', None):
            self.button_panel.set_button_state(self.button_panel.effects_button, new)
            self.button_panel.update_effects_button_icon()

    def update_effects_button_state(self):
        """Sync effects button visual to config state."""
        enabled = self.config.get("sound", "effects_enabled")
        if enabled is None:
            enabled = True
        if getattr(self, 'button_panel', None) and getattr(self.button_panel, 'effects_button', None):
            self.button_panel.set_button_state(self.button_panel.effects_button, enabled)
            self.button_panel.update_effects_button_icon()

    def on_toggle_notification(self):
        """Toggle notifications muted on/off. Stack/Replace is chosen in Settings."""
        current_muted = self.config.get("notification", "muted") or False
        self.apply_notification_muted(not current_muted)

    def apply_notification_muted(self, muted: bool):
        """Set notification muted state. Shared by the panel button and tray."""
        config = self.app_controller.config if self.app_controller else self.config
        config.set("notification", "muted", value=muted)

        if self.app_controller:
            self.config.data = self.app_controller.config.data

        if self.app_controller and hasattr(self.app_controller, "update_notification_menu"):
            self.app_controller.update_notification_menu()

        popup_manager.set_muted(muted)
        self.button_panel.update_notification_button_icon()
        print(f"🔔 Notifications: {'Disabled' if muted else 'Enabled'}")

    def update_notification_button_state(self):
        """Sync notification button visual to config state"""
        if getattr(self, "button_panel", None) and getattr(self.button_panel, "notification_button", None):
            self.button_panel.update_notification_button_icon()

    def sync_notification_state(self):
        """Sync notification state from config - updates button and popup_manager"""
        if self.app_controller:
            self.config.data = self.app_controller.config.data

        self.update_notification_button_state()

        mode = self.config.get("notification", "mode") or "stack"
        muted = self.config.get("notification", "muted") or False
        popup_manager.set_notification_mode(mode)
        popup_manager.set_muted(muted)

    def on_toggle_always_on_top(self):
        """Toggle always on top window flag"""
        current = self.config.get("ui", "always_on_top") or False
        self._apply_always_on_top(not current)

    def _apply_always_on_top(self, new: bool):
        """Set always-on-top to an explicit state. Shared by the panel button and Settings."""
        # Save to config
        config = self.app_controller.config if self.app_controller else self.config
        config.set("ui", "always_on_top", value=new)

        # Update local config data
        if self.app_controller:
            self.config.data = self.app_controller.config.data

        # Apply window flag (requires hide/show to take effect properly)
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, new)

        # Show window if it was visible before
        if was_visible:
            self.setWindowOpacity(0)
            self.show()
            call_later(self, 50, lambda: self.setWindowOpacity(1))
            self.activateWindow()
            self.raise_()

        # Update button icon to reflect new state
        if hasattr(self, 'button_panel') and hasattr(self.button_panel, 'update_pin_button_icon'):
            self.button_panel.update_pin_button_icon()

        print(f"📌 Always on top: {'Enabled' if new else 'Disabled'}")

    def update_always_on_top_button_state(self):
        """Sync always on top button visual to config state"""
        if getattr(self, 'button_panel', None) and getattr(self.button_panel, 'update_pin_button_icon', None):
            self.button_panel.update_pin_button_icon()

    def on_exit_requested(self):
        """Handle exit request from the button panel."""
        # Prefer the application controller's cleanup exit when available
        if self.app_controller and hasattr(self.app_controller, 'exit_application'):
            self.app_controller.exit_application()
        else:
            QApplication.quit()

    def setup_sounds(self):
        """Setup sound paths using the per-category sound folders."""
        sounds_dir = get_resource_dir("sounds")
        for kind, attr in (
            ("mention", "mention_sound_path"),
            ("ban", "ban_sound_path"),
            ("competition", "competition_sound_path"),
        ):
            path = get_sound_path(sounds_dir, kind, self.config)
            setattr(self, attr, str(path) if path else None)

    def _play_notification_sound(self, path: str | None, kind: str, force: bool = False, fallback_beep: bool = False):
        """Play an effect by path. play_sound() already threads and handles its
        own errors, so no extra wrapping is needed here."""
        if not force and is_sound_frozen(self.config, kind):
            return
        if not path:
            if fallback_beep:
                try:
                    QApplication.instance().beep()
                except Exception as e:
                    print(f"System beep error: {e}")
            return
        play_sound(path, config=self.config, force=force)

    def play_mention_sound(self):
        self._play_notification_sound(self.mention_sound_path, "mention", fallback_beep=True)

    def play_ban_sound(self):
        self._play_notification_sound(self.ban_sound_path, "ban")

    def play_competition_sound(self):
        """Falls back to mention sound if no dedicated file is present."""
        path = self.competition_sound_path or self.mention_sound_path
        self._play_notification_sound(path, "competition")

    def on_voice_input_enabled_toggled(self, enabled: bool):
        mic = getattr(self, "mic_button", None)
        if mic is None:
            return
        mic.setVisible(enabled)
        if not enabled:
            self.voice_input.stop()
