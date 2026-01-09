import requests
import os
import platform
from datetime import datetime
from typing import List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
from bs4 import BeautifulSoup

from helpers.data import get_data_dir

@dataclass
class ChatMessage:
    timestamp: str
    username: str
    message: str
   
    def __repr__(self):
        return f"{self.timestamp} {self.username}: {self.message}"

class ChatlogNotFoundError(Exception):
    """Raised when chatlog is not found (404)"""
    pass

class ChatlogsParser:
    BASE_URL = "https://klavogonki.ru/chatlogs"
    MIN_DATE = datetime(2012, 2, 12).date()
    MAX_FILE_SIZE_MB = 10 # Maximum file size in MB
    NOT_FOUND_PREFIX = "NotFound_" # Prefix for 404 marker files
    TRUNCATED_PREFIX = "Truncated_" # Prefix for truncated cache files (due to size)
   
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.cache_dir = get_data_dir("chatlogs")
   
    def _get_cache_path(self, date: str, truncated: bool = False) -> Path:
        """Get cache file path for a date"""
        prefix = self.TRUNCATED_PREFIX if truncated else ""
        return self.cache_dir / f"{prefix}{date}.html"
   
    def _get_not_found_path(self, date: str) -> Path:
        """Get not-found marker file path for a date"""
        return self.cache_dir / f"{self.NOT_FOUND_PREFIX}{date}.txt"
   
    def _is_cached(self, date: str) -> Tuple[bool, bool]:
        """Check if chatlog is cached
        
        Returns:
            tuple: (is_cached, was_truncated)
        """
        # Check for truncated version first
        if self._get_cache_path(date, truncated=True).exists():
            return True, True
        # Check for normal version
        if self._get_cache_path(date, truncated=False).exists():
            return True, False
        return False, False
   
    def _is_not_found(self, date: str) -> bool:
        """Check if chatlog was previously not found (404)"""
        return self._get_not_found_path(date).exists()
   
    def _load_from_cache(self, date: str) -> Tuple[str, bool]:
        """Load chatlog from cache
        
        Returns:
            tuple: (html_content, was_truncated)
        """
        # Try truncated version first
        truncated_path = self._get_cache_path(date, truncated=True)
        if truncated_path.exists():
            with open(truncated_path, 'r', encoding='utf-8') as f:
                return f.read(), True
        
        # Try normal version
        cache_path = self._get_cache_path(date, truncated=False)
        with open(cache_path, 'r', encoding='utf-8') as f:
            return f.read(), False
   
    def _save_to_cache(self, date: str, html: str, truncated: bool = False):
        """Save chatlog to cache (only if not today)"""
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        if date_obj >= datetime.now().date():
            return # Don't cache today or future dates
       
        cache_path = self._get_cache_path(date, truncated=truncated)
        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(html)
   
    def _mark_not_found(self, date: str):
        """Mark date as not found (only if not today)"""
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        if date_obj >= datetime.now().date():
            return # Don't mark today or future dates
       
        not_found_path = self._get_not_found_path(date)
        with open(not_found_path, 'w') as f:
            f.write(f"404 - Not found on {datetime.now().isoformat()}")
   
    def fetch_log(self, date: Optional[str] = None) -> Tuple[str, bool, bool]:
        """Fetch chatlog HTML for a specific date (YYYY-MM-DD)
       
        Returns:
            tuple: (html_content, was_truncated, from_cache)
       
        Raises:
            ChatlogNotFoundError: If chatlog doesn't exist (404)
            ValueError: If date is before minimum date
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
       
        # Check minimum date
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        if date_obj < self.MIN_DATE:
            raise ValueError(f"Date cannot be before {self.MIN_DATE.strftime('%Y-%m-%d')}")
       
        # Check if already marked as not found
        if self._is_not_found(date):
            raise ChatlogNotFoundError(f"Chatlog not found for date {date} (cached 404)")
       
        # Check cache
        is_cached, was_truncated = self._is_cached(date)
        if is_cached:
            html, was_truncated = self._load_from_cache(date)
            return html, was_truncated, True # From cache
       
        # Fetch from network
        url = f"{self.BASE_URL}/{date}.html"
       
        try:
            response = self.session.get(url, timeout=10, stream=True)
           
            # Check for 404
            if response.status_code == 404:
                self._mark_not_found(date)
                raise ChatlogNotFoundError(f"Chatlog not found for date {date}")
           
            response.raise_for_status()
           
            # Check file size before loading
            content_length = response.headers.get('content-length')
            was_truncated = False
           
            if content_length:
                size_mb = int(content_length) / (1024 * 1024)
                if size_mb > self.MAX_FILE_SIZE_MB:
                    # Read only up to limit
                    max_bytes = self.MAX_FILE_SIZE_MB * 1024 * 1024
                    content = b''
                    for chunk in response.iter_content(chunk_size=8192):
                        content += chunk
                        if len(content) >= max_bytes:
                            content = content[:max_bytes]
                            break
                    response._content = content
                    response.encoding = 'utf-8'
                    was_truncated = True
           
            response.encoding = 'utf-8'
            html = response.text
           
            # Save to cache with truncation flag (only if not today)
            self._save_to_cache(date, html, truncated=was_truncated)
           
            return html, was_truncated, False # Return from_cache=False
           
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                self._mark_not_found(date)
                raise ChatlogNotFoundError(f"Chatlog not found for date {date}")
            raise
   
    def parse_messages(self, html: str) -> List[ChatMessage]:
        """Parse messages from chatlog HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        messages = []
       
        for ts_tag in soup.find_all('a', class_='ts'):
            # Get timestamp
            timestamp = ts_tag.get('name')
            if not timestamp:
                continue
           
            timestamp = timestamp.strip('[] ') # Remove [], spaces
           
            # Get username
            font_tag = ts_tag.find_next('font', class_='mn')
            if not font_tag:
                continue
           
            username = font_tag.get_text().strip('<> ') # Remove <>, spaces
           
            # Get message text and URLs
            message = ''
            for sibling in font_tag.next_siblings:
                if sibling.name == 'br':
                    break
                if isinstance(sibling, str):
                    message += sibling
                elif sibling.name == 'a':
                    # Extract URL from anchor tag
                    href = sibling.get('href', '')
                    if href:
                        message += href
                    else:
                        # Fallback to anchor text if no href
                        message += sibling.get_text()
           
            message = message.strip()
            if message:
                messages.append(ChatMessage(timestamp, username, message))
       
        return messages
   
    def get_messages(self, date: Optional[str] = None) -> Tuple[List[ChatMessage], bool, bool]:
        """Get all messages for a specific date (YYYY-MM-DD)
       
        Returns:
            tuple: (messages, was_truncated, from_cache)
       
        Raises:
            ChatlogNotFoundError: If chatlog doesn't exist
            ValueError: If date is before minimum date
        """
        html, was_truncated, from_cache = self.fetch_log(date)
        messages = self.parse_messages(html)
        return messages, was_truncated, from_cache


if __name__ == "__main__":
    parser = ChatlogsParser()
