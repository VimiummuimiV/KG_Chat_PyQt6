"""Voice input: capture, level meter, speech-to-text.

Dependencies:
    pip install sounddevice numpy SpeechRecognition

Recognition: Google Web Speech via SpeechRecognition (needs network).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal


SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
BLOCK_MS = 40
BLOCKSIZE = SAMPLE_RATE * BLOCK_MS // 1000

# Energy VAD (int16 RMS). Tuned for speech at typical headset gain.
SPEECH_RMS = 450
# Short breaths must not become a new "sentence" — Google capitalizes
# every request, so a 0.4s split turns commas into " Вот".
SILENCE_TO_COMMIT_S = 0.85
MAX_UTTERANCE_S = 12.0
MIN_UTTERANCE_S = 0.30
DRAFT_EVERY_S = 0.85
DRAFT_FIRST_S = 0.55

LANG_RU = "ru-RU"
LANG_EN = "en-US"
LANG_AUTO = "auto"

SUPPORTED_LANGUAGES = (LANG_RU, LANG_EN, LANG_AUTO)


def _sd():
    import sounddevice as sd
    return sd


def _np():
    import numpy as np
    return np


@dataclass
class InputDevice:
    index: int
    name: str
    hostapi: str
    is_default: bool

    def label(self) -> str:
        extra = f" [{self.hostapi}]" if self.hostapi else ""
        suffix = "  ●" if self.is_default else ""
        return f"{self.name}{extra}{suffix}"


def list_input_devices() -> list[InputDevice]:
    """Every PortAudio input endpoint. Names are whatever the host API reports
    (MME on Windows is capped at 31 characters — that is not our truncation)."""
    try:
        sd = _sd()
    except Exception:
        return []

    devices: list[InputDevice] = []
    try:
        default_in = sd.default.device[0] if sd.default.device else None
        hostapis = sd.query_hostapis()
        for i, info in enumerate(sd.query_devices()):
            if int(info.get("max_input_channels") or 0) <= 0:
                continue
            host = ""
            try:
                host = str(hostapis[info["hostapi"]]["name"])
            except Exception:
                pass
            devices.append(
                InputDevice(
                    index=i,
                    name=str(info.get("name") or f"Device {i}"),
                    hostapi=host,
                    is_default=(i == default_in),
                )
            )
    except Exception:
        return []
    return devices


def resolve_device(saved_name: Optional[str], saved_index: Optional[int]) -> Optional[int]:
    """Prefer matching by name; fall back to index; else default."""
    devices = list_input_devices()
    if not devices:
        return None
    if saved_name:
        for d in devices:
            if d.name == saved_name:
                return d.index
        # Old configs may store an MME-truncated prefix of a longer name.
        for d in devices:
            if d.name.startswith(saved_name.rstrip()) or saved_name.startswith(d.name.rstrip()):
                return d.index
    if saved_index is not None:
        for d in devices:
            if d.index == saved_index:
                return d.index
    for d in devices:
        if d.is_default:
            return d.index
    return devices[0].index


def _rms_int16(block) -> float:
    np = _np()
    if block.size == 0:
        return 0.0
    data = block.astype(np.float64)
    return float(np.sqrt(np.mean(data * data)))


def _level_from_rms(rms: float) -> float:
    # Map typical speech RMS onto 0..1 with headroom before clip (int16 max ~32767).
    # ~800 quiet, ~2500 conversational, ~8000 loud, ~20000 clipping.
    if rms <= 0:
        return 0.0
    import math
    norm = math.log10(max(rms, 1.0)) / math.log10(20000.0)
    return max(0.0, min(1.0, norm))


def recognize_pcm(pcm: bytes, language: str = LANG_AUTO, fast: bool = False) -> str:
    """Google Web Speech. `fast` unused."""
    if not pcm or len(pcm) < SAMPLE_RATE * 2 * MIN_UTTERANCE_S:
        return ""
    try:
        import speech_recognition as sr
    except Exception as e:
        raise RuntimeError(
            "SpeechRecognition is not installed. pip install SpeechRecognition"
        ) from e

    audio = sr.AudioData(pcm, SAMPLE_RATE, 2)

    def one(lang: str) -> str:
        rec = sr.Recognizer()
        rec.energy_threshold = 200
        rec.dynamic_energy_threshold = False
        try:
            return (rec.recognize_google(audio, language=lang) or "").strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            raise RuntimeError(f"STT request failed: {e}") from e

    return one(LANG_RU if language != LANG_EN else LANG_EN)


class _CaptureThread(QThread):
    """Pulls mic audio, emits level, slices utterances by VAD."""

    level = pyqtSignal(float)
    utterance = pyqtSignal(bytes)
    preview = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, device_index: Optional[int], parent=None):
        super().__init__(parent)
        self._device_index = device_index
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            sd = _sd()
            np = _np()
        except Exception:
            self.failed.emit(
                "Install audio deps: pip install sounddevice numpy SpeechRecognition"
            )
            return

        speech_chunks: list = []
        speaking = False
        silence_s = 0.0
        speech_s = 0.0
        last_draft_at = 0.0
        sent_first_draft = False
        smooth = 0.0

        def emit_preview():
            if speech_chunks and speech_s >= MIN_UTTERANCE_S:
                self.preview.emit(np.concatenate(speech_chunks).tobytes())

        def flush():
            nonlocal speech_chunks, speaking, silence_s, speech_s
            nonlocal last_draft_at, sent_first_draft
            if speech_chunks and speech_s >= MIN_UTTERANCE_S:
                pcm = np.concatenate(speech_chunks).tobytes()
                self.utterance.emit(pcm)
            speech_chunks = []
            speaking = False
            silence_s = 0.0
            speech_s = 0.0
            last_draft_at = 0.0
            sent_first_draft = False

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=BLOCKSIZE,
                device=self._device_index,
            ) as stream:
                while not self._stop.is_set():
                    block, overflowed = stream.read(BLOCKSIZE)
                    if overflowed:
                        pass
                    mono = block[:, 0] if block.ndim > 1 else block
                    rms = _rms_int16(mono)
                    instant = _level_from_rms(rms)
                    smooth = 0.65 * smooth + 0.35 * instant
                    self.level.emit(smooth)

                    is_speech = rms >= SPEECH_RMS
                    if is_speech:
                        speech_chunks.append(np.ascontiguousarray(mono))
                        speaking = True
                        silence_s = 0.0
                        speech_s += BLOCK_MS / 1000.0
                        if not sent_first_draft and speech_s >= DRAFT_FIRST_S:
                            emit_preview()
                            sent_first_draft = True
                            last_draft_at = speech_s
                        elif speech_s - last_draft_at >= DRAFT_EVERY_S:
                            emit_preview()
                            last_draft_at = speech_s
                        if speech_s >= MAX_UTTERANCE_S:
                            flush()
                    elif speaking:
                        speech_chunks.append(np.ascontiguousarray(mono))
                        silence_s += BLOCK_MS / 1000.0
                        speech_s += BLOCK_MS / 1000.0
                        if silence_s >= SILENCE_TO_COMMIT_S:
                            flush()
        except Exception as e:
            self.failed.emit(str(e))
            return

        # Release: commit whatever was buffered
        try:
            np = _np()
            if speech_chunks and speech_s >= MIN_UTTERANCE_S:
                self.utterance.emit(np.concatenate(speech_chunks).tobytes())
        except Exception:
            pass


class _RecognizeWorker(QThread):
    finished_text = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, pcm: bytes, language: str, parent=None, fast: bool = False):
        super().__init__(parent)
        self._pcm = pcm
        self._language = language
        self._fast = fast

    def run(self):
        try:
            text = recognize_pcm(self._pcm, self._language, fast=self._fast)
            self.finished_text.emit(text)
        except Exception as e:
            self.failed.emit(str(e))


class VoiceInputEngine(QObject):
    """Owns capture + recognition. All signals are GUI-thread safe."""

    level_changed = pyqtSignal(float)
    text_ready = pyqtSignal(str)
    draft_ready = pyqtSignal(str)
    state_changed = pyqtSignal(str)  # idle | listening | recognizing | error
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._capture: Optional[_CaptureThread] = None
        self._workers: list[_RecognizeWorker] = []
        self._preview_worker: Optional[_RecognizeWorker] = None
        self._language = LANG_RU
        self._device_index: Optional[int] = None
        self._listening = False
        self._state = "idle"

    @property
    def listening(self) -> bool:
        return self._listening

    @property
    def state(self) -> str:
        return self._state

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str):
        if language in SUPPORTED_LANGUAGES:
            self._language = language

    def set_device_index(self, index: Optional[int]):
        self._device_index = index
        if self._listening:
            # Restart on the new device without dropping latch/PTT intent.
            self.stop()
            self.start()

    def start(self):
        if self._listening:
            return
        self._listening = True
        self._set_state("listening")
        cap = _CaptureThread(self._device_index, parent=self)
        cap.level.connect(self.level_changed)
        cap.utterance.connect(self._on_utterance)
        cap.preview.connect(self._on_preview)
        cap.failed.connect(self._on_capture_failed)
        cap.finished.connect(self._on_capture_finished)
        self._capture = cap
        cap.start()

    def stop(self):
        self._listening = False
        cap = self._capture
        self._capture = None
        if cap is not None:
            cap.stop()
            cap.wait(800)
            cap.deleteLater()
        self.level_changed.emit(0.0)
        if not self._workers:
            self._set_state("idle")

    def shutdown(self):
        self.stop()
        for w in list(self._workers):
            w.wait(400)

    def _set_state(self, state: str):
        self._state = state
        self.state_changed.emit(state)

    def _on_capture_failed(self, message: str):
        self._listening = False
        self._set_state("error")
        self.error.emit(message)
        self.level_changed.emit(0.0)

    def _on_capture_finished(self):
        if not self._listening and not self._workers:
            self._set_state("idle")

    def _on_preview(self, pcm: bytes):
        if not pcm or self._preview_worker is not None:
            return
        worker = _RecognizeWorker(pcm, self._language, parent=self, fast=True)
        worker.finished_text.connect(lambda text, w=worker: self._on_preview_done(w, text))
        worker.failed.connect(lambda m, w=worker: self._on_preview_failed(w, m))
        self._preview_worker = worker
        worker.start()

    def _on_preview_done(self, worker: _RecognizeWorker, text: str):
        if self._preview_worker is worker:
            self._preview_worker = None
        worker.deleteLater()
        if text:
            self.draft_ready.emit(text)

    def _on_preview_failed(self, worker: _RecognizeWorker, message: str):
        self._on_preview_done(worker, "")
        if message:
            print(f"🎤 STT preview: {message}")
            self.error.emit(message)

    def _on_utterance(self, pcm: bytes):
        if not pcm:
            return
        self._set_state("recognizing")
        worker = _RecognizeWorker(pcm, self._language, parent=self)
        worker.finished_text.connect(lambda text, w=worker: self._on_recognized(w, text))
        worker.failed.connect(lambda m, w=worker: self._on_recognize_failed(w, m))
        self._workers.append(worker)
        worker.start()

    def _drop_worker(self, worker: _RecognizeWorker):
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def _on_recognized(self, worker: _RecognizeWorker, text: str):
        self._drop_worker(worker)
        if text:
            self.text_ready.emit(text)
        if self._listening:
            self._set_state("listening")
        elif not self._workers:
            self._set_state("idle")

    def _on_recognize_failed(self, worker: _RecognizeWorker, message: str):
        self._drop_worker(worker)
        self.error.emit(message)
        if self._listening:
            self._set_state("listening")
        elif not self._workers:
            self._set_state("idle")
