"""Emoticon manager for loading and managing animated emoticons"""
from pathlib import Path
from typing import Dict, Optional
import re


class EmoticonManager:
    """Manage emoticons from multiple directories"""
    
    def __init__(self, emoticons_base_path: Path):
        self.emoticons_base_path = emoticons_base_path
        self.emoticon_map: Dict[str, Path] = {}
        self._load_emoticons()
    
    def _load_emoticons(self):
        """Scan all emoticon directories and build name -> path mapping"""
        if not self.emoticons_base_path.exists():
            print(f"⚠️ Emoticons directory not found: {self.emoticons_base_path}")
            return
        
        # Scan all subdirectories (Army, Boys, Christmas, Girls, Halloween, Inlove, etc.)
        for group_dir in self.emoticons_base_path.iterdir():
            if not group_dir.is_dir():
                continue
            
            # Scan all GIF files in this group
            for emoticon_file in group_dir.glob("*.gif"):
                # Use filename without extension as emoticon name
                emoticon_name = emoticon_file.stem.lower()
                
                # Store path (overwrites if duplicate names exist across groups)
                self.emoticon_map[emoticon_name] = emoticon_file
        
        print(f"📦 Loaded {len(self.emoticon_map)} emoticons from {self.emoticons_base_path}")
    
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