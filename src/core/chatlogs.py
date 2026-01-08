import requests
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass
from bs4 import BeautifulSoup


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
    MAX_FILE_SIZE_MB = 10  # Maximum file size in MB
    
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
    
    def fetch_log(self, date: Optional[str] = None) -> str:
        """Fetch chatlog HTML for a specific date (YYYY-MM-DD)
        
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
        
        url = f"{self.BASE_URL}/{date}.html"
        
        try:
            response = self.session.get(url, timeout=10, stream=True)
            
            # Check for 404
            if response.status_code == 404:
                raise ChatlogNotFoundError(f"Chatlog not found for date {date}")
            
            response.raise_for_status()
            
            # Check file size before loading
            content_length = response.headers.get('content-length')
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
                    return response.text, True  # Return (text, was_truncated)
            
            response.encoding = 'utf-8'
            return response.text, False  # Return (text, was_truncated)
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
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
            
            timestamp = timestamp.strip('[] ')  # Remove [], spaces
            
            # Get username
            font_tag = ts_tag.find_next('font', class_='mn')
            if not font_tag:
                continue
            
            username = font_tag.get_text().strip('<> ')  # Remove <>, spaces
            
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
    
    def get_messages(self, date: Optional[str] = None) -> tuple[List[ChatMessage], bool]:
        """Get all messages for a specific date (YYYY-MM-DD)
        
        Returns:
            tuple: (messages, was_truncated)
        
        Raises:
            ChatlogNotFoundError: If chatlog doesn't exist
            ValueError: If date is before minimum date
        """
        html, was_truncated = self.fetch_log(date)
        messages = self.parse_messages(html)
        return messages, was_truncated


if __name__ == "__main__":
    parser = ChatlogsParser()
