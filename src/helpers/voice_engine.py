"""Voice Engine for TTS (Text-to-Speech)"""
import threading
from queue import Queue
from typing import Optional
import tempfile
import os
import time

from playsound3 import playsound
from gtts import gTTS


class VoiceEngine:
    """Manages TTS playback with queuing support"""
   
    def __init__(self):
        self.enabled = False
        self.queue = Queue()
        self.last_username = None
        self.worker = None
       
    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        if enabled and (not self.worker or not self.worker.is_alive()):
            self.worker = threading.Thread(target=self._process_queue, daemon=True)
            self.worker.start()
        elif not enabled:
            self._clear_queue()
   
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
            except:
                break
   
    def speak_message(self, username: str, message: str, my_username: str, is_initial: bool = False):
        if not self.enabled or is_initial:
            return
       
        parts = []
        is_mention = my_username.lower() in message.lower()
       
        if username != self.last_username or is_mention:
            verb = "обращается" if is_mention else "пишет"
            parts.append(f"{username} {verb}")
            if not is_mention:
                self.last_username = username
       
        parts.append(message)
       
        lang = 'ru' if any('\u0400' <= c <= '\u04FF' for c in message) else 'en'
        self.queue.put((". ".join(parts), lang))
   
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


def play_sound(sound_path: str, volume: float = 1.0):
    if volume == 0.0:
        return
        
    def _play():
        try:
            playsound(sound_path, block=False)
        except Exception as e:
            print(f"Sound error: {e}")
            try:
                from PyQt6.QtWidgets import QApplication
                QApplication.instance().beep()
            except:
                pass
    
    threading.Thread(target=_play, daemon=True).start()