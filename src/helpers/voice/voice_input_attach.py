"""Wire VoiceInputEngine + MicButton into ChatWindow with minimal edits.

Call from ChatWindow._init_ui() after send_button is created:

    from helpers.voice.voice_input_attach import install_voice_input
    install_voice_input(self)

And from ChatWindow.closeEvent() before accept:

    if getattr(self, "voice_input", None):
        self.voice_input.shutdown()
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLineEdit

from helpers.voice.voice_input import VoiceInputEngine, resolve_device
from components.mic_button import MicButton
from helpers.translate import tr


def _cfg_get(config, *keys, default=None):
    value = config.get(*keys) if config else None
    return default if value is None else value


def install_voice_input(window) -> MicButton:
    """Create engine + button, insert next to Send, persist the selected microphone."""
    config = window.config
    icons_path = window.icons_path

    icon_size = 30
    button_size = 48
    btn_cfg = _cfg_get(config, "ui", "buttons") or {}
    if isinstance(btn_cfg, dict):
        icon_size = btn_cfg.get("icon_size", icon_size)
        button_size = btn_cfg.get("button_size", button_size)

    saved_name = _cfg_get(config, "voice_input", "device_name", default=None)
    saved_index = _cfg_get(config, "voice_input", "device_id", default=None)

    engine = VoiceInputEngine(parent=window)
    engine.set_device_index(resolve_device(saved_name, saved_index))

    mic = MicButton(icons_path, icon_size=icon_size, button_size=button_size, parent=window)
    mic.set_device(saved_name, saved_index)

    # [input] [mic] [send] [emoji]
    layout = window.input_top_layout
    send = getattr(window, "send_button", None)
    if send is not None:
        layout.insertWidget(layout.indexOf(send), mic)
    else:
        layout.addWidget(mic)

    window.voice_input = engine
    window.mic_button = mic
    window._voice_latched = False
    window._voice_base = None  # field text before the current live utterance

    def _target_field() -> QLineEdit | None:
        getter = getattr(window, "_active_input_field", None)
        field = getter() if callable(getter) else getattr(window, "input_field", None)
        return field if isinstance(field, QLineEdit) else None

    def _focus_end(field: QLineEdit | None = None):
        field = field or _target_field()
        if field is None:
            return
        field.setFocus(Qt.FocusReason.OtherFocusReason)
        field.setCursorPosition(len(field.text()))
        # Keep the caret (right edge of the text) in view.
        try:
            field.deselect()
        except Exception:
            pass

    def _base_for(field: QLineEdit) -> str:
        current = field.text()
        base = getattr(window, "_voice_base", None)
        if base is None or not current.startswith(base):
            window._voice_base = current
        return window._voice_base

    def _put(text: str, commit: bool):
        field = _target_field()
        if field is None or not text:
            _focus_end(field)
            return
        base = _base_for(field)
        sep = "" if (not base or base.endswith(" ")) else " "
        new = base + sep + text.strip()
        field.setText(new)
        if commit:
            window._voice_base = new
        _focus_end(field)

    def _start():
        engine.start()
        mic.set_listening(True)
        field = _target_field()
        if field is not None:
            window._voice_base = field.text()
        QTimer.singleShot(0, _focus_end)

    def _stop():
        engine.stop()
        mic.set_listening(False)
        mic.set_latched(False)
        window._voice_latched = False
        window._voice_base = None
        QTimer.singleShot(0, _focus_end)

    def on_hold_started():
        _start()

    def on_hold_stopped():
        if window._voice_latched:
            QTimer.singleShot(0, _focus_end)
            return
        _stop()

    def start_voice_ptt():
        """Ctrl+Space press: push-to-talk. No-op if already listening (latch)."""
        window._voice_ptt_held = True
        if engine.listening:
            QTimer.singleShot(0, _focus_end)
            return
        _start()

    def stop_voice_ptt():
        """Ctrl+Space release. Leaves click-latch running."""
        held = getattr(window, "_voice_ptt_held", False)
        window._voice_ptt_held = False
        if not held:
            return
        if window._voice_latched:
            QTimer.singleShot(0, _focus_end)
            return
        _stop()

    window.start_voice_ptt = start_voice_ptt
    window.stop_voice_ptt = stop_voice_ptt
    window._voice_ptt_held = False

    def on_latch_toggled(latched: bool):
        window._voice_latched = latched
        mic.set_latched(latched)
        if latched:
            _start()
        else:
            _stop()

    def on_device(dev):
        if dev is None:
            config.set("voice_input", "device_name", value=None)
            config.set("voice_input", "device_id", value=None)
            engine.set_device_index(resolve_device(None, None))
            mic.set_device(None, None)
            return
        config.set("voice_input", "device_name", value=dev.name)
        config.set("voice_input", "device_id", value=dev.index)
        engine.set_device_index(dev.index)
        mic.set_device(dev.name, dev.index)

    engine.level_changed.connect(mic.set_level)
    engine.draft_ready.connect(lambda t: _put(t, commit=False))
    engine.text_ready.connect(lambda t: _put(t, commit=True))
    engine.state_changed.connect(
        lambda s: mic.set_status_hint(
            tr("Recognizing…", "Распознавание…") if s == "recognizing" else ""
        )
    )
    engine.error.connect(lambda m: mic.set_status_hint(m))

    mic.hold_started.connect(on_hold_started)
    mic.hold_stopped.connect(on_hold_stopped)
    mic.latch_toggled.connect(on_latch_toggled)
    mic.device_chosen.connect(on_device)

    return mic
