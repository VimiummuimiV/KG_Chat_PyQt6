"""Chatlog parser - core parsing logic with multiple modes"""
from datetime import datetime, timedelta
from typing import List, Optional, Callable, Set
from dataclasses import dataclass, field
from pathlib import Path

from core.chatlogs import ChatlogsParser, ChatlogNotFoundError, ChatMessage


@dataclass
class ParseConfig:
    """Configuration for parsing"""
    mode: str  # 'single', 'fromdate', 'range', 'fromstart', 'fromregistered', 'personalmentions'
    from_date: Optional[str] = None  # YYYY-MM-DD
    to_date: Optional[str] = None  # YYYY-MM-DD
    usernames: List[str] = field(default_factory=list)  # List of usernames to filter
    search_terms: List[str] = field(default_factory=list)  # Search terms for message content
    mention_keywords: List[str] = field(default_factory=list)  # Keywords for personal mentions mode


class ChatlogsParserEngine:
    """Engine for parsing chatlogs with various modes and filters"""
    
    def __init__(self):
        self.parser = ChatlogsParser()
        self.stop_requested = False
    
    def stop(self):
        """Request stop of parsing"""
        self.stop_requested = True
    
    def reset_stop(self):
        """Reset stop flag"""
        self.stop_requested = False
    
    def parse(
        self,
        config: ParseConfig,
        progress_callback: Optional[Callable[[str, str, int], None]] = None,
        message_callback: Optional[Callable[[List[ChatMessage], str], None]] = None
    ) -> List[ChatMessage]:
        """
        Parse chatlogs based on configuration
        
        Args:
            config: Parse configuration
            progress_callback: Called with (start_date, current_date, percent)
            message_callback: Called with (messages, date) for incremental display
        
        Returns:
            List of all filtered messages
        """
        self.reset_stop()
        all_messages = []
        
        # Get date range
        from_date = datetime.strptime(config.from_date, '%Y-%m-%d').date()
        to_date = datetime.strptime(config.to_date, '%Y-%m-%d').date()
        
        # Calculate total days for progress calculation
        total_days = (to_date - from_date).days + 1
        
        current_date = from_date
        
        while current_date <= to_date and not self.stop_requested:
            date_str = current_date.strftime('%Y-%m-%d')
            
            # Calculate progress based on days processed
            days_processed = (current_date - from_date).days + 1
            percent = int((days_processed / total_days) * 100)
            
            if progress_callback:
                progress_callback(config.from_date, date_str, percent)
            
            try:
                messages, _, _ = self.parser.get_messages(date_str)
                
                if self.stop_requested:
                    break
                
                # Filter messages
                filtered = self._filter_messages(messages, config)
                
                if self.stop_requested:
                    break
                
                all_messages.extend(filtered)
                
                # Incremental callback
                if message_callback and filtered:
                    message_callback(filtered, date_str)
                
            except ChatlogNotFoundError:
                pass  # Skip missing dates
            except Exception as e:
                print(f"Error parsing {date_str}: {e}")
            
            current_date += timedelta(days=1)
        
        return all_messages
    
    def _filter_messages(
        self,
        messages: List[ChatMessage],
        config: ParseConfig
    ) -> List[ChatMessage]:
        """Filter messages based on configuration"""
        if not messages:
            return []
        
        filtered = messages
        
        # Username filter
        if config.usernames:
            usernames_lower = [u.lower() for u in config.usernames]
            filtered = [
                msg for msg in filtered
                if msg.username.lower() in usernames_lower
            ]
        
        # Search terms filter (message content)
        if config.search_terms:
            search_terms_lower = [term.lower() for term in config.search_terms]
            filtered = [
                msg for msg in filtered
                if any(term in msg.message.lower() for term in search_terms_lower)
            ]
        
        # Mention keywords filter (for personal mentions mode)
        if config.mention_keywords:
            mention_keywords_lower = [kw.lower() for kw in config.mention_keywords]
            filtered = [
                msg for msg in filtered
                if any(kw in msg.message.lower() for kw in mention_keywords_lower)
            ]
        
        return filtered
    
    def count_messages_per_user(self, messages: List[ChatMessage]) -> dict:
        """Count messages per username"""
        from collections import Counter
        return Counter(msg.username for msg in messages)