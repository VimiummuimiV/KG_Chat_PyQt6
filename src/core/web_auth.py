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

_UI_ENHANCE = """
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

    const colorLogin = '#88ff88';
    const colorPass  = '#ffdd88';
    const colorError = '#ff5555';

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
            border: 2px solid transparent !important;
            transition: border-color 0.2s !important;
            display: flex !important;
            flex-direction: column !important;
        }
        #login-page .big input {
            background: transparent !important;
            padding: 8px !important;
            width: 100% !important;
            border: none !important;
            outline: none !important;
        }
        #login-page .big:has(input[name="login"]) input {
            color: ${colorLogin} !important;
        }
        #login-page .big:has(input[name="pass"]) input {
            color: ${colorPass} !important;
        }

        #login-page .big:has(input[name="login"])::before {
            content: "Логин";
            display: block;
            color: ${colorLogin};
            font-size: 11px;
            padding: 4px 8px 0;
        }

        #login-page .big:has(input[name="login"]):has(input:focus) {
            border: 2px solid ${colorLogin} !important;
        }

        #login-page .big:has(input[name="pass"])::before {
            content: "Пароль";
            display: block;
            color: ${colorPass};
            font-size: 11px;
            padding: 4px 8px 0;
        }

        #login-page .big:has(input[name="pass"]):has(input:focus) {
            border: 2px solid ${colorPass} !important;
        }

        #login-page .smart-captcha {
            filter: invert(93%) !important;
        }

        #login-page .error {
            padding: 8px 0 0 !important;
            color: ${colorError} !important;
        }

        #login-page #submit_login {
            margin: 8px 0 0 !important;
            height: 50px !important;
            width: 100% !important;

            font-size: 0 !important;
            color: transparent !important;

            background: #111111
                url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='${colorLogin.replace("#", "%23")}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E\
            %3Cpath d='M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4'/%3E\
            %3Cpolyline points='10 17 15 12 10 7'/%3E\
            %3Cline x1='15' y1='12' x2='3' y2='12'/%3E\
            %3C/svg%3E")
                center / 24px 24px 
                no-repeat !important;

            border: none !important;
            padding: 8px 16px !important;
            border-radius: 8px !important;
            cursor: pointer !important;
            transition: background-color 0.2s !important;
        }

        #login-page #submit_login:hover {
            background-color: #222222 !important;
        }
    `;
    (document.head || document.documentElement).appendChild(darkForm);

    document.querySelectorAll('#login-page .big').forEach(big => {
        big.style.cursor = 'text';
        big.addEventListener('click', () => big.querySelector('input')?.focus());
    });
})();
"""


class LoginWebView(QDialog):
    """Browser login dialog. Navigates to gamelist after login and emits login_success(dict)."""

    login_success = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        self.setWindowTitle("Log in to Klavogonki")
        self.resize(360, 360)
        self._navigating_to_gamelist = False

        self._view = QWebEngineView()

        script = QWebEngineScript()
        script.setSourceCode(_UI_ENHANCE)
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