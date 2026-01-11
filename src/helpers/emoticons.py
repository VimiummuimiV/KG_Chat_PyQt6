"""Emoticon manager for loading and managing animated emoticons"""
from pathlib import Path
from typing import Dict, Optional
import re


class EmoticonManager:
    """Manage emoticons from multiple directories with theme support"""
    
    def __init__(self, emoticons_base_path: Path, is_dark_theme: bool = True):
        self.emoticons_base_path = emoticons_base_path
        self.is_dark_theme = is_dark_theme
        self.emoticon_map: Dict[str, Path] = {}
        self._load_emoticons(verbose=True)
    
    def set_theme(self, is_dark: bool):
        """Update theme and reload emoticons"""
        if self.is_dark_theme != is_dark:
            self.is_dark_theme = is_dark
            self._load_emoticons(verbose=False)
    
    def _load_emoticons(self, verbose: bool = False):
        """Scan all emoticon directories and build name -> path mapping with theme support"""
        self.emoticon_map.clear()
        
        if not self.emoticons_base_path.exists():
            if verbose:
                print(f"⚠️ Emoticons directory not found: {self.emoticons_base_path}")
            return
        
        theme_folder = "dark" if self.is_dark_theme else "light"
        
        def load_from_dir(directory: Path):
            """Load emoticons from a directory, checking for theme folders first"""
            theme_dir = directory / theme_folder
            has_themes = (directory / "dark").exists() and (directory / "light").exists()
            
            if has_themes:
                # Load theme-specific emoticons
                for f in theme_dir.glob("*.gif"):
                    self.emoticon_map[f.stem.lower()] = f
            else:
                # Load universal emoticons
                for f in directory.glob("*.gif"):
                    self.emoticon_map[f.stem.lower()] = f
                # Recursively check subdirectories
                for subdir in directory.iterdir():
                    if subdir.is_dir():
                        load_from_dir(subdir)
        
        # Scan all group directories
        for group_dir in self.emoticons_base_path.iterdir():
            if group_dir.is_dir():
                load_from_dir(group_dir)
        
        if verbose:
            print(f"📦 Loaded {len(self.emoticon_map)} emoticons for {'dark' if self.is_dark_theme else 'light'} theme")
    
    def get_emoticon_path(self, name: str) -> Optional[Path]:
        """Get path for emoticon by name (case-insensitive)"""
        return self.emoticon_map.get(name.lower())
    
    def has_emoticon(self, name: str) -> bool:
        """Check if emoticon exists"""
        return name.lower() in self.emoticon_map
    
    def parse_emoticons(self, text: str) -> list:
        """
        Parse text and return list of segments with emoticons marked.
        Returns list of tuples: (type, content) where type is 'text' or 'emoticon'
        
        Example:
        "Hello :smile: world :biggrin:" -> 
        [('text', 'Hello '), ('emoticon', 'smile'), ('text', ' world '), ('emoticon', 'biggrin')]
        """
        segments = []
        pattern = r':([a-zA-Z0-9_-]+):'
        last_end = 0
        
        for match in re.finditer(pattern, text):
            emoticon_name = match.group(1)
            
            # Add text before emoticon
            if match.start() > last_end:
                segments.append(('text', text[last_end:match.start()]))
            
            # Add emoticon if it exists
            if self.has_emoticon(emoticon_name):
                segments.append(('emoticon', emoticon_name))
            else:
                # Keep original text if emoticon not found
                segments.append(('text', match.group(0)))
            
            last_end = match.end()
        
        # Add remaining text
        if last_end < len(text):
            segments.append(('text', text[last_end:]))
        
        return segments if segments else [('text', text)]