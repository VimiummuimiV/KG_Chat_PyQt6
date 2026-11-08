"""ChatWindow: own balance fetching and session re-authorization."""

import json
import threading

from core.web.scores import ERR_AUTH, ERR_NETWORK, ERR_NO_COOKIES, ERR_PARSE, fetch_scores_bonuses
from helpers.translate import tr
from ui.dialogs.html_dialog import show_warning_with_html
from ui.dialogs.web_login_dialog import LoginWebView


class ChatBalanceMixin:
    """ChatWindow: own balance fetching and session re-authorization."""

    def fetch_own_balance(self, gid: int):
        """Headless one-shot fetch of scores/bonuses."""
        # If both display options are off, no need to fetch
        show_scores = self.config.get("competitions", "show_scores")
        show_bonuses = self.config.get("competitions", "show_bonuses")
        if show_scores is False and show_bonuses is False:
            return

        cookies_json = (self.account or {}).get("session_cookies")
        if not cookies_json:
            self._on_balance_fetch_failed(ERR_NO_COOKIES)
            return
        try:
            cookies = json.loads(cookies_json)
        except Exception:
            self._on_balance_fetch_failed(ERR_NO_COOKIES)
            return

        def _fetch():
            data, err, debug_html = fetch_scores_bonuses(cookies)
            if err:
                self.dispatch.emit(lambda: self._on_balance_fetch_failed(err, debug_html))
                return
            scores, bonuses, updated_cookies = data
            self.dispatch.emit(
                lambda: self._on_own_balance_fetched(gid, scores, bonuses, updated_cookies)
            )

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_own_balance_fetched(self, gid: int, scores: int, bonuses: int, updated_cookies=None):
        live = self.competition_live.get(gid)
        if live is None:
            return
        self.balance_fetch_errors_shown.clear()
        live.update(scores=scores, bonuses=bonuses)
        self.refresh_competition_message(gid)
        if updated_cookies:
            self._persist_session_cookies(updated_cookies)

    def _on_balance_fetch_failed(self, error_code: str, debug_html: str = None):
        """One dialog + log line per error code per session."""
        if error_code in self.balance_fetch_errors_shown:
            return
        self.balance_fetch_errors_shown.add(error_code)

        messages = {
            ERR_NO_COOKIES: (
                "No website session cookies for this account. "
                "Re-authorize the account in Accounts to refresh your session.",
                "Отсутствуют session cookies для этого аккаунта. "
                "Повторно авторизуйтесь в разделе Аккаунты, чтобы актуализировоать сессию.",
            ),
            ERR_AUTH: (
                "Website session expired or is not authorized. "
                "Re-authorize the account in Accounts.",
                "Сессия сайта истекла или не авторизована. "
                "Повторно авторизуйтесь в разделе Аккаунты.",
            ),
            ERR_NETWORK: (
                "Network error while loading scores/bonuses.",
                "Сетевая ошибка при загрузке очков/бонусов.",
            ),
            ERR_PARSE: (
                "Could not parse scores/bonuses from the site page. "
                "The page layout may have changed.",
                "Не удалось разобрать очки/бонусы со страницы сайта. "
                "Возможно, изменилась вёрстка.",
            ),
        }
        en, ru = messages.get(error_code, (
            f"Failed to load scores/bonuses ({error_code}).",
            f"Не удалось загрузить очки/бонусы ({error_code}).",
        ))
        self.append_competition_log(f"balance error: {error_code}")
        offer_auth = error_code in (ERR_NO_COOKIES, ERR_AUTH)
        show_warning_with_html(
            self,
            tr("Scores / bonuses", "Очки / бонусы"),
            tr(en, ru),
            debug_html,
            action_text=tr("Authorize", "Авторизоваться") if offer_auth else None,
            on_action=self._reauthorize_session if offer_auth else None,
        )

    def _reauthorize_session(self):
        """Open browser login to refresh website session cookies for this account."""

        dlg = LoginWebView(self)
        dlg.login_success.connect(self._on_reauth_success)
        dlg.exec()

    def _on_reauth_success(self, user_data: dict):
        login = user_data.get("login")
        cookies = user_data.get("cookies")
        if not login or not cookies:
            print(f"⚠️ reauth: missing login/cookies login={login!r} cookies={bool(cookies)}")
            return
        names = sorted(c.get("name") for c in cookies if c.get("name"))
        print(
            f"🔄 reauth: login={login!r} cookies={names} "
            f"PHPSESSID={'yes' if 'PHPSESSID' in names else 'NO'}"
        )
        cookies_json = json.dumps(cookies)
        if self.xmpp_client:
            ok = self.xmpp_client.account_manager.update_session_cookies(login, cookies_json)
            print(f"🔄 reauth: DB write → {ok}")
        if self.account and self.account.get("chat_username") == login:
            self.account["session_cookies"] = cookies_json
            # Clear any previous errors so the next fetch attempt can succeed
            self.balance_fetch_errors_shown.discard(ERR_NO_COOKIES)
            self.balance_fetch_errors_shown.discard(ERR_AUTH)
            print("🔄 reauth: in-memory account.session_cookies updated")
            for gid in list(self.competition_live):
                self.fetch_own_balance(gid)

    def _persist_session_cookies(self, cookies: list):
        """Write rotated session cookies back to storage (server-side renewal only)."""
        if not self.account or not self.xmpp_client:
            return
        cookies_json = json.dumps(cookies)
        self.xmpp_client.account_manager.update_session_cookies(self.account['chat_username'], cookies_json)
        self.account['session_cookies'] = cookies_json
