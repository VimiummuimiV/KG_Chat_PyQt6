"""Chatlog parser - core parsing logic with multiple modes and multithreading"""
from datetime import datetime, timedelta
from typing import List, Optional, Callable, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

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
    """Engine for parsing chatlogs with various modes and filters using multithreading"""
    def __init__(self, max_workers: int = 20):
        self.parser = ChatlogsParser()
        self.stop_requested = False
        self.max_workers = max_workers
        self._lock = threading.Lock()
    
    def stop(self):
        """Request stop of parsing"""
        self.stop_requested = True
    
    def reset_stop(self):
        """Reset stop flag"""
        self.stop_requested = False
    
    def _fetch_date(self, date_str: str, config: ParseConfig) -> Tuple[str, List[ChatMessage]]:
        try:
            # This will use cache if available, otherwise fetch from network
            messages, _, _ = self.parser.get_messages(date_str)
            
            if self.stop_requested:
                return date_str, []
            
            # Filter messages
            filtered = self._filter_messages(messages, config)
            
            return date_str, filtered
            
        except ChatlogNotFoundError:
            # Date has no chatlog (404)
            return date_str, []
        except Exception as e:
            print(f"Error parsing {date_str}: {e}")
            return date_str, []
    
    def parse(
        self,
        config: ParseConfig,
        progress_callback: Optional[Callable[[str, str, int], None]] = None,
        message_callback: Optional[Callable[[List[ChatMessage], str], None]] = None
    ) -> List[ChatMessage]:

        self.reset_stop()
        
        # Get date range
        from_date = datetime.strptime(config.from_date, '%Y-%m-%d').date()
        to_date = datetime.strptime(config.to_date, '%Y-%m-%d').date()
        
        # Calculate total days for progress calculation
        total_days = (to_date - from_date).days + 1
        
        # Generate list of all dates to process
        dates_to_process = []
        current_date = from_date
        while current_date <= to_date:
            dates_to_process.append(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)
        
        # Track progress
        completed_count = 0
        results_dict = {}  # Store results by date to maintain chronological order
        
        # Process dates in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks - each worker gets a different date
            future_to_date = {
                executor.submit(self._fetch_date, date_str, config): date_str
                for date_str in dates_to_process
            }
            
            # Process completed futures as they finish
            for future in as_completed(future_to_date):
                if self.stop_requested:
                    # Cancel remaining futures
                    for f in future_to_date:
                        f.cancel()
                    break
                
                try:
                    date_str, filtered = future.result()
                    
                    # Store result (keyed by date to maintain order)
                    results_dict[date_str] = filtered
                    
                    # Update progress (thread-safe)
                    with self._lock:
                        completed_count += 1
                        percent = int((completed_count / total_days) * 100)
                    
                    if progress_callback:
                        progress_callback(config.from_date, date_str, percent)
                    
                    # Incremental callback (if messages found)
                    if message_callback and filtered:
                        message_callback(filtered, date_str)
                    
                except Exception as e:
                    print(f"Error processing future: {e}")
        
        # Combine results in chronological order
        all_messages = []
        if not self.stop_requested:
            for date_str in dates_to_process:
                if date_str in results_dict:
                    all_messages.extend(results_dict[date_str])
        
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