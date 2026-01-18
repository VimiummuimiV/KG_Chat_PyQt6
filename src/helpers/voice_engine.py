"""Voice Engine for TTS (Text-to-Speech) with volume control"""
import threading
from queue import Queue
from typing import Optional
from gtts import gTTS
from io import BytesIO
import pygame
import tempfile
import os

class VoiceEngine:
    """Manages TTS playback with queuing support and volume control"""
   
    def __init__(self, tts_volume: float = 1.0, notification_volume: float = 1.0):
        """
        Initialize voice engine
       
        Args:
            tts_volume: TTS playback volume (0.0 to 1.0, default 1.0)
            notification_volume: Notification sound volume (0.0 to 1.0, default 1.0)
        """
        self.enabled = False
        self.queue = Queue()
        self.last_username = None
        self.worker = None
        self.tts_volume = max(0.0, min(1.0, tts_volume))
        self.notification_volume = max(0.0, min(1.0, notification_volume))
        
        # Initialize pygame mixer
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
       
    def set_enabled(self, enabled: bool):
        """Enable or disable TTS"""
        self.enabled = enabled
        if enabled and (not self.worker or not self.worker.is_alive()):
            self.worker = threading.Thread(target=self._process_queue, daemon=True)
            self.worker.start()
        elif not enabled:
            self._clear_queue()
   
    def set_tts_volume(self, volume: float):
        """
        Set TTS playback volume
       
        Args:
            volume: Volume level (0.0 = mute, 1.0 = normal)
        """
        self.tts_volume = max(0.0, min(1.0, volume))
   
    def set_notification_volume(self, volume: float):
        """
        Set notification sound volume
       
        Args:
            volume: Volume level (0.0 = mute, 1.0 = normal)
        """
        self.notification_volume = max(0.0, min(1.0, volume))
   
    def _process_queue(self):
        """Background worker to process TTS queue"""
        while True:
            try:
                item = self.queue.get()
                if item is None:  # Stop signal
                    break
                if self.enabled:
                    text, lang = item
                    self._speak(text, lang)
                self.queue.task_done()
            except Exception as e:
                print(f"TTS error: {e}")
   
    def _speak(self, text: str, lang: str):
        """Generate and play speech with volume control"""
        temp_file = None
        try:
            if self.tts_volume == 0.0:
                return  # Muted, don't play
            
            # Generate TTS audio
            audio_buffer = BytesIO()
            gTTS(text=text, lang=lang, slow=False).write_to_fp(audio_buffer)
            audio_buffer.seek(0)
           
            # Save to temporary file (pygame needs a file path)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                temp_file.write(audio_buffer.read())
                temp_path = temp_file.name
           
            # Load and play with pygame
            pygame.mixer.music.load(temp_path)
            pygame.mixer.music.set_volume(self.tts_volume)
            pygame.mixer.music.play()
           
            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
                
        except Exception as e:
            print(f"TTS playback error: {e}")
        finally:
            # Clean up temporary file
            if temp_file:
                try:
                    os.unlink(temp_path)
                except:
                    pass
   
    def _clear_queue(self):
        """Clear pending messages"""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except:
                break
   
    def speak_message(self, username: str, message: str, my_username: str, is_initial: bool = False):
        """Queue a message for TTS playback"""
        if not self.enabled or is_initial or self.tts_volume == 0.0:
            return
       
        # Build announcement text
        parts = []
        is_mention = my_username.lower() in message.lower()
       
        if username != self.last_username or is_mention:
            verb = "обращается" if is_mention else "пишет"
            parts.append(f"{username} {verb}")
            if not is_mention:  # Only update last_username if not a mention
                self.last_username = username
       
        parts.append(message)
       
        # Detect language and queue
        lang = 'ru' if any('\u0400' <= c <= '\u04FF' for c in message) else 'en'
        self.queue.put((". ".join(parts), lang))
   
    def shutdown(self):
        """Shutdown the voice engine"""
        self.enabled = False
        self._clear_queue()
        if self.worker:
            self.queue.put(None)  # Stop signal
        pygame.mixer.quit()


# Global singleton
_voice_engine: Optional[VoiceEngine] = None


def get_voice_engine() -> VoiceEngine:
    """Get or create global voice engine instance"""
    global _voice_engine
    if _voice_engine is None:
        _voice_engine = VoiceEngine()
    return _voice_engine


def play_sound(sound_path: str, volume: float = 1.0):
    """
    Play a sound file using pygame (non-blocking) with volume control
   
    Args:
        sound_path: Path to the sound file (MP3, WAV, OGG)
        volume: Volume level (0.0 = mute, 1.0 = normal)
    """
    try:
        # Clamp volume to valid range
        volume = max(0.0, min(1.0, volume))
       
        if volume == 0.0:
            return  # Muted, don't play
       
        # Load and play sound
        sound = pygame.mixer.Sound(sound_path)
        sound.set_volume(volume)
        sound.play()
        
    except Exception as e:
        print(f"Sound error: {e}")
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().beep()
        except:
            pass
