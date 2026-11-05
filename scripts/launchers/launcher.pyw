"""
KG Chat Launcher (Windows)
Double-click to run without console window
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Import and run
from src.main import main

if __name__ == "__main__":
    main()
