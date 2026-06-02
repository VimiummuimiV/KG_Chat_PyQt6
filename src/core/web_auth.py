from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEngineScript
from PyQt6.QtWidgets import QDialog, QVBoxLayout


_CHAT_PARAMS = """
(function() {
    var m = document.documentElement.innerHTML.match(/chatParams:\\s*(\\{.+?\\})\\s*\\}/);
    if (!m) return null;
    try { return JSON.parse(m[1]); } catch(e) { return null; }
})();
"""

_LOGGED_OUT = "!document.querySelector('#login_form, .login-form');"

_UI_CLEANUP = """
(function() {
    const hideSelectors = [
        '.ownbanner-back',
        '#head',
        '#footer',
        '#reformal_tab',
        '.feedback'
    ];
    const hideStyle = document.createElement('style');
    hideStyle.textContent = `${hideSelectors.join(', ')} { display: none !important; }`;
    (document.head || document.documentElement).appendChild(hideStyle);

    const geometryStyle = document.createElement('style');
    geometryStyle.textContent = '#content { min-width: 300px !important; min-height: 200px !important; }';
    (document.head || document.documentElement).appendChild(geometryStyle);

    const darkForm = document.createElement('style');
    darkForm.textContent = `
        html, body { background: #000000 !important; }

        #login-page h4, 
        #login-page table th,
        #login-page .links { display: none !important; }

        #login-page .big {
            margin: 0 0 8px !important;
            background-color: #111111 !important;
            border-radius: 8px !important;
            overflow: hidden !important;
            border: none !important;
        }
        #login-page .big input {
            background: transparent !important;
            color: #ededed !important;
            padding: 8px !important;
            width: 100% !important;
            border: none !important;
            outline: none !important;
        }

        #login-page .smart-captcha {
            filter: invert(93%) !important;
        }

        #login-page .error {
            padding: 8px 0 0 !important;
            color: #ff5555 !important;
        }

        #login-page #submit_login {
            margin: 8px 0 0 !important;
            width: 100% !important;
            background-color: #111111 !important;
            color: #ededed !important;
            border: none !important;
            padding: 8px 16px !important;
            border-radius: 8px !important;
            cursor: pointer !important;
        }
    `;
    (document.head || document.documentElement).appendChild(darkForm);
})();
"""


class LoginWebView(QDialog):
    """Browser login dialog. Navigates to gamelist after login and emits login_success(dict)."""

    login_success = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        self.setWindowTitle("Log in to Klavogonki")
        self.resize(360, 320)
        self._navigating_to_gamelist = False

        self._view = QWebEngineView()

        script = QWebEngineScript()
        script.setSourceCode(_UI_CLEANUP)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self._view.page().scripts().insert(script)

        self._view.load(QUrl("https://klavogonki.ru/login"))
        self._view.loadFinished.connect(self._on_load_finished)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    def _on_load_finished(self, ok: bool):
        if not ok:
            return
        url = self._view.url().toString()

        if url.rstrip('/').endswith('/gamelist'):
            self._view.page().runJavaScript(_CHAT_PARAMS, self._on_data)
            return

        if '/login' not in url and not self._navigating_to_gamelist:
            self._view.page().runJavaScript(_LOGGED_OUT, self._on_logged_in_check)

    def _on_logged_in_check(self, logged_in: bool):
        if logged_in and not self._navigating_to_gamelist:
            self._navigating_to_gamelist = True
            self._view.load(QUrl("https://klavogonki.ru/gamelist/"))

    def _on_data(self, data):
        if not data or not isinstance(data, dict):
            self.reject()
            return
        user = data.get("user", {})
        avatar = (user.get("avatar") or "").replace("\\/", "/")
        self.login_success.emit({
            "id":         user.get("id"),
            "login":      user.get("login"),
            "pass":       data.get("pass"),
            "avatar":     avatar,
            "background": user.get("background") or "#808080",
        })
        self._view.page().profile().cookieStore().deleteAllCookies()
        self.accept()