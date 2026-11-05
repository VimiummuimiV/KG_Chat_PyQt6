"""Background worker running a chatlog parse."""

from PyQt6.QtCore import pyqtSignal, QThread

from core.chatlogs.range_parser import ChatlogsParserEngine, ParseConfig


class ParserWorker(QThread):
    """Worker thread for parsing"""
    progress = pyqtSignal(str, str, int) # start_date, current_date, percent
    messages_found = pyqtSignal(list, str) # messages, date
    finished = pyqtSignal(list) # all messages
    error = pyqtSignal(str)
    sync_stats = pyqtSignal(int, dict) # fetched_count, db_stats

    def __init__(self, config: ParseConfig):
        super().__init__()
        self.config = config
        self.engine = ChatlogsParserEngine()

    def run(self):
        try:
            # Get missing dates count before fetching
            missing_dates = self.engine.parser.db.get_missing_dates(
                self.config.from_date,
                self.config.to_date
            )
            total_missing = len(missing_dates)

            # Run parse
            messages = self.engine.parse(
                self.config,
                progress_callback=self.progress.emit,
                message_callback=self.messages_found.emit if self.config.mode != 'syncdatabase' else None
            )

            # For sync mode, emit stats
            if self.config.mode == 'syncdatabase':
                db_stats = self.engine.parser.db.get_database_stats()
                self.sync_stats.emit(total_missing, db_stats)

            self.finished.emit(messages)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self.engine.stop()
