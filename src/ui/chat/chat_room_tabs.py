"""ChatWindow: room tabs, game rooms and custom rooms."""

import re

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QTabBar,
    QTabWidget,
    QWidget,
)

from components.menu import create_menu
from components.toast import copy_text_with_toast, show_toast, ToastKind
from core.xmpp.jid_utils import custom_room_name_from_jid, game_id_from_jid, is_from_game_room
from helpers.system.memory import release_memory_soon
from helpers.translate import tr
from ui.chat.ui_room import RoomWidget
from ui.dialogs.join_room_dialog import JoinRoomDialog


class ChatRoomTabsMixin:
    """ChatWindow: room tabs, game rooms and custom rooms."""

    def all_room_widgets(self):
        """Every open RoomWidget — game/competition rooms and custom rooms."""
        return list(self.game_rooms.values()) + list(self.custom_rooms.values())

    def current_room(self):
        """RoomWidget of the currently selected tab, or None if General."""
        if not self.room_tabs or self.room_tabs.currentIndex() <= 0:
            return None
        w = self.room_tabs.currentWidget()
        return w if isinstance(w, RoomWidget) else None

    def ensure_general_tab_visible(self):
        """Switch to General so stacked views/input are visible; remember the room tab."""
        if self.room_tabs is not None and self.room_tabs.currentIndex() != 0:
            w = self.room_tabs.currentWidget()
            if isinstance(w, RoomWidget):
                self.restore_room_game_id = w.game_id
            self.room_tabs.setCurrentIndex(0)

    def restore_room_tab(self):
        """Re-select the game-room tab we left when opening a General stacked view."""
        game_id = self.restore_room_game_id
        self.restore_room_game_id = None
        if game_id is None or not self.room_tabs:
            return
        w = self.game_rooms.get(game_id)
        if w is not None:
            self.room_tabs.setCurrentWidget(w)

    def open_game_room_by_id(self, game_id, room_label: str = "Game"):
        class _Fake:
            pass
        fake = _Fake()
        try:
            fake.competition_game_id = int(game_id)
        except (TypeError, ValueError):
            return
        self.open_game_room_tab(fake, room_label=room_label)

    def _create_room_widget(self, *, game_id=None, room_name: str = None, room_label: str = "Game"):
        """Build and wire a RoomWidget. Shared by game rooms and custom
        rooms, which differ only in which of game_id/room_name is set."""
        font_scaler = getattr(self.app_controller, 'font_scaler', None)
        widget = RoomWidget(
            self.config, self.emoticon_manager, self.icons_path,
            account=self.account, ban_manager=self.ban_manager,
            user_tracker=self.user_tracker,
            game_id=game_id, room_name=room_name, room_label=room_label,
            font_scaler=font_scaler, parent=self,
        )
        widget.send_requested.connect(lambda text, w=widget: self._send_room_message(text, w))
        self.wire_userlist_signals(widget)
        widget.open_game_requested.connect(self.open_game_room_by_id)
        widget.emoticon_requested.connect(lambda w=widget: self.on_room_emoticon_requested(w))
        self.wire_username_signals(widget, right_click_widget=widget.messages_widget)
        widget.set_compact_mode(self.width() <= 1000)  # match current window width immediately
        QTimer.singleShot(0, self.update_input_style)  # picks up active ban styling once registered
        return widget

    def open_game_room_tab(self, msg, room_label: str = "Game"):
        """Open or focus a game-room tab.

        room_label: "Game" (default, opened via a live game_id) or
        "Competition" (opened via RMB on a competition announcement timestamp).
        """
        game_id = getattr(msg, 'competition_game_id', None)
        if not game_id:
            return
        try:
            game_id = int(game_id)
        except (TypeError, ValueError):
            return

        if self.chatlog_split_widget:
            self.close_chatlog_split_view()

        # Already open → just switch to it
        if game_id in self.game_rooms:
            self.room_tabs.setCurrentWidget(self.game_rooms[game_id])
            return

        self._ensure_room_tabs()

        widget = self._create_room_widget(game_id=game_id, room_label=room_label)
        self.game_rooms[game_id] = widget
        self.room_tabs.addTab(widget, widget.tab_title())
        self.room_tabs.setCurrentWidget(widget)
        self._join_room(widget.room_jid, game_id=game_id)

    def on_join_room_requested(self):
        dialog = JoinRoomDialog(self.config, self.icons_path, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        room_name = dialog.room_name()
        if not room_name:
            return
        # Allow only simple room names (letters, digits, underscore, hyphen)
        if not re.match(r'^[a-z0-9_-]+$', room_name):
            show_toast(
                self,
                tr("Invalid room name: use only letters, digits, underscore or hyphen",
                   "Неверное имя комнаты: только буквы, цифры, подчёркивание или дефис"),
                ToastKind.WARNING,
            )
            return
        if room_name == "general":
            show_toast(self, tr("You are already in the General room", "Вы уже находитесь в общей комнате"), ToastKind.INFO)
            return
        if dialog.should_remember():
            dialog.remember_name(room_name)
        self._open_custom_room_tab(room_name)

    def _open_custom_room_tab(self, room_name: str):
        room_name = (room_name or "").strip().lower()
        if not room_name:
            return

        if self.chatlog_split_widget:
            self.close_chatlog_split_view()

        if room_name in self.custom_rooms:
            self.room_tabs.setCurrentWidget(self.custom_rooms[room_name])
            return

        self._ensure_room_tabs()

        widget = self._create_room_widget(room_name=room_name, room_label=room_name)
        self.custom_rooms[room_name] = widget
        self.room_tabs.addTab(widget, widget.tab_title())
        self.room_tabs.setCurrentWidget(widget)
        self._join_room(widget.room_jid)

        # Silently put plain room name on the clipboard (no dialog)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(room_name)

    def close_custom_room_tab(self, room_name: str):
        self._close_room_tab(self.custom_rooms, room_name, f"c:{room_name}")

    @staticmethod
    def _transfer_layout_items(src_layout, dst_layout):
        """Move every item from src_layout to dst_layout, preserving each
        item's stretch factor (e.g. left pane vs userlist width). Shared by
        _ensure_room_tabs and _collapse_room_tabs, which both rewrap the
        general-chat content between content_layout and general_body's own
        layout and previously duplicated this loop."""
        while src_layout.count():
            # Capture the stretch factor before takeAt(0) removes it —
            # otherwise panes reset to equal width.
            stretch = src_layout.stretch(0)
            item = src_layout.takeAt(0)
            if item.widget():
                dst_layout.addWidget(item.widget())
            elif item.layout():
                dst_layout.addLayout(item.layout())
            dst_layout.setStretch(dst_layout.count() - 1, stretch)

    def wire_userlist_signals(self, userlist):
        """Connect the profile/private-chat/paste actions shared by every
        userlist panel — the main userlist, the chatlog userlist, and each
        game room's own (which just re-emits its internal userlist's
        signals). open_game_requested is wired separately since only the
        main userlist and game-room widgets have it."""
        userlist.profile_requested.connect(self.show_profile_view)
        userlist.private_chat_requested.connect(self.enter_private_mode)
        userlist.paste_requested.connect(self.paste_username_to_input)
        userlist.track_requested.connect(self.on_track_user_requested)
        userlist.ban_requested.connect(self.on_ban_requested)
        userlist.pronunciation_requested.connect(self.set_username_pronunciation)
        userlist.pronunciation_manager = self.pronunciation_manager

    def wire_username_signals(self, source, right_click_widget=None):
        """Connect username left/ctrl/shift/right click signals to their
        shared handlers. Used for the general messages view, chatlog
        widgets, and each game-room tab, which all wire the same four
        signals to the same handlers.

        right_click_widget: widget passed to _on_username_right_click so
        context-menu actions (ban, remove messages) apply to the right
        message list. None lets it default to self.messages_widget."""
        source.username_left_clicked.connect(self.on_username_left_click)
        source.username_ctrl_clicked.connect(self.on_username_ctrl_click)
        source.username_shift_clicked.connect(self.on_username_shift_click)
        source.username_right_clicked.connect(
            lambda msg, pos, w=right_click_widget: self.on_username_right_click(msg, pos, w)
        )

    def _ensure_room_tabs(self):
        """Create QTabWidget once; wrap existing general content as non-closable tab 0."""
        if self.room_tabs is not None:
            return

        self.general_body = QWidget()
        general_layout = QHBoxLayout()
        general_layout.setContentsMargins(0, 0, 0, 0)
        general_layout.setSpacing(self.config.get("ui", "spacing", "widget_content") or 6)
        self.general_body.setLayout(general_layout)

        # Freeze repaints during the rewrap to avoid a flash of the half-populated layout
        self.setUpdatesEnabled(False)
        self._transfer_layout_items(self.content_layout, general_layout)

        self.room_tabs = QTabWidget()
        self.room_tabs.setDocumentMode(True)
        self.room_tabs.setMovable(True)
        self.room_tabs.setTabsClosable(True)
        self.room_tabs.tabCloseRequested.connect(self._on_room_tab_close_requested)
        self.room_tabs.currentChanged.connect(self._on_room_tab_changed)

        tab_bar = self.room_tabs.tabBar()
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._on_room_tab_context_menu)

        self.room_tabs.addTab(self.general_body, "")
        self.tr_set(lambda text: self.room_tabs.setTabText(0, text), "General", "Общая")
        # General is permanent — hide its close button
        tab_bar.setTabButton(0, QTabBar.ButtonPosition.RightSide, None)

        self.content_layout.addWidget(self.room_tabs)
        self.setUpdatesEnabled(True)

    def _collapse_room_tabs(self):
        """Reverse of _ensure_room_tabs: once no game-room tabs remain, unwrap
        General back into content_layout directly so the tab bar doesn't sit
        there taking up space for a single permanent tab."""
        if self.room_tabs is None:
            return

        self.setUpdatesEnabled(False)
        general_layout = self.general_body.layout()
        self._transfer_layout_items(general_layout, self.content_layout)

        self.content_layout.removeWidget(self.room_tabs)
        self.room_tabs.deleteLater()
        self.room_tabs = None
        self.general_body = None
        self.unread_rooms.clear()
        self.setUpdatesEnabled(True)

    def _room_tab_index(self, game_id):
        """QTabWidget index for a room, or 0 for General (gid=None). -1 if not open.
        gid can be int (game), None (General), or 'c:name' (custom room)."""
        if not self.room_tabs:
            return -1
        if game_id is None:
            return 0
        if isinstance(game_id, str) and game_id.startswith("c:"):
            widget = self.custom_rooms.get(game_id[2:])
        else:
            widget = self.game_rooms.get(game_id)
        return self.room_tabs.indexOf(widget) if widget else -1

    def _refresh_tab_title(self, game_id):
        """Repaint the "(N) " unread prefix on a room tab, or General (gid=None)."""
        index = self._room_tab_index(game_id)
        if index < 0:
            return
        if game_id is None:
            base = "General"
        elif isinstance(game_id, str) and game_id.startswith("c:"):
            base = self.custom_rooms[game_id[2:]].tab_title()
        else:
            base = self.game_rooms[game_id].tab_title()
        count = self.unread_rooms.get(game_id, 0)
        prefix = f"({count}) " if count else ""
        self.room_tabs.setTabText(index, prefix + base)

    def bump_tab_unread(self, game_id):
        """Increment the unread counter for a room (gid=None for General)."""
        self.unread_rooms[game_id] = self.unread_rooms.get(game_id, 0) + 1
        self._refresh_tab_title(game_id)

    def _clear_tab_unread(self, game_id):
        """Clear the unread counter for a room (gid=None for General)."""
        if self.unread_rooms.pop(game_id, 0):
            self._refresh_tab_title(game_id)

    def _on_room_tab_close_requested(self, index: int):
        if index <= 0:
            return  # General never closes
        widget = self.room_tabs.widget(index)
        if not isinstance(widget, RoomWidget):
            return
        if widget.room_name:
            self.close_custom_room_tab(widget.room_name)
        else:
            self.close_game_room_tab(widget.game_id)

    def _on_room_tab_context_menu(self, pos):
        if not self.room_tabs:
            return
        tab_bar = self.room_tabs.tabBar()
        index = tab_bar.tabAt(pos)
        if index < 0:
            return
        menu = create_menu(self)
        widget = self.room_tabs.widget(index)
        # Custom rooms: allow copying the plain room name
        if isinstance(widget, RoomWidget) and widget.room_name:
            name = widget.room_name
            menu.addAction(
                tr("Copy room name", "Скопировать имя комнаты"),
                lambda n=name: copy_text_with_toast(self, n),
            )
            menu.addSeparator()
        if index > 0:
            menu.addAction(tr("Close", "Закрыть"), lambda: self._on_room_tab_close_requested(index))
            menu.addAction(tr("Close others", "Закрыть остальные"), lambda: self._close_other_room_tabs(index))
        if self.game_rooms or self.custom_rooms:
            menu.addAction(tr("Close all rooms", "Закрыть все комнаты"), self._close_all_room_tabs)
        if menu.actions():
            menu.exec(tab_bar.mapToGlobal(pos))

    def _close_other_room_tabs(self, keep_index: int):
        if not self.room_tabs:
            return
        keep_widget = self.room_tabs.widget(keep_index)
        for game_id in list(self.game_rooms.keys()):
            widget = self.game_rooms.get(game_id)
            if widget is not None and widget is not keep_widget:
                self.close_game_room_tab(game_id)
        for name in list(self.custom_rooms.keys()):
            widget = self.custom_rooms.get(name)
            if widget is not None and widget is not keep_widget:
                self.close_custom_room_tab(name)

    def _close_all_room_tabs(self):
        for game_id in list(self.game_rooms.keys()):
            self.close_game_room_tab(game_id)
        for name in list(self.custom_rooms.keys()):
            self.close_custom_room_tab(name)

    def _on_room_tab_changed(self, index: int):
        # Optional: focus the input of the newly selected pane
        if index <= 0:
            if hasattr(self, 'input_field') and self.input_field:
                self.input_field.setFocus()
            self._clear_tab_unread(None)
        else:
            w = self.room_tabs.widget(index)
            if isinstance(w, RoomWidget):
                if w.input_field:
                    w.input_field.setFocus()
                if w.room_name:
                    self._clear_tab_unread(f"c:{w.room_name}")
                else:
                    self._clear_tab_unread(w.game_id)

    def _join_room(self, room_jid: str, game_id=None):
        """Join a MUC room. game_id set → game/competition room, unset → custom room."""
        client = self.xmpp_client
        if not client or not client.sid:
            return
        try:
            client.join_room(room_jid, game_id=str(game_id) if game_id is not None else None)
        except Exception as e:
            print(f"⚠️ Room join error: {e}")

    def _leave_room(self, room_jid: str):
        client = self.xmpp_client
        if not client or not room_jid:
            return
        try:
            client.leave_room(room_jid)
        except Exception as e:
            print(f"⚠️ Leave room error: {e}")

    def _close_room_tab(self, rooms: dict, key, unread_key):
        """Pop and tear down a room tab. `rooms` is self.game_rooms or
        self.custom_rooms, `key` its dict key, `unread_key` the matching
        key in self._unread_rooms (game_id itself, or 'c:<name>')."""
        widget = rooms.pop(key, None)
        if not widget:
            return
        self.unread_rooms.pop(unread_key, None)
        self._leave_room(widget.room_jid)
        index = self.room_tabs.indexOf(widget) if self.room_tabs else -1
        if index >= 0:
            self.room_tabs.removeTab(index)
        widget.cleanup()
        widget.setParent(None)
        widget.deleteLater()
        release_memory_soon()

        # Last room closed → collapse back to plain General view,
        # so a lone permanent tab doesn't waste vertical space.
        if not self.game_rooms and not self.custom_rooms:
            self._collapse_room_tabs()

    def close_game_room_tab(self, game_id):
        self._close_room_tab(self.game_rooms, game_id, game_id)

    def _send_room_message(self, text: str, widget=None):
        room = widget or self.current_room()
        if not room or not self.xmpp_client or not room.room_jid:
            return
        self.dispatch_chat_message(text, 'groupchat', room.room_jid, room.add_message)

    def room_for_jid(self, from_jid: str):
        """Resolve an incoming stanza's from_jid to its open room widget.
        Returns (widget, unread_key, game_id) or (None, None, None) if the
        jid isn't a currently-open game or custom room."""
        if self.game_rooms and is_from_game_room(from_jid):
            game_id = game_id_from_jid(from_jid)
            room = self.game_rooms.get(game_id) if game_id is not None else None
            if room is not None:
                return room, game_id, game_id
        if self.custom_rooms:
            cname = custom_room_name_from_jid(from_jid)
            room = self.custom_rooms.get(cname) if cname else None
            if room is not None:
                return room, f"c:{cname}", None
        return None, None, None
