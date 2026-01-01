"""Scale management and UI controls."""
from pathlib import Path
import flet as ft


SCALE_FILE = Path.home() / ".kg_chat_scale"


def load_scale() -> int:
    """Load saved scale value or default to 100."""
    try:
        with open(SCALE_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 100


def save_scale(value: int):
    """Save scale value to home directory."""
    try:
        with open(SCALE_FILE, "w") as f:
            f.write(str(int(value)))
    except:
        pass


def build_scale_controls(on_scale_change_callback=None) -> tuple:
    """Build scale slider and label.
    
    Args:
        on_scale_change_callback: callable(scale_value) when slider changes
    
    Returns:
        (scale_slider, scale_label, initial_scale_value)
    """
    initial_scale = load_scale()
    
    scale_label = ft.Text(f"{initial_scale}%", size=11, width=40)
    
    def on_scale_change(e):
        value = int(e.control.value)
        scale_label.value = f"{value}%"
        save_scale(value)
        if on_scale_change_callback:
            on_scale_change_callback(value)
    
    scale_slider = ft.Slider(
        min=70,
        max=150,
        value=initial_scale,
        divisions=80,
        on_change=on_scale_change,
        width=120
    )
    
    return scale_slider, scale_label, initial_scale
