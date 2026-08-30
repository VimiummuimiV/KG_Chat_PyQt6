from PyQt6.QtCore import QUrl, pyqtSignal, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWebEngineCore import QWebEngineScript, QWebEngineProfile, QWebEnginePage
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QWidget, QStackedLayout

from components.loading_spinner import LoadingSpinner
from helpers.translate import tr


_CHAT_PARAMS = """
(function() {
    var m = document.documentElement.innerHTML.match(/chatParams:\\s*(\\{.+?\\})\\s*\\}/);
    if (!m) return null;
    try { return JSON.parse(m[1]); } catch(e) { return null; }
})();
"""

_LOGGED_OUT = "!document.querySelector('#login_form, .login-form');"

_UI_ENHANCE = """
(function() {
    var path = (location.pathname || '/').replace(/\\/+$/, '') || '/';
    if (path !== '/login' && !path.endsWith('/login')) return;

    const colorLogin = '120, 100%, 76%';
    const colorPass  = '45, 100%, 76%';
    const colorCode  = '200, 100%, 76%';
    const colorError = '0, 100%, 66%';

    var s = document.createElement('style');
    s.textContent = `
        .ownbanner-back,
        #head,
        #footer,
        #reformal_tab,
        .feedback {
            display: none !important;
        }

        #content {
            min-width: 300px !important;
            min-height: 200px !important;
        }

        html, body {
            background: #000000 !important;
        }

        #login-page table {
            width: 100% !important;
            border-collapse: collapse !important;
        }

        #login-page table tbody,
        #login-page table tr {
            display: block !important;
            width: 100% !important;
        }

        #login-page table th,
        #login-page h4,
        #login-page table td[colspan],
        #login-page .links {
            display: none !important;
        }

        #login-page table td {
            display: block !important;
            width: 100% !important;
            padding: 0 !important;
            box-sizing: border-box !important;
        }

        #login-page .big {
            margin: 0 0 8px !important;
            background-color: #111111 !important;
            border-radius: 8px !important;
            overflow: hidden !important;
            border: 2px solid transparent !important;
            transition: border-color 0.2s !important;
            display: flex !important;
            flex-direction: column !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }

        #login-page .big input {
            background: transparent !important;
            padding: 8px !important;
            border: none !important;
            outline: none !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }

        #login-page .big:has(input[name="login"]) input {
            color: hsl(${colorLogin}) !important;
        }

        #login-page .big:has(input[name="pass"]) input {
            color: hsl(${colorPass}) !important;
        }

        #login-page .big:has(input[name="code"]) input {
            color: hsl(${colorCode}) !important;
            letter-spacing: 0.12em !important;
        }

        #login-page .big:has(input[name="login"])::before {
            content: "Логин";
            display: block;
            color: hsl(${colorLogin});
            font-size: 11px;
            padding: 4px 8px 0;
        }

        #login-page .big:has(input[name="pass"])::before {
            content: "Пароль";
            display: block;
            color: hsl(${colorPass});
            font-size: 11px;
            padding: 4px 8px 0;
        }

        #login-page .big:has(input[name="code"])::before {
            content: "Код";
            display: block;
            color: hsl(${colorCode});
            font-size: 11px;
            padding: 4px 8px 0;
        }

        #login-page .big:has(input[name="login"]):has(input:focus) {
            border-color: hsl(${colorLogin}) !important;
        }

        #login-page .big:has(input[name="pass"]):has(input:focus) {
            border-color: hsl(${colorPass}) !important;
        }

        #login-page .big:has(input[name="code"]):has(input:focus) {
            border-color: hsl(${colorCode}) !important;
        }

        #login-page .smart-captcha {
            filter: invert(93%) !important;
        }

        #login-page .error {
            padding: 8px 0 0 !important;
            color: hsl(${colorError}) !important;
        }

        #login-page #submit_login {
            margin: 8px 0 0 !important;
            height: 50px !important;
            width: 100% !important;
            box-sizing: border-box !important;

            font-size: 0 !important;
            color: transparent !important;

            background: hsla(${colorLogin}, 0.15)
                url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='hsl(${colorLogin})' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E\\
            %3Cpath d='M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4'/%3E\\
            %3Cpolyline points='10 17 15 12 10 7'/%3E\\
            %3Cline x1='15' y1='12' x2='3' y2='12'/%3E\\
            %3C/svg%3E")
                center / 24px 24px no-repeat !important;

            border: none !important;
            padding: 8px 16px !important;
            border-radius: 8px !important;
            cursor: pointer !important;
            transition: background-color 0.2s !important;
        }

        #login-page #submit_login:hover {
            background-color: hsla(${colorLogin}, 0.25) !important;
        }
    `;
    (document.head || document.documentElement).appendChild(s);

    document.querySelectorAll('#login-page .big').forEach(function(big) {
        big.style.cursor = 'text';
        big.addEventListener('click', function() {
            var input = big.querySelector('input');
            if (input) input.focus();
        });
    });

    var focus = document.querySelector('#login-page input[name="code"]')
             || document.querySelector('#login-page input[name="login"]');
    if (focus) focus.focus();
})();
"""


class LoginWebView(QDialog):
    """Browser login → gamelist chatParams → login_success(dict)."""

    login_success = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        self.setWindowTitle(tr("Authorization", "Авторизация"))
        self.resize(360, 360)
        self.setStyleSheet("background:#000;")
        self._navigating_to_gamelist = False
        self._spinner = LoadingSpinner(None, 48)
        self._captured_cookies = {}

        self._view = QWebEngineView()
        self._profile = QWebEngineProfile(self)
        self._page = QWebEnginePage(self._profile, self._view)
        self._view.setPage(self._page)
        self._page.setBackgroundColor(QColor(0, 0, 0))
        self._profile.cookieStore().cookieAdded.connect(self._on_cookie_added)

        palette = self._view.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0))
        self._view.setPalette(palette)
        self._view.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        script = QWebEngineScript()
        script.setSourceCode(_UI_ENHANCE)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self._page.scripts().insert(script)

        root = QWidget(self)
        root.setStyleSheet("background:#000;")
        stack = QStackedLayout(root)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self._view)

        self._wait_bg = QWidget()
        self._wait_bg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._wait_bg.setStyleSheet("background:#000;")
        stack.addWidget(self._wait_bg)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(root)

        self._view.loadStarted.connect(lambda: self._show_wait(True))
        self._view.urlChanged.connect(self._on_url_changed)
        self._view.loadFinished.connect(self._on_load_finished)

        self._show_wait(True)
        self._view.load(QUrl("https://klavogonki.ru/login"))

    @staticmethod
    def _is_login_url(url: str) -> bool:
        path = QUrl(url).path().rstrip("/") or "/"
        return path == "/login" or path.endswith("/login")

    def _center_spinner(self):
        size = self._spinner.spinner_size
        c = self.mapToGlobal(self.rect().center())
        self._spinner.move(c.x() - size // 2, c.y() - size // 2)

    def _show_wait(self, visible: bool):
        self._wait_bg.setVisible(visible)
        if visible:
            self._wait_bg.raise_()
            self._center_spinner()
            self._spinner.start()
        else:
            self._spinner.stop()

    def _stop_spinner(self):
        if self._spinner is not None:
            self._spinner.stop()
            self._spinner.deleteLater()
            self._spinner = None

    def moveEvent(self, event):
        super().moveEvent(event)
        if self._spinner and self._wait_bg.isVisible():
            self._center_spinner()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._spinner and self._wait_bg.isVisible():
            self._center_spinner()

    def done(self, result):
        self._stop_spinner()
        super().done(result)

    def _on_url_changed(self, url: QUrl):
        if not self._is_login_url(url.toString()):
            self._show_wait(True)

    def _on_load_finished(self, ok: bool):
        url = self._view.url().toString()
        if not ok or not self._is_login_url(url):
            self._show_wait(True)
            if ok and url.rstrip("/").endswith("/gamelist"):
                self._view.page().runJavaScript(_CHAT_PARAMS, self._on_data)
            elif ok and not self._navigating_to_gamelist:
                self._view.page().runJavaScript(_LOGGED_OUT, self._on_logged_in_check)
            return
        self._show_wait(False)

    def _on_cookie_added(self, cookie):
        domain = cookie.domain().lstrip(".")
        if "klavogonki.ru" not in domain:
            return
        name = bytes(cookie.name()).decode("utf-8", "ignore")
        value = bytes(cookie.value()).decode("utf-8", "ignore")
        if not name:
            return
        self._captured_cookies[name] = {
            "name": name,
            "value": value,
            "domain": cookie.domain(),
            "path": cookie.path(),
        }

    def _on_logged_in_check(self, logged_in: bool):
        if logged_in and not self._navigating_to_gamelist:
            self._navigating_to_gamelist = True
            self._show_wait(True)
            self._view.load(QUrl("https://klavogonki.ru/gamelist/"))

    def _on_data(self, data):
        if not data or not isinstance(data, dict):
            self.reject()
            return
        user = data.get("user") or {}
        self.login_success.emit({
            "id": user.get("id"),
            "login": user.get("login"),
            "pass": data.get("pass"),
            "avatar": (user.get("avatar") or "").replace("\\/", "/"),
            "background": user.get("background") or "#808080",
            "cookies": list(self._captured_cookies.values()),
        })
        self.accept()