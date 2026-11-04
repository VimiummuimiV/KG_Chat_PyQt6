---
name: kg-chat-coding-rules
description: Coding conventions and project structure for KG_Chat_PyQt6, the PyQt6 XMPP chat client for Klavogonki (main.py, core/, helpers/, components/, ui/, themes/, settings/). Covers clean-code rules (no duplication, no over-engineering), where every new file must live, import order, naming rules (full names, no digits, leading underscore for file-private names), good practices and delivery rules. Use whenever writing, editing, reviewing or adding files to this project, even for small changes, and whenever the user mentions the chat client, ui_chat.py, KG_Chat_Data, Klavobot, or any file or folder from this project.
---

# KG_Chat_PyQt6 coding rules

## Clean code

- No over-engineering. Add only what the task needs: no speculative classes, layers, options, abstractions or state. Prefer the simplest direct solution.
- No duplication. Before writing anything, search the project for code that does the same thing by nature (storage, colors, translation, parsing, styling, threading) and reuse or extend it. When two places need the same logic, extract it once into the right shared location and make both use it. Matching by nature counts, not only identical text.
- Clean separation of concerns. Logic, storage and network code live in `core/`; widgets only display and wire signals. Do not grow `ui/ui_chat.py` with logic that has a natural home elsewhere.
- Comments are minimal: a terse one-liner only where the reason is non-obvious. No multi-line explanatory blocks, no narration of history, no commented-out code. All comments and docstrings are in English.
- User-visible strings go through `tr("English", "Русский")` so they follow the interface language live. Code, comments and identifiers stay English.
- Do not refactor or rename unrelated code. Match the style of the surrounding file.
- Before finalizing check for: duplicates, unused names, needless variables or helpers, comments that restate the code, anything that could be simpler.

## Project structure

Put every new file in the folder that owns its kind of code. Never drop a file in a folder just because it is nearby.

```
main.py                 application entry: tray, account window, global hotkey, exit
settings/config.json    default configuration (the user config overrides it)
themes/theme.py         theme manager, light/dark switching, stylesheets
core/                   no widgets: data, network, XMPP, parsing, persistence
helpers/                shared non-visual logic and managers used across files
components/             reusable widgets used by more than one screen
ui/                     screens and windows of the app
ui/dialogs/             modal dialogs
```

### core/
XMPP and protocol: `xmpp.py` (BOSH client), `messages.py` (message/presence parsing), `userlist.py`.
Accounts and web: `accounts.py`, `web_auth.py`, `api_data.py`, `scores.py`, `races_listener.py`, `youtube.py`.
Chatlogs: `chatlogs.py` (fetch and parse), `chatlogs_db.py` (SQLite), `chatlogs_parser.py` (range parsing with workers).
Persistence and per-account state: `presence_db.py`, `user_state.py` (shared per-username JSON store), `mentions_digest.py`, `self_ban.py`.
Rule: nothing here builds a widget. Small per-account JSON state reuses `ByUserStore` from `user_state.py` instead of new load/save code.

### helpers/
Shared logic and managers: `config.py`, `data.py` (`get_data_dir`, the `KG_Chat_Data` folder), `translate.py`, `cache.py`, `fonts.py`, `font_scaler.py`, `color_utils.py`, `color_contrast.py`, `username_color_manager.py`, `emoticons.py`, `ban_manager.py` (the ignore list), `user_tracker.py`, `presence_log.py`, `pronunciation_manager.py`, `hotkey_manager.py`, `power_monitor.py`, `startup_manager.py`, `window_size_manager.py`, `resize.py`, `jid_utils.py`, `me_action.py`, `mention_parser.py`, `dates.py`, `browser.py`, `input_activity.py`, `workers_calculator.py`, `message_interactions.py`, `flash_highlight.py`.
Subfolders: `scroll/` (scrolling behavior and scroll buttons), `voice/` (TTS and voice input).
Colors: new app palettes follow the `get_*_colors` pattern in `color_utils.py` (hue and saturation from config, defaults in code).
Some older widgets live here (image viewer, video player, help panel). Do not copy that: new reusable widgets go to `components/`.

### components/
Reusable widgets: `notification.py`, `search.py`, `tag_button.py`, `mic_button.py`, `loading_spinner.py`, `presence_badge.py`, `user_count_row.py`, `messages_separator.py`, `tray_badge.py`, and `context_menu/` for context menus.

### ui/
Main screens: `ui_chat.py` (chat window), `ui_room.py` (room tab), `ui_messages.py`, `ui_userlist.py`, `ui_chatlog.py`, `ui_chatlog_userlist.py`, `ui_chatlogs_parser.py`, `ui_settings.py`, `ui_accounts.py`, `ui_profile.py`, `ui_banlist.py`, `ui_user_tracker.py`, `ui_pronunciation.py`, `ui_emoticon_selector.py`, `ui_buttons.py`.
Message list rendering: `message_model.py`, `message_delegate.py`, `message_renderer.py`.
`dialogs/`: one file per dialog.

### Where does a new file go
- Talks to the network, a database or the protocol, or is plain data and state → `core/`
- Non-visual helper or manager used by several files → `helpers/`
- Widget reused by two or more screens → `components/`
- A whole screen, window or pane → `ui/` (`ui_<name>.py`)
- A modal dialog → `ui/dialogs/`
- Default setting values → `settings/config.json`; colors and theming → `themes/` and `helpers/color_utils.py`
- Persistent user data goes under `KG_Chat_Data` via `get_data_dir()`, never next to the sources.

## Imports

Every import block has three groups in this order, separated by exactly one blank line (no blank lines inside a group):

1. Python standard library (`json`, `re`, `threading`, `datetime`, `pathlib`, `typing`, ...)
2. Installed third-party packages (`PyQt6`, `requests`, `lxml`, ...)
3. Project modules (`components`, `core`, `helpers`, `themes`, `ui`)

```python
import json
import re
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from core.self_ban import SelfBan
from helpers.translate import tr
```

- `from __future__ import annotations` goes first, above all groups, when used.
- Inside a group: plain `import x` lines first, then `from x import y` lines; each part sorted alphabetically by module name. In the project group sort by full module path.
- One `import` statement per module, one module per line: never `import re, json`.
- One imported name → one line. Several names that do not fit one line → parentheses, one name per line, trailing comma, names sorted alphabetically (case-insensitive).
- Project imports are absolute from the source root (`from core.x import y`), never relative.
- No wildcard imports, no unused imports, no underscore names imported from another module.
- Imports sit at the top of the file. A function-local import is allowed only to break a circular import and needs a one-line comment naming the cycle. Prefer removing the cycle by moving the shared code down into `core/` or `helpers/`.

## Naming

- Full, readable words. No abbreviations a reader would have to guess, no single letters (loop indices excepted), no cryptic shortenings.
- No digits in names of variables, constants, functions, classes or methods. Describe the difference in words instead.
- Keep names simple, but specific enough that they cannot collide with other names in scope or in the module, and never shadow builtins (`type`, `id`, `list`, `input`).
- A leading underscore marks what is used only inside its own file; a bare name marks what other files use. This applies to variables, constants, functions, classes and methods:
  - used only in this file (module level) or only inside this class (class members) → `_name`, `_CONSTANT`, `_helper()`, `_PrivateClass`
  - imported or called from another file → `name`, `CONSTANT`, `helper()`, `PublicClass`
  - local variables inside a function need no underscore
  - when something becomes shared or stops being shared, rename it so the prefix stays truthful
- Constants are UPPER_SNAKE_CASE, classes PascalCase, everything else snake_case. Related constants of one concept are grouped, not scattered as many sibling names.

## Good practices

- One responsibility per file and per function. Keep functions short, use early returns instead of deep nesting. Split a file when it starts to mix concerns.
- No magic numbers in function bodies: meaningful literals (intervals in milliseconds, sizes, limits) become named constants at the top of the file.
- Group related state into one small object or dict instead of many sibling variables that are passed, reset or removed together.
- Never block the UI thread. Network and heavy disk work run in a worker thread and return to the UI through the existing `_dispatch` signal; widgets are touched only from the main thread.
- Give every `QTimer`, widget and connection an owner (`parent=self`) and stop or disconnect it in the teardown path.
- Handle errors at boundaries only (file, network, parsing external data). Never a bare `except:`; catch `Exception` at most, and never hide a failure that the user needs to know about.
- Time: chatlog timestamps are Moscow time (`CHATLOG_TIMEZONE` in `core/chatlogs.py`), live XMPP stamps are UTC. Convert explicitly, never compare them to naive local time.
- Settings are read through `Config.get`; defaults live in code or `settings/config.json`. No hardcoded user paths.
- Public classes and functions get a one-line English docstring and type hints on new code.
- Add a dependency only when the standard library or an existing helper cannot do the job.
- Delete dead code and unused names instead of leaving them.
- Verify before delivering: the files compile (`python -m py_compile`) and any new logic is exercised with a quick check.

## Delivery

- Return only the files that were changed or newly created, at their project paths.
- Files use CRLF line endings: keep them in edited files and use them in new ones.
- Discuss with the user in Russian or English; keep all code and code comments in English.
