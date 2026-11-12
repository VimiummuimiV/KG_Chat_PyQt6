"""ChatWindow: keyboard shortcuts and global event filter."""

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QLineEdit, QMenu, QTextEdit

from components.image_viewer.viewer import ImageHoverView


_HANDLED_EVENT_TYPES = frozenset({
    QEvent.Type.KeyPress,
    QEvent.Type.KeyRelease,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.Wheel,
})


class ChatHotkeysMixin:
    """ChatWindow: keyboard shortcuts and global event filter."""

    def eventFilter(self, obj, event):
        event_type = event.type()
        # the image viewer keeps every key and mouse action for itself
        if event_type not in _HANDLED_EVENT_TYPES or ImageHoverView.is_open():
            return super().eventFilter(obj, event)

        # Ctrl+Space hold-to-talk. Must live here (not only keyPressEvent):
        # the focused QLineEdit would otherwise swallow Space.
        if event_type == QEvent.Type.KeyPress and not event.isAutoRepeat():
            if (event.key() == Qt.Key.Key_Space
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                start = getattr(self, "start_voice_ptt", None)
                if callable(start):
                    start()
                    return True
        if event_type == QEvent.Type.KeyRelease and not event.isAutoRepeat():
            if getattr(self, "voice_ptt_held", False) and event.key() in (
                Qt.Key.Key_Space,
                Qt.Key.Key_Control,
            ):
                stop = getattr(self, "stop_voice_ptt", None)
                if callable(stop):
                    stop()
                return event.key() == Qt.Key.Key_Space

        font_scaler = getattr(self.app_controller, 'font_scaler', None)
        if font_scaler is not None:
            # Ctrl + Scroll → font size
            if event_type == QEvent.Type.Wheel:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    if event.angleDelta().y() > 0:
                        font_scaler.scale_up()
                    else:
                        font_scaler.scale_down()
                    return True
            # Ctrl + Plus/Minus/Equal → font size
            elif event_type == QEvent.Type.KeyPress:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                        font_scaler.scale_up()
                        return True
                    elif event.key() == Qt.Key.Key_Minus:
                        font_scaler.scale_down()
                        return True

        # Tab switches views or cycles emoticon groups; Ctrl+Tab cycles room tabs in keyPressEvent
        if (event_type == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
                and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier)):
            sel = getattr(self, 'emoticon_selector', None)
            if sel and sel.isVisible():
                # Emoticon selector gets priority: Tab/Shift+Tab cycles through groups
                forward = event.key() != Qt.Key.Key_Backtab and not (
                    event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                )
                sel.cycle_tab(forward=forward)
                return True

            if event.key() == Qt.Key.Key_Tab:
                current_view = self.stacked_widget.currentWidget()
                if current_view == self.messages_splitter:
                    # Close the split chatlog pane if open, otherwise switch to full chatlog view
                    if self.chatlog_split_widget:
                        self.close_chatlog_split_view()
                    else:
                        self.show_chatlog_view()
                elif current_view == self.chatlog_widget:
                    # Close the date split pane if open, otherwise leave chatlog for messages
                    if self.chatlog_widget.split_chatlog_widget:
                        self.chatlog_widget.close_split_view()
                    else:
                        # Restore room tab if chatlog was opened from a game tab (Tab / ensure)
                        self.on_stacked_back()
                else:
                    # Profile / settings / ban / pronun → messages, restore room tab if any
                    self.on_stacked_back()
                return True

        # Handle mouse button presses/releases for navigation and focus reclaim
        if event_type == QEvent.Type.MouseButtonPress:
            # Back/Forward mouse buttons navigate chatlog days
            # (works on main stacked chatlog OR split view under cursor)
            cw = self.get_hovered_chatlog_widget()
            if cw:
                direction = {Qt.MouseButton.BackButton: -1, Qt.MouseButton.ForwardButton: 1}.get(event.button())
                if direction is not None:
                    cw.navigate_hold(direction)
                    return True

            # Close emoticon selector if click is outside it and outside the button
            if hasattr(self, 'emoticon_selector') and self.emoticon_selector.isVisible():
                try:
                    gp = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                    w = QApplication.widgetAt(gp)
                    # Walk up parents to see if click landed inside selector or on the button
                    button = self.active_emoticon_button()
                    inside = False
                    while w:
                        if w == self.emoticon_selector or w == button:
                            inside = True
                            break
                        w = w.parentWidget()
                    if not inside and self.emoticon_selector.parent() is self:
                        self.emoticon_selector.setVisible(False)
                        self.config.set("ui", "emoticon_selector_visible", value=False)
                except Exception:
                    pass

            # Reclaim focus after clicks outside text inputs, but not inside a QMenu (it would steal focus before the action fires)
            try:
                gp = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                clicked = QApplication.widgetAt(gp)
                in_menu = False
                w = clicked
                while w:
                    if isinstance(w, QMenu):
                        in_menu = True
                        break
                    w = w.parentWidget()
                if clicked and not in_menu and not isinstance(clicked, QLineEdit):
                    self.setFocus()
            except Exception:
                pass

        if event_type == QEvent.Type.MouseButtonRelease:
            cw = self.get_hovered_chatlog_widget()
            if cw and event.button() in (Qt.MouseButton.BackButton, Qt.MouseButton.ForwardButton):
                cw.navigate_hold()
                return True

        return super().eventFilter(obj, event)

    # Layout-independent: Latin letter Qt keys equal their ASCII/VK codes, so nativeVirtualKey works on any layout
    _KEY_ACTION = {
        Qt.Key.Key_F: 'focus',
        Qt.Key.Key_U: 'userlist',
        Qt.Key.Key_B: 'banlist',
        Qt.Key.Key_P: 'pronun',
        Qt.Key.Key_M: 'mute',
        Qt.Key.Key_T: 'top',
        Qt.Key.Key_V: 'voice',
        Qt.Key.Key_R: 'reset_size',
        Qt.Key.Key_C: 'color',
        Qt.Key.Key_N: 'notification',
        Qt.Key.Key_S: 'search',
        Qt.Key.Key_H: 'nav_backward',
        Qt.Key.Key_L: 'nav_forward',
        Qt.Key.Key_Left:  'nav_backward',
        Qt.Key.Key_Right: 'nav_forward',
        Qt.Key.Key_J: 'scroll_down',
        Qt.Key.Key_K: 'scroll_up',
        Qt.Key.Key_Down: 'scroll_down',
        Qt.Key.Key_Up: 'scroll_up',
        Qt.Key.Key_G: 'scroll_gg',   # gg = top, G (Shift+G) = bottom
        Qt.Key.Key_D: 'calendar',
        Qt.Key.Key_Space: 'page_down',
        Qt.Key.Key_X: 'exit_private',
        Qt.Key.Key_E: 'enter_competition',
    }

    def keyPressEvent(self, event):
        key, mods = event.key(), event.modifiers()
        ctrl  = mods == Qt.KeyboardModifier.ControlModifier
        shift = mods == Qt.KeyboardModifier.ShiftModifier
        ctrl_held = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift_held = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        if ctrl_held and key == Qt.Key.Key_Space:
            start = getattr(self, "start_voice_ptt", None)
            if callable(start) and not event.isAutoRepeat():
                start()
            return

        if ctrl_held and key == Qt.Key.Key_W and not shift_held:
            room = self.current_room()
            if room:
                self.close_game_room_tab(room.game_id)
            return

        if ctrl_held and key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            if self.room_tabs and self.room_tabs.count() > 1:
                delta = -1 if (key == Qt.Key.Key_Backtab or shift_held) else 1
                count = self.room_tabs.count()
                self.room_tabs.setCurrentIndex((self.room_tabs.currentIndex() + delta) % count)
            return

        if mods and not ctrl_held and not shift_held:
            return super().keyPressEvent(event)

        focused_widget = QApplication.focusWidget()
        focused = isinstance(focused_widget, (QLineEdit, QTextEdit))

        # Forward Ctrl+C to the text selector overlay if active
        if ctrl and (key == Qt.Key.Key_C or event.nativeVirtualKey() == Qt.Key.Key_C):
            delegate = getattr(self.messages_widget, 'delegate', None)
            if delegate and delegate.text_selector:
                delegate.text_selector.copy()
                return

        # F1 — context-aware help
        if key == Qt.Key.Key_F1:
            sel = getattr(self, 'emoticon_selector', None)
            if sel and sel.isVisible():
                context = 'emoticon'
            elif (self.chatlog_widget and
                  self.stacked_widget.currentWidget() == self.chatlog_widget):
                context = 'parser' if self.chatlog_widget.parser_visible else 'chatlog'
            else:
                context = 'chat'
            self.help_panel.show_for_context(context)
            return

        # Loose input focus on (Esc) — also closes chatlog search if open
        if key == Qt.Key.Key_Escape and focused:
            self.input_field.clearFocus()
            return
        if key == Qt.Key.Key_Escape:
            sel = getattr(self, 'emoticon_selector', None)
            if sel and sel.isVisible():
                sel.toggle_visibility()
                self.input_field.setFocus()
                return
            cw = self.chatlog_for_hotkey()
            if cw and cw.search_visible:
                cw.toggle_search()
                return
            if self.stacked_widget.currentWidget() == self.messages_splitter:
                mw = self.active_messages_widget()
                if mw and mw.search_visible:
                    mw.toggle_search()
                    return
        # Ctrl+; toggle emoticon selector (works even when input focused, layout-independent)
        # nativeScanCode 0x27 = physical semicolon key on all standard keyboards
        if ctrl and (key == Qt.Key.Key_Semicolon or event.nativeScanCode() == 0x27):
            self.toggle_emoticon_selector()
            return
        # Ctrl+F toggle search for current view (chatlog or messages)
        if ctrl and (key == Qt.Key.Key_F or event.nativeVirtualKey() == Qt.Key.Key_F):
            self.toggle_search_for_current_view()
            return
        # Ctrl+A copy all messages of the current view (text inputs keep their own select-all)
        if ctrl and not focused and (key == Qt.Key.Key_A or event.nativeVirtualKey() == Qt.Key.Key_A):
            self.copy_messages_from_current_view()
            return
        # Ctrl+C / Ctrl+S in chatlog parser — copy / save results
        if ctrl and self.chatlog_widget and self.stacked_widget.currentWidget() == self.chatlog_widget:
            cw = self.chatlog_widget
            if cw.parser_visible:
                if key == Qt.Key.Key_C or event.nativeVirtualKey() == Qt.Key.Key_C:
                    cw.on_copy_results()
                    return
                if key == Qt.Key.Key_S or event.nativeVirtualKey() == Qt.Key.Key_S:
                    cw.on_save_results()
                    return
        # Ctrl+P open chatlog and parser from anywhere
        if ctrl and (key == Qt.Key.Key_P or event.nativeVirtualKey() == Qt.Key.Key_P):
            if not self.chatlog_widget or self.stacked_widget.currentWidget() != self.chatlog_widget:
                self.show_chatlog_view()
            if self.chatlog_widget and not self.chatlog_widget.parser_visible:
                self.chatlog_widget.toggle_parser()
            return
        # Ctrl+Shift+U toggle user tracker
        if ctrl_held and shift_held and (key == Qt.Key.Key_U or event.nativeVirtualKey() == Qt.Key.Key_U):
            self.toggle_user_tracker_view()
            return
        # Ctrl+, uses the physical comma key (VK_OEM_COMMA 0xBC, scan 0x33); on RU layout it types «б»
        if ctrl and (
            key == Qt.Key.Key_Comma
            or event.nativeVirtualKey() in (Qt.Key.Key_Comma, 0xBC)
            or event.nativeScanCode() == 0x33
        ):
            self.toggle_settings_view()
            return
        # Ctrl+J join / create room
        if ctrl and (key == Qt.Key.Key_J or event.nativeVirtualKey() == Qt.Key.Key_J):
            self.on_join_room_requested()
            return
        # Ctrl+U switch account
        if ctrl and (key == Qt.Key.Key_U or event.nativeVirtualKey() == Qt.Key.Key_U):
            self.on_switch_account()
            return
        # Ctrl+T toggle theme
        if ctrl and (key == Qt.Key.Key_T or event.nativeVirtualKey() == Qt.Key.Key_T):
            self.toggle_theme()
            return
        # Resolve physical key regardless of layout
        vk = self._KEY_ACTION.get(key) or self._KEY_ACTION.get(event.nativeVirtualKey())

        # ── Emoticon selector keyboard navigation ──────────────────────────────
        sel = getattr(self, 'emoticon_selector', None)
        if sel and sel.isVisible() and not focused:
            nk = event.nativeVirtualKey()
            sc = event.nativeScanCode()
            if not ctrl and not shift:
                if key == Qt.Key.Key_Left  or nk == Qt.Key.Key_H: sel.navigate(-1, 0); return
                if key == Qt.Key.Key_Right or nk == Qt.Key.Key_L: sel.navigate(1, 0); return
                if key == Qt.Key.Key_Down  or nk == Qt.Key.Key_J: sel.navigate(0, 1); return
                if key == Qt.Key.Key_Up    or nk == Qt.Key.Key_K: sel.navigate(0, -1); return
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or nk == Qt.Key.Key_A or sc == 0x27:
                    sel.insert_selected(); return
            if shift and (key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or nk == Qt.Key.Key_A or sc == 0x27):
                sel.insert_selected(shift=True); return
        # ───────────────────────────────────────────────────────────────────────

        # E = enter last competition race in browser (works with empty input focused)
        is_e = (key == Qt.Key.Key_E or event.nativeVirtualKey() == Qt.Key.Key_E) and not ctrl and not shift
        if is_e:
            if not focused or not (self.active_input_field().text() or "").strip():
                self.open_latest_competition_in_browser()
                return

        if not vk or focused:
            return super().keyPressEvent(event)
        def _active_scrollbar():
            current = self.stacked_widget.currentWidget()
            if current == self.messages_splitter:
                return self.messages_widget.list_view.verticalScrollBar()
            if self.chatlog_widget and current == self.chatlog_widget:
                return self.chatlog_widget.list_view.verticalScrollBar()
            return None
        # Focus input on (F) key if not focused, for quick access
        if vk == 'focus':
            # Focus the active room's input, not always General's
            self.active_input_field().setFocus()
        # User list toggle (U) — Ctrl+U is handled before the focus guard above
        elif vk == 'userlist':
            self.toggle_user_list()
        # Ban list toggle (B)
        elif vk == 'banlist':
            self.toggle_ban_list_view()
        # Pronunciation toggle (P) / in chatlog: toggle parser (P)
        elif vk == 'pronun':
            cw = self.chatlog_widget
            if cw and self.stacked_widget.currentWidget() == cw:
                cw.toggle_parser()
            else:
                self.toggle_pronunciation_view()
        # Mute effects sound (M) or toggle mention filter in chatlog (M)
        elif vk == 'mute':
            cw = self.chatlog_for_hotkey()
            if cw:
                cw.toggle_mention_filter()
            else:
                self.on_toggle_effects_sound()
        # Toggle search (S) — chatlog or messages; parser: start parse when visible
        elif vk == 'search':
            self.toggle_search_for_current_view()
        # Navigate chatlog days — H backward, L forward, supports hold
        elif vk in ('nav_backward', 'nav_forward'):
            cw = self.chatlog_for_hotkey()
            if cw and not event.isAutoRepeat():
                cw.navigate_hold(-1 if vk == 'nav_backward' else 1)
        # Vim-style scroll — J down, K up, works in chat and chatlog
        elif vk in ('scroll_down', 'scroll_up'):
            scroll_bar = _active_scrollbar()
            if scroll_bar:
                step = scroll_bar.singleStep() * 5
                scroll_bar.setValue(scroll_bar.value() + (step if vk == 'scroll_down' else -step))
        # Vim-style G = bottom, gg = top
        elif vk == 'scroll_gg':
            scroll_bar = _active_scrollbar()
            if scroll_bar:
                if shift:
                    scroll_bar.setValue(scroll_bar.maximum())
                else:
                    if not hasattr(self, '_gg_timer'):
                        self._gg_timer = QTimer(self)
                        self._gg_timer.setSingleShot(True)
                    if self._gg_timer.isActive():
                        self._gg_timer.stop()
                        scroll_bar.setValue(scroll_bar.minimum())
                    else:
                        self._gg_timer.start(300)
        # Space — scroll down one page
        elif vk == 'page_down':
            scroll_bar = _active_scrollbar()
            if scroll_bar:
                scroll_bar.setValue(scroll_bar.value() + (-scroll_bar.pageStep() if shift else scroll_bar.pageStep()))
        # Always on top toggle (T)
        elif vk == 'top':
            self.on_toggle_always_on_top()
        # Voice sound toggle (V)
        elif vk == 'voice':
            self.on_toggle_voice_sound()
        # Reset window size (R)
        elif vk == 'reset_size':
            self.reset_window_size()
        # Change username color (C) / Ctrl+C reset
        # In chatlog when parser visible: C cancels if parsing, Ctrl+C copies
        elif vk == 'color':
            cw = self.chatlog_widget
            if cw and self.stacked_widget.currentWidget() == cw and cw.parser_visible:
                if ctrl:
                    cw.on_copy_results()
                elif cw.parser_widget.is_parsing:
                    cw.parser_widget.on_parse_clicked()  # Cancel
            elif ctrl:
                self.on_reset_username_color()
            else:
                self.on_change_username_color()
        # Toggle notifications cycle (N)
        elif vk == 'notification':
            self.on_toggle_notification()
        # Open calendar date picker in chatlog (D)
        elif vk == 'calendar':
            cw = self.chatlog_for_hotkey()
            if cw:
                cw.show_calendar()
        # Exit private mode / clear private messages / clear new messages marker and presence logs (X)
        elif vk == 'exit_private':
            if self.private_mode:
                self.exit_private_mode()
            else:
                self.clear_private_messages()
            self.clear_new_messages_marker()
            if self.presence_log_widget:
                self.presence_log_widget.clear_presence_messages()
        # Enter last competition race in browser (E)
        elif vk == 'enter_competition':
            self.open_latest_competition_in_browser()

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        key = event.key()
        if getattr(self, "voice_ptt_held", False) and key in (
            Qt.Key.Key_Space,
            Qt.Key.Key_Control,
        ):
            stop = getattr(self, "stop_voice_ptt", None)
            if callable(stop):
                stop()
            return
        vk = self._KEY_ACTION.get(key) or self._KEY_ACTION.get(event.nativeVirtualKey())
        if vk in ('nav_backward', 'nav_forward'):
            cw = self.chatlog_for_hotkey()
            if cw:
                cw.navigate_hold()  # Stop hold
                return
        super().keyReleaseEvent(event)
