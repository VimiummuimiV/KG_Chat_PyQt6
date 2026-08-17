"""Voice Engine for TTS (Text-to-Speech)"""
import os
import re
import tempfile
import threading
import time
from queue import Queue
from typing import Optional

from playsound3 import playsound
from gtts import gTTS


def clean_text_for_tts(text: str) -> str:
    """Clean text for TTS by removing symbols, URLs, and punctuation"""
    # Extract domain from URLs (e.g., "https://mail.google.com/path" -> "mail.google.com")
    text = re.sub(
        r'https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})(?:/[^\s]*)?',
        r'\1',
        text,
    )
    
    # Convert hyphens, minus signs, and underscores to spaces for natural pauses
    text = re.sub(r'[-−_]', ' ', text)
    
    # Remove special characters/symbols but KEEP periods and commas for natural pauses
    text = re.sub(r'[:;@"#$%&\'()*+/<=>[\\\]^`{|}~]', '', text)
    
    # Collapse multiple spaces into one and remove leading/trailing spaces
    text = ' '.join(text.split()).strip()
    
    return text


class VoiceEngine:
    """Manages TTS playback with queuing support"""

    def __init__(self):
        self.enabled = False
        self.queue = Queue()
        self.last_username = None
        self.worker = None
        self.pronunciation_manager = None

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        if enabled and (not self.worker or not self.worker.is_alive()):
            self.worker = threading.Thread(target=self._process_queue, daemon=True)
            self.worker.start()
        elif not enabled:
            self._clear_queue()

    def set_pronunciation_manager(self, pronunciation_manager):
        """Set the pronunciation manager for username replacements"""
        self.pronunciation_manager = pronunciation_manager

    def _process_queue(self):
        while True:
            try:
                item = self.queue.get()
                if item is None:
                    break
                if self.enabled:
                    text, lang = item
                    self._speak(text, lang)
                self.queue.task_done()
            except Exception as e:
                print(f"TTS error: {e}")

    def _speak(self, text: str, lang: str):
        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                temp_file_path = temp_file.name
                gTTS(text=text, lang=lang, slow=False).write_to_fp(temp_file)
            time.sleep(0.05)
            playsound(temp_file_path, block=True)
        except Exception as e:
            print(f"TTS playback error: {e}")
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    time.sleep(0.1)
                    os.unlink(temp_file_path)
                except Exception as e:
                    print(f"Temp file cleanup error: {e}")

    def _clear_queue(self):
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except Exception:
                break

    def speak_message(
        self,
        username: str,
        message: str,
        my_username: str,
        is_initial: bool = False,
        is_private: bool = False,
        is_ban: bool = False,
        is_system: bool = False,
    ):
        """Speak a message with appropriate verb based on message type.

        - Ban: always «ультует»
        - Private / mention: always «обращается»
        - System (/me): no announcement
        - Regular: «пишет» only when username changes
        """
        if not self.enabled or is_initial:
            return

        is_mention = my_username.lower() in message.lower()
       
        # Get pronunciation for username if manager is available
        spoken_username = username
        if self.pronunciation_manager:
            spoken_username = self.pronunciation_manager.get_pronunciation(username)
       
        # Clean the message for natural TTS reading
        cleaned_message = clean_text_for_tts(message)
        
        # Split message into language chunks (Russian vs English)
        chunks = []
        current_chunk = []
        current_lang = None

        for word in cleaned_message.split():
            # Detect language of this word
            is_cyrillic = any('\u0400' <= c <= '\u04FF' for c in word)
            is_digit_only = word.isdigit() or all(c.isdigit() or c in '.,' for c in word)

            # Digits are ALWAYS pronounced in Russian
            if is_digit_only:
                word_lang = 'ru'
            elif is_cyrillic:
                word_lang = 'ru'
            else:
                word_lang = 'en'

            if current_lang is None:
                current_lang = word_lang

            if word_lang == current_lang:
                current_chunk.append(word)
            else:
                # Language changed, save current chunk and start new one
                if current_chunk:
                    chunks.append((' '.join(current_chunk), current_lang))
                current_chunk = [word]
                current_lang = word_lang
        
        # Add last chunk
        if current_chunk:
            chunks.append((' '.join(current_chunk), current_lang))
        
        # Determine if we need to announce the username
        announce_username = False
        verb = ''

        if is_system:
            # System message (/me): don't announce username, message already contains it
            # e.g., "* username does something" - just read as-is
            announce_username = False
        elif is_ban:
            # Ban message: always announce with "ультует"
            verb = 'ультует'
            announce_username = True
        elif is_private or is_mention:
            # Private message or mention: ALWAYS announce with "обращается"
            verb = 'обращается'
            announce_username = True
        elif username != self.last_username:
            # Regular message: announce with "пишет" only when username changes
            verb = 'пишет'
            announce_username = True
            self.last_username = username
        
        # Prepend username announcement if needed
        if announce_username and chunks:
            # Username announcement: verb is ALWAYS in Russian
            # Username is in Russian if it contains Cyrillic, otherwise English
            if any('\u0400' <= c <= '\u04FF' for c in spoken_username):
                # Russian username - announce everything in Russian
                chunks.insert(0, (f'{spoken_username} {verb}.', 'ru'))
            else:
                # English username - username in English, verb in Russian
                chunks.insert(0, (spoken_username, 'en'))
                chunks.insert(1, (f'{verb}.', 'ru'))

        # Queue each chunk separately with its language
        for text, lang in chunks:
            self.queue.put((text, lang))

    def shutdown(self):
        self.enabled = False
        self._clear_queue()
        if self.worker:
            self.queue.put(None)


_voice_engine: Optional[VoiceEngine] = None


def get_voice_engine() -> VoiceEngine:
    global _voice_engine
    if _voice_engine is None:
        _voice_engine = VoiceEngine()
    return _voice_engine


# One effect at a time: previous sound is stopped before a new one starts.
_sound_lock = threading.Lock()
_sound_obj = None


def cancel_current_sound():
    """Stop the effect currently playing, if any."""
    global _sound_obj
    with _sound_lock:
        sound = _sound_obj
        _sound_obj = None
    if sound is None:
        return
    try:
        sound.stop()
    except Exception:
        pass


def play_sound(sound_path: str, volume: float = 1.0, config=None, force: bool = False):
    """Play a short effect. Stops any previous effect first (no stacking).

    force=True skips the effects_enabled check (settings preview).
    """
    if volume == 0.0 or not sound_path:
        return

    if config and not force:
        if config.get('sound', 'effects_enabled') is False:
            return

    def _play():
        global _sound_obj
        with _sound_lock:
            # Stop previous without nested lock (already held)
            prev = _sound_obj
            _sound_obj = None
            if prev is not None:
                try:
                    prev.stop()
                except Exception:
                    pass
            try:
                # block=False → returns a Sound object with .stop() / .wait() / .is_alive()
                sound = playsound(sound_path, block=False)
                _sound_obj = sound
            except Exception as e:
                print(f'Sound error: {e}')
                try:
                    from PyQt6.QtWidgets import QApplication
                    app = QApplication.instance()
                    if app:
                        app.beep()
                except Exception:
                    pass
                return

        # Wait outside the lock so a new play_sound() can interrupt this one.
        try:
            sound.wait()
        except Exception:
            pass
        finally:
            with _sound_lock:
                if _sound_obj is sound:
                    _sound_obj = None

    threading.Thread(target=_play, daemon=True).start()
