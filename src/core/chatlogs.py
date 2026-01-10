import requests
from datetime import datetime
from typing import List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
from lxml import etree

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
    NOT_FOUND_SUFFIX = "_NotFound" # Suffix for 404 marker files
    TRUNCATED_SUFFIX = "_Truncated" # Suffix for truncated cache files (due to size)
   
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.cache_dir = get_data_dir("chatlogs")
   
    def _get_cache_path(self, date: str, truncated: bool = False) -> Path:
        """Get cache file path for a date"""
        suffix = self.TRUNCATED_SUFFIX if truncated else ""
        return self.cache_dir / f"{date}{suffix}.html"
   
    def _get_not_found_path(self, date: str) -> Path:
        """Get not-found marker file path"""
        return self.cache_dir / f"{date}{self.NOT_FOUND_SUFFIX}.txt"
   
    def _is_cached(self, date: str) -> Tuple[bool, bool]:
        """Check cache, returns (is_cached, was_truncated)"""
        if self._get_cache_path(date, truncated=True).exists():
            return True, True
        if self._get_cache_path(date, truncated=False).exists():
            return True, False
        return False, False
   
    def _is_not_found(self, date: str) -> bool:
        """Check if previously marked as 404"""
        return self._get_not_found_path(date).exists()
   
    def _load_from_cache(self, date: str) -> Tuple[str, bool]:
        """Load from cache, returns (html, was_truncated)"""
        for truncated in (True, False):
            path = self._get_cache_path(date, truncated)
            if path.exists():
                return path.read_text(encoding='utf-8'), truncated
        return "", False
   
    def _save_to_cache(self, date: str, html: str, truncated: bool = False):
        """Save to cache (skip if today)"""
        if datetime.strptime(date, '%Y-%m-%d').date() >= datetime.now().date():
            return
        self._get_cache_path(date, truncated).write_text(html, encoding='utf-8')
   
    def _mark_not_found(self, date: str):
        """Mark as 404 (skip if today)"""
        if datetime.strptime(date, '%Y-%m-%d').date() >= datetime.now().date():
            return
        self._get_not_found_path(date).write_text(f"404 - Not found on {datetime.now().isoformat()}")
   
    def fetch_log(self, date: Optional[str] = None) -> Tuple[str, bool, bool]:
        """Fetch chatlog HTML for date (YYYY-MM-DD)
        
        Returns: (html, was_truncated, from_cache)
        Raises: ChatlogNotFoundError, ValueError
        """
        date = date or datetime.now().strftime('%Y-%m-%d')
       
        # Check minimum date
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        if date_obj < self.MIN_DATE:
            raise ValueError(f"Date cannot be before {self.MIN_DATE.strftime('%Y-%m-%d')}")
       
        # Check if already marked as not found
        if self._is_not_found(date):
            raise ChatlogNotFoundError(f"Chatlog not found for date {date} (cached 404)")
       
        # Check file cache
        is_cached, was_truncated = self._is_cached(date)
        if is_cached:
            html, was_truncated = self._load_from_cache(date)
            return html, was_truncated, True
       
        # Fetch from network
        url = f"{self.BASE_URL}/{date}.html"
        try:
            response = self.session.get(url, timeout=10, stream=True)
           
            if response.status_code == 404:
                self._mark_not_found(date)
                raise ChatlogNotFoundError(f"Chatlog not found for date {date}")
           
            response.raise_for_status()
            response.encoding = 'utf-8'
           
            # Handle large files
            was_truncated = False
            content_length = response.headers.get('content-length')
            
            if content_length and int(content_length) / (1024 * 1024) > self.MAX_FILE_SIZE_MB:
                max_bytes = int(self.MAX_FILE_SIZE_MB * 1024 * 1024)
                content = b''
                for chunk in response.iter_content(8192):
                    content += chunk
                    if len(content) >= max_bytes:
                        content = content[:max_bytes]
                        break
                html = content.decode('utf-8', errors='ignore')
                was_truncated = True
            else:
                html = response.text
           
            self._save_to_cache(date, html, truncated=was_truncated)
            return html, was_truncated, False
           
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response and e.response.status_code == 404:
                self._mark_not_found(date)
                raise ChatlogNotFoundError(f"Chatlog not found for date {date}")
            raise
   
    def parse_messages(self, html: str) -> List[ChatMessage]:
        """Parse messages from HTML using lxml
        
        Structure: <a class="ts" name="HH:MM:SS"/>
                   <font class="mn">&lt;user&gt;</font>text<br/>
        """
        parser = etree.HTMLParser(encoding='utf-8')
        tree = etree.fromstring(html.encode('utf-8'), parser)
        messages = []
        
        for ts_elem in tree.xpath('//a[@class="ts"]'):
            timestamp = ts_elem.get('name')
            if not timestamp:
                continue
            
            font_elems = ts_elem.xpath('following-sibling::font[@class="mn"][1]')
            if not font_elems:
                continue
            
            font_elem = font_elems[0]
            username = (font_elem.text or '').strip('<> ')
            if not username:
                continue
            
            # Collect message parts
            parts = [font_elem.tail] if font_elem.tail else []
            for sibling in font_elem.itersiblings():
                if sibling.tag == 'br':
                    break
                if sibling.tag == 'a':
                    parts.append(sibling.get('href', sibling.text or ''))
                elif sibling.text:
                    parts.append(sibling.text)
                if sibling.tail:
                    parts.append(sibling.tail)
            
            message = ''.join(parts).strip()
            if message:
                messages.append(ChatMessage(timestamp, username, message))
        
        return messages
   
    def get_messages(self, date: Optional[str] = None) -> Tuple[List[ChatMessage], bool, bool]:
        """Get parsed messages for date
        
        Returns: (messages, was_truncated, from_cache)
        Raises: ChatlogNotFoundError, ValueError
        """
        html, was_truncated, from_cache = self.fetch_log(date)
        return self.parse_messages(html), was_truncated, from_cache


if __name__ == "__main__":
    parser = ChatlogsParser()
