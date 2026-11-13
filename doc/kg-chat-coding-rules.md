---
name: kg-chat-coding-rules
description: Coding conventions and project structure for KG_Chat_PyQt6, the PyQt6 XMPP chat client for Klavogonki (main.py, core/, helpers/, components/, ui/, themes/, settings/). Covers clean-code rules (no duplication, no over-engineering), where every new file must live, import order, naming rules (full names, no digits, leading underscore for file-private names), styling and themes (QSS templates with palette tokens, object names and properties instead of per-widget setStyleSheet, when QSS is not the tool, fast theme switching), SVG icon folders and file naming, good practices and delivery rules. Use whenever writing, editing, reviewing or adding files to this project, even for small changes, and whenever the user mentions the chat client, ui_chat.py, KG_Chat_Data, Klavobot, or any file or folder from this project.
---

# KG_Chat_PyQt6 coding rules

## Clean code

- No over-engineering. Add only what the task needs: no speculative classes, layers, options, abstractions or state. Prefer the simplest direct solution.
- No duplication. Before writing anything, search the project for code that does the same thing by nature (storage, colors, translation, parsing, styling, threading) and reuse or extend it. When two places need the same logic, extract it once into the right shared location and make both use it. Matching by nature counts, not only identical text.
- Clean separation of concerns. Logic, storage and network code live in `core/`; widgets only display and wire signals. Do not grow a screen file with logic that has a natural home elsewhere.
- Keep files focused. A file around 500 lines or a class that mixes concerns is split: a big widget class becomes a shell class plus mixin files `<screen>_<topic>.py` (see ui/chat/), module-level helpers go to their own file.
- Comments are minimal: a terse one-liner only where the reason is non-obvious. No multi-line explanatory blocks, no decorative banners, no narration of history, no commented-out code. All comments and docstrings are in English.
- User-visible strings go through `tr("English", "Русский")` so they follow the interface language live. Code, comments and identifiers stay English.
- Do not refactor or rename unrelated code. Match the style of the surrounding file.
- Before finalizing check for: duplicates, unused names, needless variables or helpers, comments that restate the code, anything that could be simpler.

## Project structure

Put every new file in the folder that owns its kind of code. Never drop a file in a folder just because it is nearby.

A folder exists only for a group of related files (a shell file with its mixins, one concern split in several files). A single file with no related files sits directly in the parent folder: never create a folder for one file. When a second related file appears, move both into a feature folder and fix the imports.

```
requirements.txt        Python dependencies
doc/                    texts and notes, not code
scripts/                nothing here is imported by the app
  setup/                install.bat, install.sh, uninstall.bat, uninstall.sh
  launchers/            launcher.pyw (Windows), launcher.sh (Linux)
src/                    all application code below lives in src/ (the source root for imports)
main.py                 application entry: tray, account window, global hotkey, exit
settings/config.json    default configuration (the user config overrides it)
themes/                 everything about the look, see Styling and themes
  theme.py              ThemeManager: current theme, one app.setStyleSheet per switch
  palette.py            color tokens of every theme, the only place where theme colors are defined
  stylesheet.py         build_stylesheet (qdarktheme base + styles/*.qss, cached per theme), repolish, set_style_property
  styles/               one <component>.qss template per component, filled with palette tokens
bin/ emoticons/ fonts/ sounds/          bundled resources, not Python code
icons/                  bundled icons: chat.ico in the root, SVGs only in the subfolders below (see Icons)
  line/                 outline icons, every file name ends with -line.svg
  fill/                 solid icons, every file name ends with -fill.svg
  emoticon_groups/      full-colour Noto Color Emoji icons of the group buttons in ui/chat/ui_emoticon_selector.py
core/                   no widgets: data, network, XMPP, parsing, persistence
  xmpp/                 client.py (BOSH), messages.py, userlist.py, jid_utils.py
  chatlogs/             fetch.py, database.py (SQLite), range_parser.py (workers), workers_calculator.py
  web/                  api_data.py, scores.py, races_listener.py, youtube.py, image_loader.py (parallel image downloads + LRU cache)
  state/                accounts.py, user_state.py (ByUserStore), presence_db.py, mentions_digest.py, self_ban.py
helpers/                shared non-visual logic and managers
  config.py data.py translate.py cache.py load.py dates.py browser.py sounds.py   (top level)
  colors/               color_utils.py, color_contrast.py
  fonts/                fonts.py, font_scaler.py
  text/                 emoticons.py, me_action.py, mention_parser.py
  system/               hotkey_manager.py, power_monitor.py, startup_manager.py, input_activity.py
  window/               window_size_manager.py, resize.py
  users/                ban_manager.py, user_tracker.py, pronunciation_manager.py, username_color_manager.py, presence_log.py
  scroll/               scrolling behavior and scroll buttons
  voice/                TTS and voice input engines
components/             reusable widgets used by more than one screen
  context_menu/         message and userlist context menus
  image_viewer/         viewer.py (ImageHoverView) + gallery.py (image URLs, ImageGallery), layer.py (layers, transitions), overlay.py (gallery bar, source badge), options.py (config defaults and accessors)
  button.py avatar.py video_player.py help_panel.py flash_highlight.py font_scale_slider.py
  presence_badge.py search.py tag_button.py mic_button.py loading_spinner.py user_count_row.py tracked_mark.py tray_badge.py colored_label.py
ui/                     screens and windows of the app
  chat/                 ui_chat.py (ChatWindow shell) + chat_*.py mixins (chat_hotkeys.py = local keyboard shortcuts), ui_room, ui_messages, ui_userlist, ui_buttons, ui_emoticon_selector, voice_input_attach
  tracker/              ui_user_tracker.py + tracker_*.py mixins and models
  chatlog/              ui_chatlog.py + chatlog_*.py mixins, ui_chatlog_userlist, ui_chatlogs_parser.py + parser_*.py
  messages/             message_model, message_delegate, message_renderer, messages_separator, message_interactions
  settings/             ui_settings.py (SettingsWidget shell) + settings_*.py mixins (one per section, e.g. settings_image_viewer.py), settings_options, settings_widgets, sound_selector
  account/              ui_accounts, ui_profile
  ui_banlist.py ui_pronunciation.py   single panels with no related files, directly in ui/
  notification/         popup_manager, popup_notification, presence_popup, message_body, notification_data, notification_settings, popup_helpers, auto_hide_popup
  dialogs/              one file per modal dialog (including web_login_dialog.py)
```

### Rules for each folder
- `core/`: nothing here builds a widget. Small per-account JSON state reuses `ByUserStore` from `core/state/user_state.py` instead of new load/save code.
- `helpers/`: non-visual only. Colors: new app palettes follow the `get_*_colors` pattern in `helpers/colors/color_utils.py` (hue and saturation from config, defaults in code).
- `components/`: widgets reused by two or more screens; must not import from `ui/`. Code that both a component and `ui/` need goes down into `components/` or `helpers/` (avatars: `components/avatar.py`), never imported upward.
- A component with its own options keeps their defaults, limits and config accessors in its own `options.py`; the settings page imports them from there instead of repeating the numbers.
- Switching an icon button's icon at runtime: `set_button_icon` from `components/button.py`.
- Every new hotkey or mouse action of a view is registered in the matching context of `components/help_panel.py` (F1).
- `ui/`: screens. A mixin file contains only methods of one concern of its shell class.

### Where does a new file go
- Talks to the network, a database or the protocol, or is plain data and state → `core/<xmpp|chatlogs|web|state>/`
- Non-visual helper or manager used by several files → `helpers/<topic>/`
- Widget reused by two or more screens → `components/`
- A whole screen, window or pane → its feature folder in `ui/` (`ui_<name>.py`); if it has no related files, directly in `ui/` without its own folder
- Install, uninstall or launch script → `scripts/setup/` or `scripts/launchers/`; they locate the project root two levels up
- A modal dialog → `ui/dialogs/`
- Default setting values → `settings/config.json`; theme colors and the look of widgets → `themes/` (tokens in `palette.py`, rules in `styles/<component>.qss`); colors computed from data or settings → `helpers/colors/color_utils.py`
- Persistent user data goes under `KG_Chat_Data` via `get_data_dir()`, never next to the sources.
- A new SVG icon → `icons/line/` or `icons/fill/` by its style, named by the Icons rules; a group button icon of the emoticon panel → `icons/emoticon_groups/`
- Bundled resources (icons, sounds, fonts, emoticons) are located with `get_resource_dir("icons")` from `helpers/data.py`, never with `Path(__file__)` arithmetic, so moving a file cannot break the path.

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

from core.state.self_ban import SelfBan
from helpers.translate import tr
```

- `from __future__ import annotations` goes first, above all groups, when used.
- Inside a group: plain `import x` lines first, then `from x import y` lines; each part sorted alphabetically by module name. In the project group sort by full module path.
- One `import` statement per module, one module per line: never `import re, json`.
- One imported name → one line. Several names that do not fit one line (about 100 characters) → parentheses, one name per line, trailing comma, names sorted alphabetically (case-insensitive).
- Project imports are absolute from the source root (`from core.xmpp.client import XMPPClient`), never relative.
- No wildcard imports, no unused imports, no underscore names imported from another module.
- Imports sit at the top of the file. A function-local import is allowed only to break a circular import (one-line comment naming the cycle) or for a Windows-only / optional third-party module (one-line comment saying so). Prefer removing the cycle by moving shared code down into `core/` or `helpers/`.
- QtWebEngine is imported at module level; `main.py` sets `AA_ShareOpenGLContexts` before any project import.

## Naming

- Full, readable words. No abbreviations a reader would have to guess, no single letters (loop indices excepted), no cryptic shortenings.
- No digits in names of variables, constants, functions, classes, methods or arguments (`is_not_found`, not `is_404`; `auth_encoded`, not `auth_b64`). Describe the difference in words instead.
- Keep names simple, but specific enough that they cannot collide with other names in scope or in the module, and never shadow builtins (`type`, `id`, `list`, `input`).
- The same kind of block has the same name in every file. Before naming a layout, panel, splitter or container, look at how the sibling files name it (`ui_chat.py` ↔ `ui_room.py`, a shell ↔ its mixins) and reuse that name; when two files call one block differently, rename them all in the same change. Layouts are named by role: `main_layout` (top layout of the widget), `content_layout` (the columns), `left_layout`, `userlist_layout`, `header_layout`, `button_layout`; the widget that holds a layout is `<role>_panel` (`userlist_layout` is set on `self.userlist_panel`). No generic or shortened names such as `root`, `body`, `left`, `ul_layout`, `gen_layout`.
- Full words, never abbreviations, in every kind of name (locals, parameters, attributes, methods, constants): `button` (not `btn`), `label` (`lbl`), `index` (`idx`), `config` (`cfg`), `value` (`val`), `dialog` (`dlg`), `context` (`ctx`), `command` (`cmd`), `username` (`uname`), `element` (`elem`), `action` (`act`), `font_metrics` (`fm`), `timestamp` (`ts`), `background` / `foreground` (`bg` / `fg`), `scroll_bar` (`sb`), `game_id` (`gid`), `error` (`err`), and `_width` / `_height` as name suffixes (not `_w` / `_h`). Units stay as suffixes (`_ms`), coordinates stay `x` / `y`.
- Underscore by use: a name used only inside its own file starts with `_` (module-level functions and constants, classes, methods, attributes); a name used from another file has none. A name that starts with `_` is never imported or accessed from another file. Check the real usage in the whole project before choosing.
- A layout, the widget that owns it and an attribute never share one name: a local variable must not carry the name of an attribute of the same object (a layout `userlist_panel` next to the widget `self.userlist_panel`). A new or renamed name is checked against every name already in its function, class and module before it is used.
- A leading underscore marks file-private names; a bare name marks names used from other files. This applies to every kind of name — variables, constants, functions, classes, methods, attributes:
  - used only inside this one file → `_name`, `_CONSTANT`, `_helper()`, `_PrivateClass`
  - read, called, connected or imported from another file (including a sibling mixin of the same shell class, e.g. `ui_chat.py` ↔ `chat_*.py`) → `name`, `CONSTANT`, `helper()`, `PublicClass` — no leading underscore
  - local variables inside a function need no underscore
  - when something becomes shared across files or stops being shared, rename it project-wide so the prefix stays truthful (also dynamic attributes set on other objects and `getattr` strings)
- Constants are UPPER_SNAKE_CASE, classes PascalCase, everything else snake_case. Related constants of one concept are grouped, not scattered as many sibling names.

## Styling and themes

The look of the app is one application stylesheet. A theme switch is one `app.setStyleSheet` of a cached string and nothing else: no loop that restyles widgets one by one. Reason: every widget with its own `setStyleSheet` costs about ten times more on each switch than a widget without one (measured ~1.5 ms against ~0.1 ms per widget), so hundreds of such widgets made a switch take over a second.

### Where things live
- `themes/palette.py`: color tokens per theme (`PALETTES["dark"]` / `["light"]`). Both themes have exactly the same keys. A token is named by its role (`panel_bg`, `text_muted`), never by its value or color name. A value that is the same in both themes is a literal in the `.qss`, not a token.
- `themes/styles/<component>.qss`: the rules of one component, written as `$token` templates. Every `.qss` in the folder is picked up automatically in alphabetical order; there is no registry. QSS `{}` braces are literal, only `$name` is substituted.
- `themes/stylesheet.py`: `build_stylesheet(theme)` (qdarktheme base + all templates, built once per theme), `repolish(widget)` and `set_style_property(widget, name, value)`.
- `themes/theme.py`: `ThemeManager` only applies the built string; it knows no colors.

### How a widget gets its look
- By `setObjectName("camelCaseRole")` (id selector `#role` or `QLabel#role`) and, for a state, a dynamic property. The widget code never contains a color or a stylesheet string for a static or theme-dependent look.
- A state (`highlighted`, `active`, `filtered`, `validation`, `loaded`) is a property selected in QSS (`QLineEdit[validation="invalid"]`), switched with `set_style_property`. Hover, pressed and disabled are QSS pseudo-states, never code.
- `update_theme` of a widget never rebuilds styles. It does only what QSS cannot express (see below) and is skipped or deferred while the widget is hidden (apply in `showEvent`).
- Names used in QSS (object names, property names) are camelCase strings; each one is defined in exactly one `.qss` file. Search the existing `.qss` files before adding a rule: reuse `mutedHint`, `mutedLabel`, `avatar` and the other shared ones from `common.qss` instead of a second copy.

### Writing the rules
- Qt precedence: a widget's own stylesheet and its ancestors' sheets beat the application sheet; inside the application sheet an id selector beats the qdarktheme type rules, and for equal specificity the later rule wins (file order, so alphabetical). Check a new rule against the qdarktheme base, do not guess.
- A plain `QWidget { }` or `QFrame { }` rule hits every descendant, and a `QLabel` is a `QFrame`. When a component relied on that cascade, write it explicitly (`#panel, #panel QWidget { }`), then give the specific rules after it.
- A custom `QWidget` subclass paints a QSS background only with `WA_StyledBackground`; `QFrame` subclasses (and `QLabel`) paint it themselves. A subclass that overrides `paintEvent` must not draw the styled background a second time.
- Verify a migration visually: render the widget offscreen before and after in both themes and compare the images; the result must be pixel-identical unless a change is intended.

### Where QSS is not the tool
QSS cannot carry a value that is data or that is used by code. These stay in code, still without a per-widget stylesheet where there are many widgets:
- Text color that is data (username colors, rank colors, event or kind colors): `ColoredLabel` from `components/colored_label.py` and `set_text_color`, never one `setStyleSheet` per row. Rows of a list are always painted or use such a widget.
- Colors used by painting, SVG icons or rich text (`QPainter`, `render_svg_icon(color=...)`, HTML `<span style>`): a small palette dict next to the code that paints. Do not copy such a dict into a second place; if QSS needs the same value, the dict is the source and the QSS gets it from there.
- Colors computed from user settings (input hue and saturation, gradient sliders, previews) or from a base color (tinted chips, badges): one helper builds the string and it is applied to the single widget that needs it. Never in a loop over many widgets and never on a theme switch.
- Files that depend on the theme (emoticon GIFs `dark/` and `light/`, placeholder avatars): reload only what differs, skip the unchanged ones, build lazily and refresh on `showEvent` when hidden.
- A short-lived dialog whose palette also feeds its rich text may keep one local stylesheet; it must not grow per-widget styles.

### A theme switch must stay cheap
- The sequence is: apply the cached application stylesheet, then update only what QSS cannot do. Wrap the application of the stylesheet in `freeze_row_sizes()` when list views exist, so row heights are measured once, then relayout.
- Never call `set_application_font` after a theme change: the stylesheet does not change fonts. It runs once at startup and when a font setting changes; a repeated call is a bug (it also prints twice).
- A global event filter returns early for events it does not handle: read `event.type()` once into a local variable, never call it repeatedly (each call builds an enum).
- Create heavy widget groups on first use, not at startup (the emoticon groups are built when first opened). A hidden but polished widget still costs on every stylesheet change.
- Cache lookups that scan all users (`login → user_id` index in `helpers/cache.py`); no linear search in a path that runs per row or per paint.
- Measure before and after in an offscreen Qt run (`QT_QPA_PLATFORM=offscreen`, hundreds of messages, dozens of users): time `toggle_theme()` and look for functions that run thousands of times with `cProfile`.

## Icons

- SVG icons live only in `icons/line/` (outline) or `icons/fill/` (solid), plus the one special folder `icons/emoticon_groups/` (below). Never loose in `icons/`; only `chat.ico` stays in its root. A file name ends with `-line` or `-fill` and the suffix always matches the folder.
- The name is the original icon name from the library it came from (Remix Icons or Feather Icons, lowercase kebab-case), never a name by usage (`close-large-line`, not `close-button`; `delete-bin-fill`, not `trash`). Original names keep similar symbols apart: `close-large-line` (plain X) and `close-circle-line` (X in a circle), `delete-bin-fill` and `delete-bin-2-fill`.
- Remix names already end with `-line` / `-fill` and are kept as is (`user-3-fill`, `arrow-left-s-line`). A name without a style suffix gets one: Remix `align-center` → `align-center-line`, `hashtag` → `hashtag-line`; every Feather icon is stroke-based, so it gets `-line` (`chevron-down-line`).
- A modified or hand-made icon keeps the name of the icon it is based on and puts the change in front of the suffix: `calendar-arrow-left-fill`, `delete-bin-2-up-fill`. The style comes from how the icon is drawn (outline or solid), not from its base: a hand-made solid icon is `-fill` even when it resembles a `-line` icon.
- When a shape looks the same in both styles (a plain X, a spinner), it is a line icon.
- Code refers to an icon with its folder: `"line/close-large-line.svg"`, `"fill/user-3-fill.svg"` (`icons_path / name` stays unchanged). When an icon is renamed or moved, update every reference in the same change.
- `icons/emoticon_groups/` holds the colour icons of the emoticon panel group buttons, taken from Noto Color Emoji. Names are the Noto / CLDR emoji names (`christmas-tree.svg`, `red-heart.svg`) with no `-line` / `-fill` suffix, because these icons are never recoloured: load them with `QIcon(path)`, not `render_svg_icon`. Qt SVG needs plain presentation attributes: no `style="..."`, no `<use>`, and `clipPath` only inside `<defs>`. A new group gets its icon from there, never an emoji character in a button text.
- Digits in icon file names are allowed: they mirror the original library names. The no-digits rule above is for code identifiers.

## Good practices

- One responsibility per file and per function. Keep functions short, use early returns instead of deep nesting. Split a file when it starts to mix concerns.
- No magic numbers in function bodies: meaningful literals (intervals in milliseconds, sizes, limits) become named constants at the top of the file.
- Group related state into one small object or dict instead of many sibling variables that are passed, reset or removed together.
- Never block the UI thread. Network and heavy disk work run in a worker thread and return to the UI through the existing `_dispatch` signal of ChatWindow; widgets are touched only from the main thread.
- Never use a name bound by `except ... as e` inside a deferred callback (lambda, `QTimer.singleShot`): Python deletes it when the block ends. Copy it to a variable first.
- Registries that other modules append to are shared through a function (`register_icon_button`), never by importing the list itself.
- Give every `QTimer`, widget and connection an owner (`parent=self`) and stop or disconnect it in the teardown path.
- Handle errors at boundaries only (file, network, parsing external data). Never a bare `except:`; catch `Exception` at most, and never hide a failure that the user needs to know about.
- Time: chatlog timestamps are Moscow time (`CHATLOG_TIMEZONE` in `core/chatlogs/fetch.py`), live XMPP stamps are UTC. Convert explicitly, never compare them to naive local time.
- Settings are read through `Config.get`; defaults live in code or `settings/config.json`. No hardcoded user paths.
- Public classes and functions get a one-line English docstring and type hints on new code.
- Add a dependency only when the standard library or an existing helper cannot do the job.
- Delete dead code and unused names instead of leaving them.
- Verify before delivering: the files compile (`python -m py_compile`), pyflakes is clean, every module imports (offscreen Qt), every `.svg` name used in code exists in its icon folder, every `$token` of a `.qss` exists in both palettes, no new or renamed name collides with or shadows another, and any new logic is exercised with a quick check. A change to styling or theming is checked in both themes (offscreen screenshots before and after) and a theme switch is toggled back and forth.

## Delivery

- Return only the files that were changed or newly created, at their project paths. After a restructure return the full tree as a zip plus the list of moved and removed files.
- Files use CRLF line endings: keep them in edited files and use them in new ones.
- Discuss with the user in Russian or English; keep all code and code comments in English.
