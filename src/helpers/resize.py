"""Centralized resize event handling for chat window"""
from PyQt6.QtCore import QTimer


def recalculate_layout(chat_window):
    """Force layout recalculation after userlist visibility / width change."""
    current_view = chat_window.stacked_widget.currentWidget()

    if current_view == chat_window.messages_splitter:
        mw = chat_window._active_messages_widget()
        mw._force_recalculate()
        QTimer.singleShot(50, mw._force_recalculate)
    elif current_view == chat_window.chatlog_widget and chat_window.chatlog_widget:
        chat_window.chatlog_widget._force_recalculate()
        QTimer.singleShot(50, chat_window.chatlog_widget._force_recalculate)
    elif current_view is getattr(chat_window, 'user_tracker_widget', None):
        chat_window.user_tracker_widget._recalculate_layout()
        QTimer.singleShot(50, chat_window.user_tracker_widget._recalculate_layout)


def handle_chat_resize(chat_window, width: int):
    """
    Handle all resize logic for ChatWindow
    
    Args:
        chat_window: ChatWindow instance
        width: Current window width
    """
    # Determine current view and corresponding widgets/settings
    current_view = chat_window.stacked_widget.currentWidget()
    is_chatlog_view = (current_view == chat_window.chatlog_widget)
    is_tracker_view = current_view is getattr(chat_window, 'user_tracker_widget', None)

    if is_chatlog_view:
        userlist_widget = chat_window.chatlog_userlist_widget
        config_key = "chatlog"
        auto_hide_attr = "auto_hide_chatlog_userlist"
    elif not is_tracker_view:
        userlist_widget = chat_window.user_list_widget
        config_key = "messages"
        auto_hide_attr = "auto_hide_messages_userlist"
    
    # Check compact mode transition (1000px threshold)
    was_compact = chat_window.messages_widget.delegate.compact_mode
    is_compact = width <= 1000
    
    # Re-enable auto-hide when crossing the 1000px threshold
    if was_compact != is_compact:
        chat_window.auto_hide_messages_userlist = True
        chat_window.auto_hide_chatlog_userlist = True
        chat_window.auto_hide_tracker_userlist = True
    
    # Handle button panel visibility
    if width < 500:
        if hasattr(chat_window, 'button_panel') and chat_window.button_panel.isVisible():
            if not getattr(chat_window, '_hover_reveal', False):
                chat_window.button_panel.setVisible(False)
    else:
        if hasattr(chat_window, 'button_panel') and not chat_window.button_panel.isVisible():
            chat_window.button_panel.setVisible(True)

    # Hide/show userlist at 1000px threshold
    if is_tracker_view:
        tracker = chat_window.user_tracker_widget
        auto_hide = chat_window.auto_hide_tracker_userlist
        show = False if (is_compact and auto_hide) else tracker.userlist_visible
        tracker.filter_panel.setVisible(show and bool(tracker.chip_widgets))
        bp = getattr(chat_window, 'button_panel', None)
        if bp and getattr(bp, 'toggle_userlist_button', None):
            bp.set_button_state(bp.toggle_userlist_button, show)
    else:
        userlist_visible_config = chat_window.config.get("ui", "userlist", config_key)
        if userlist_visible_config is None:
            userlist_visible_config = True
        auto_hide = getattr(chat_window, auto_hide_attr)

        if auto_hide:
            show = (not is_compact) and userlist_visible_config
            if hasattr(chat_window, 'userlist_panel'):
                chat_window.userlist_panel.setVisible(show)
            if userlist_widget is not None:
                userlist_widget.setVisible(show)
            bp = getattr(chat_window, 'button_panel', None)
            if bp and getattr(bp, 'toggle_userlist_button', None):
                bp.set_button_state(bp.toggle_userlist_button, show)
    
    # Reposition emoticon selector if visible
    if hasattr(chat_window, 'emoticon_selector') and chat_window.emoticon_selector.isVisible():
        QTimer.singleShot(10, chat_window._position_emoticon_selector)
    
    # Update compact mode for all widgets
    if was_compact != is_compact:
        chat_window.messages_widget.set_compact_mode(is_compact)
        if chat_window.chatlog_widget:
            chat_window.chatlog_widget.set_compact_mode(is_compact)
            chat_window.chatlog_widget.set_compact_layout(is_compact)
        if getattr(chat_window, 'chatlog_split_widget', None):
            chat_window.chatlog_split_widget.set_compact_mode(is_compact)
            chat_window.chatlog_split_widget.set_compact_layout(is_compact)
        QTimer.singleShot(150, chat_window._complete_resize_recalculation)
    else:
        QTimer.singleShot(50, chat_window._complete_resize_recalculation)