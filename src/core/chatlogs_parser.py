"""Chatlog parser - SQLite database with multithreading for network fetches"""
from datetime import datetime, timedelta
from typing import List, Optional, Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from core.chatlogs import ChatlogsParser, ChatlogNotFoundError
from core.chatlogs_db import ChatMessage
from helpers.workers_calculator import WorkerCalculator


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
    """Engine for parsing chatlogs - uses SQLite DB and multithreading for network fetches"""
    
    def __init__(self, max_workers: Optional[int] = None):
        self.parser = ChatlogsParser()
        self.stop_requested = False
        
        # Calculate optimal workers if not provided
        if max_workers is None:
            max_workers, info = WorkerCalculator.calculate_optimal_workers()
            print(f"🔧 Auto-configured workers: {info}")
        else:
            print(f"🔧 Using {max_workers} workers")
        
        self.max_workers = max_workers
        self._lock = threading.Lock()
    
    def stop(self):
        """Request stop of parsing"""
        self.stop_requested = True
    
    def reset_stop(self):
        """Reset stop flag"""
        self.stop_requested = False
    
    def _fetch_date(self, date_str: str) -> tuple:
        """Fetch and cache a single date (network operation)"""
        try:
            html, was_truncated, _ = self.parser.fetch_log(date_str)
            messages = self.parser.parse_messages(html, date_str)
            self.parser.db.save_messages(date_str, messages, was_truncated)
            return date_str, messages, None
        except ChatlogNotFoundError:
            return date_str, [], None
        except Exception as e:
            return date_str, [], str(e)
    
    def parse(
        self,
        config: ParseConfig,
        progress_callback: Optional[Callable[[str, str, int], None]] = None,
        message_callback: Optional[Callable[[List[ChatMessage], str], None]] = None
    ) -> List[ChatMessage]:
        """Parse chatlogs with optimal strategy:
        - Use direct DB query if all dates are cached
        - Use multithreading only for network fetches of missing dates
        """
        self.reset_stop()
        
        # Get date range
        from_date = datetime.strptime(config.from_date, '%Y-%m-%d').date()
        to_date = datetime.strptime(config.to_date, '%Y-%m-%d').date()
        
        # Check which dates need to be fetched from network
        missing_dates = self.parser.db.get_missing_dates(
            config.from_date,
            config.to_date
        )
        
        total_days = (to_date - from_date).days + 1
        
        # If we have missing dates, fetch them with multithreading
        live_messages: List[ChatMessage] = []
        if missing_dates:
            live_messages = self._fetch_missing_dates(
                missing_dates,
                config.from_date,
                total_days,
                progress_callback
            )
            
            if self.stop_requested:
                # Return partial results from DB, plus today's log fetched live
                messages = self.parser.db.get_messages(
                    config.from_date,
                    config.to_date,
                    config.usernames or None,
                    config.search_terms or None,
                    config.mention_keywords or None
                )
                return self._merge_live_messages(messages, live_messages, config)
        
        # Now all cacheable dates are in DB - use optimized DB query
        messages = self.parser.db.get_messages(
            config.from_date,
            config.to_date,
            config.usernames or None,
            config.search_terms or None,
            config.mention_keywords or None
        )
        # Today's log is fetched live but never cached (it keeps changing),
        # so merge it in from the network fetch instead of the DB query above.
        messages = self._merge_live_messages(messages, live_messages, config)
        
        # Group messages by date for incremental callback
        if message_callback and messages:
            messages_by_date = {}
            for msg in messages:
                if msg.date not in messages_by_date:
                    messages_by_date[msg.date] = []
                messages_by_date[msg.date].append(msg)
            
            # Send callbacks in chronological order
            for date in sorted(messages_by_date.keys()):
                if self.stop_requested:
                    break
                message_callback(messages_by_date[date], date)
        
        # Final progress update
        if progress_callback:
            progress_callback(config.from_date, config.to_date, 100)
        
        return messages
    
    def _fetch_missing_dates(
        self,
        missing_dates: List[str],
        start_date: str,
        total_days: int,
        progress_callback: Optional[Callable[[str, str, int], None]]
    ) -> List[ChatMessage]:
        """Fetch missing dates using multithreading. Returns everything fetched
        so callers can use today's messages, which save_messages() never caches."""
        completed_count = 0
        fetched_messages: List[ChatMessage] = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all fetch tasks
            future_to_date = {
                executor.submit(self._fetch_date, date_str): date_str
                for date_str in missing_dates
            }
            
            # Process completed futures
            for future in as_completed(future_to_date):
                if self.stop_requested:
                    for f in future_to_date:
                        f.cancel()
                    break
                
                try:
                    date_str, messages, error = future.result()
                    fetched_messages.extend(messages)
                    
                    with self._lock:
                        completed_count += 1
                        # Progress based on total days in range, not just missing
                        percent = int((completed_count / len(missing_dates)) * 100)
                    
                    if progress_callback:
                        progress_callback(start_date, date_str, percent)
                    
                    if error:
                        print(f"Error fetching {date_str}: {error}")
                
                except Exception as e:
                    print(f"Error processing future: {e}")
        
        return fetched_messages
    
    def _merge_live_messages(
        self,
        db_messages: List[ChatMessage],
        live_messages: List[ChatMessage],
        config: ParseConfig
    ) -> List[ChatMessage]:
        """Append messages fetched live for dates that db_messages doesn't cover
        (today, which is never cached), applying config's filters in memory."""
        if not live_messages:
            return db_messages
        
        covered_dates = {msg.date for msg in db_messages}
        extra = [msg for msg in live_messages if msg.date not in covered_dates]
        
        if config.usernames:
            allowed = {name.lower() for name in config.usernames}
            extra = [msg for msg in extra if msg.username.lower() in allowed]
        if config.search_terms:
            terms = [term.lower() for term in config.search_terms]
            extra = [msg for msg in extra if any(term in msg.message.lower() for term in terms)]
        if config.mention_keywords:
            keywords = [keyword.lower() for keyword in config.mention_keywords]
            extra = [msg for msg in extra if any(keyword in msg.message.lower() for keyword in keywords)]
        
        if not extra:
            return db_messages
        
        combined = db_messages + extra
        combined.sort(key=lambda msg: (msg.date, msg.timestamp))
        return combined
    
    def count_messages_per_user(self, messages: List[ChatMessage]) -> dict:
        """Count messages per username"""
        from collections import Counter
        return Counter(msg.username for msg in messages)
