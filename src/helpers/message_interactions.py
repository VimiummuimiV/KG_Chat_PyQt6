"""Reusable mouse-interaction detection for message list views.

Hit-tests clicks against a MessageDelegate's click_rects (username/timestamp
regions) and emits signals for them. Shared by MessagesWidget (realtime chat)
and ChatlogWidget so this logic isn't duplicated across views.
"""
from types import SimpleNamespace

from PyQt6.QtCore import QObject, Qt, QEvent, pyqtSignal


class MessageInteractions(QObject):
    """Installs an event filter on a list view's viewport and emits signals
    for username/timestamp clicks, based on the delegate's click_rects."""

    timestamp_left_clicked = pyqtSignal(str)   # date_str ("%Y-%m-%d")
    timestamp_right_clicked = pyqtSignal(str)  # date_str ("%Y-%m-%d") — normal messages
    competition_timestamp_left_clicked = pyqtSignal(object)  # msg — open competition room chat
    username_left_clicked = pyqtSignal(str, bool)         # username, is_double_click
    username_right_clicked = pyqtSignal(object, object)   # msg, global_pos
    username_ctrl_clicked = pyqtSignal(str)   # Ctrl+LMB → enter private
    username_shift_clicked = pyqtSignal(str)  # Shift+LMB → open profile
    chip_clicked = pyqtSignal(str)  # player name from competition chip → open profile

    def __init__(self, list_view, delegate, handle_timestamp: bool = True):
        super().__init__(list_view)
        self.list_view = list_view
        self.delegate = delegate
        # ChatlogWidget already handles timestamp clicks itself (copy URL + highlight
        # via the delegate's own editorEvent on mouse release). Swallowing the press
        # here too interferes with that, so it opts out with handle_timestamp=False.
        self.handle_timestamp = handle_timestamp
        self.list_view.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        try:
            if obj == self.list_view.viewport():
                if event.type() == QEvent.Type.MouseButtonPress:
                    return self._handle_mouse_press(event)
                elif event.type() == QEvent.Type.MouseButtonDblClick:
                    return self._handle_mouse_double_click(event)
        except RuntimeError:
            # list_view's underlying C++ object was already deleted (e.g. its
            # owning widget was torn down while an event was still in flight).
            # Nothing left to hit-test against - just let the event pass through.
            return False
        return super().eventFilter(obj, event)

    def _handle_username_click(self, event, identifier: str, right_click_target):
        """Shared LMB modifier dispatch (ctrl/shift/plain) and RMB emit,
        used for both regular usernames and presence-log usernames."""
        if event.button() == Qt.MouseButton.LeftButton:
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ControlModifier:
                self.username_ctrl_clicked.emit(identifier)
            elif mods & Qt.KeyboardModifier.ShiftModifier:
                self.username_shift_clicked.emit(identifier)
            else:
                self.username_left_clicked.emit(identifier, False)
            return True
        elif event.button() == Qt.MouseButton.RightButton:
            global_pos = self.list_view.viewport().mapToGlobal(event.pos())
            self.username_right_clicked.emit(right_click_target, global_pos)
            return True
        return False

    def _handle_mouse_press(self, event):
        """Handle single mouse clicks"""
        index = self.list_view.indexAt(event.pos())
        if not index.isValid():
            return False

        msg = index.data(Qt.ItemDataRole.DisplayRole)
        if not msg:
            return False

        row = index.row()

        if row not in self.delegate.click_rects:
            return False

        rects = self.delegate.click_rects[row]
        pos = event.pos()

        # Presence-log username (multi-user summary row)
        for name_rect, login in rects.get('presence_users') or []:
            if not name_rect.contains(pos) or not login:
                continue
            proxy = SimpleNamespace(
                login=login, username=login, from_jid=None,
                is_presence_log=True, presence_row=row,
            )
            if self._handle_username_click(event, login, proxy):
                return True

        # Check username click
        if rects['username'].contains(pos):
            if self._handle_username_click(event, msg.username, msg):
                return True

        # Check timestamp click
        if self.handle_timestamp and rects['timestamp'].contains(pos):
            date_str = msg.timestamp.strftime("%Y-%m-%d")
            is_competition = (
                getattr(msg, 'is_competition', False)
                and getattr(msg, 'competition_game_id', None)
            )
            if event.button() == Qt.MouseButton.LeftButton:
                if is_competition:
                    self.competition_timestamp_left_clicked.emit(msg)
                else:
                    self.timestamp_left_clicked.emit(date_str)
                return True
            elif event.button() == Qt.MouseButton.RightButton:
                # Competition timestamps have no special RMB (race URL is in the body)
                if not is_competition:
                    self.timestamp_right_clicked.emit(date_str)
                return True

        # Competition player chips → open profile
        if event.button() == Qt.MouseButton.LeftButton:
            for chip_rect, name in rects.get('chips') or []:
                if chip_rect.contains(pos) and name and name != "…":
                    self.chip_clicked.emit(name)
                    return True

        return False

    def _handle_mouse_double_click(self, event):
        """Handle double clicks"""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        index = self.list_view.indexAt(event.pos())
        if not index.isValid():
            return False

        msg = index.data(Qt.ItemDataRole.DisplayRole)
        if not msg:
            return False

        row = index.row()

        if row not in self.delegate.click_rects:
            return False

        rects = self.delegate.click_rects[row]
        pos = event.pos()

        # Check username double-click
        if rects['username'].contains(pos):
            self.username_left_clicked.emit(msg.username, True)
            return True

        return False