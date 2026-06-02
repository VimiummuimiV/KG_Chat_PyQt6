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
        '.feedback',
        '.links'
    ];
    const hideStyle = document.createElement('style');
    hideStyle.textContent = `${hideSelectors.join(', ')} { display: none !important; }`;
    (document.head || document.documentElement).appendChild(hideStyle);

    const geometryStyle = document.createElement('style');
    geometryStyle.textContent = '#content { min-width: 300px !important; min-height: 300px !important; }';
    (document.head || document.documentElement).appendChild(geometryStyle);

    const invertStyle = document.createElement('style');
    invertStyle.textContent = `
        #content { filter: invert(100%) !important; }
        html, body { background: #2b2b2b !important; }
    `;
    (document.head || document.documentElement).appendChild(invertStyle);
})();
"""


class LoginWebView(QDialog):
    """Browser login dialog. Navigates to gamelist after login and emits login_success(dict)."""

    login_success = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        self.setWindowTitle("Log in to Klavogonki")
        self.resize(500, 500)
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
        self.accept()