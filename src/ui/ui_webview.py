"""Web view widget for displaying URLs within the chat"""
from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QMessageBox
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage, QWebEngineProfile

from helpers.create import create_icon_button
from helpers.fonts import get_font, FontType
from helpers.web_filter import AdBlocker


class CustomWebEnginePage(QWebEnginePage):
    """Custom page to suppress console warnings and handle crashes"""
    
    crash_detected = pyqtSignal()
    
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # Temporarily show all messages for debugging
        level_name = {
            QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel: "INFO",
            QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel: "WARN",
            QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel: "ERROR"
        }.get(level, "LOG")
        
        print(f"JS [{level_name}] {message} (line {lineNumber})")
    
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        # Allow all navigation (including redirects for YouTube)
        return True


class WebViewWidget(QWidget):
    """Widget for displaying web pages with navigation controls"""
    
    back_requested = pyqtSignal()
    
    def __init__(self, config, icons_path: Path, return_view: str = "messages"):
        super().__init__()
        self.config = config
        self.icons_path = icons_path
        self.return_view = return_view  # Track where to return: "messages" or "chatlog"
        self.web_view = None
        self.profile = None
        self.ad_blocker = None
        self.is_loading = False
        
        self._init_ui()
    
    def cleanup(self):
        """Cleanup webview to stop playback and free memory - fully self-contained"""
        print("🧹 Starting WebView cleanup...")
        
        if self.web_view:
            try:
                # Stop any ongoing loads
                self.web_view.stop()
                
                # Load blank page to stop media playback
                self.web_view.setUrl(QUrl("about:blank"))
                
                # Process events to ensure page unloads
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                
                # Disconnect signals
                try:
                    self.web_view.urlChanged.disconnect()
                    self.web_view.loadStarted.disconnect()
                    self.web_view.loadFinished.disconnect()
                    self.web_view.renderProcessTerminated.disconnect()
                except:
                    pass
                
                # Delete the web view
                self.web_view.deleteLater()
                self.web_view = None
            except Exception as e:
                print(f"Web view cleanup error: {e}")
        
        # Clear profile and ad blocker
        if self.profile:
            # Clear HTTP cache
            try:
                self.profile.clearHttpCache()
            except:
                pass
            self.profile = None
        
        self.ad_blocker = None
        
        # Remove from parent if still attached
        try:
            self.setParent(None)
        except:
            pass
        
        # Force garbage collection to free memory immediately
        import gc
        gc.collect()
        
        print("✅ WebView cleanup complete")
    
    def _init_ui(self):
        """Initialize UI"""
        margin = self.config.get("ui", "margins", "widget") or 5
        spacing = self.config.get("ui", "spacing", "widget_elements") or 6
        
        # Set background color on the main widget to prevent transparency
        from themes.theme import ThemeManager
        theme_manager = ThemeManager(self.config)
        is_dark = theme_manager.is_dark()
        
        bg_color = "#1e1e1e" if is_dark else "#ffffff"
        
        self.setStyleSheet(f"""
            WebViewWidget {{
                background-color: {bg_color};
            }}
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # No margins
        layout.setSpacing(0)  # No spacing between nav and webview
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # Align content to top
        self.setLayout(layout)
        
        # Create navigation bar container
        nav_container = QWidget()
        nav_container.setObjectName("webview_nav_container")
        
        # Navigation bar layout inside container
        nav_bar = QHBoxLayout()
        nav_bar.setSpacing(self.config.get("ui", "buttons", "spacing") or 8)
        nav_container.setLayout(nav_bar)
        
        # Back to chat button
        self.back_button = create_icon_button(
            self.icons_path, "go-back.svg", "Back to chat",
            size_type="large", config=self.config
        )
        self.back_button.clicked.connect(self._on_back_clicked)
        nav_bar.addWidget(self.back_button)
        
        # Browser back button
        self.browser_back_button = create_icon_button(
            self.icons_path, "arrow-left.svg", "Previous page",
            size_type="large", config=self.config
        )
        self.browser_back_button.clicked.connect(self._go_back)
        nav_bar.addWidget(self.browser_back_button)
        
        # Browser forward button
        self.browser_forward_button = create_icon_button(
            self.icons_path, "arrow-right.svg", "Next page",
            size_type="large", config=self.config
        )
        self.browser_forward_button.clicked.connect(self._go_forward)
        nav_bar.addWidget(self.browser_forward_button)
        
        # Reload button
        self.reload_button = create_icon_button(
            self.icons_path, "reload.svg", "Reload page",
            size_type="large", config=self.config
        )
        self.reload_button.clicked.connect(self._reload)
        nav_bar.addWidget(self.reload_button)
        
        # URL bar
        self.url_bar = QLineEdit()
        self.url_bar.setFont(get_font(FontType.UI))
        self.url_bar.setFixedHeight(self.config.get("ui", "input_height") or 48)
        self.url_bar.setPlaceholderText("URL")
        self.url_bar.returnPressed.connect(self._load_url_from_bar)
        nav_bar.addWidget(self.url_bar, stretch=1)
        
        # Open in browser button
        self.open_external_button = create_icon_button(
            self.icons_path, "browser.svg", "Open in external browser",
            size_type="large", config=self.config
        )
        self.open_external_button.clicked.connect(self._open_external)
        nav_bar.addWidget(self.open_external_button)
        
        layout.addWidget(nav_container, stretch=0)  # No stretch - fixed height at top
        
        # Create custom profile with memory limits
        self.profile = QWebEngineProfile.defaultProfile()
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )
        
        # Keep reasonable cache size
        self.profile.setHttpCacheMaximumSize(100 * 1024 * 1024)  # 100MB cache
        
        # Install ad blocker
        self.ad_blocker = AdBlocker(self.profile)
        self.profile.setUrlRequestInterceptor(self.ad_blocker)
        
        # Web view with custom page and profile
        self.web_view = QWebEngineView()
        custom_page = CustomWebEnginePage(self.profile, self.web_view)
        self.web_view.setPage(custom_page)
        
        # Set a proper user agent
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        self.profile.setHttpUserAgent(user_agent)
        
        # Configure settings - keep features enabled but stable
        settings = self.web_view.settings()
        
        # Core JavaScript features
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)
        
        # Storage
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        
        # Media playback
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        
        # Visual features
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadIconsForPage, True)
        
        # Advanced features - keep most enabled for compatibility
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        
        # Security
        settings.setAttribute(QWebEngineSettings.WebAttribute.XSSAuditingEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, False)
        
        # Disable features that cause issues
        settings.setAttribute(QWebEngineSettings.WebAttribute.PdfViewerEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript, False)
        
        # Connect signals with error handling
        self.web_view.urlChanged.connect(self._on_url_changed)
        self.web_view.loadStarted.connect(self._on_load_started)
        self.web_view.loadFinished.connect(self._on_load_finished)
        self.web_view.renderProcessTerminated.connect(self._on_render_process_terminated)
        
        # Start visible immediately at top position to prevent centering
        self.web_view.setVisible(True)
        layout.addWidget(self.web_view, stretch=1)  # Stretch=1 to take all remaining space
        
        # Initially disable navigation buttons
        self._update_navigation_buttons()
    
    def _on_back_clicked(self):
        """Handle back to chat button - stop loading first"""
        if self.web_view:
            try:
                self.web_view.stop()
            except:
                pass
        self.back_requested.emit()
    
    def _on_render_process_terminated(self, termination_status, exit_code):
        """Handle renderer process crashes gracefully"""
        status_names = {
            0: "Normal termination",
            1: "Abnormal termination", 
            2: "Crashed",
            3: "Killed"
        }
        status_text = status_names.get(termination_status, f"Unknown ({termination_status})")
        
        print(f"⚠️ WebView process terminated: {status_text}, exit code: {exit_code}")
        
        # Get current URL for debugging
        current_url = "unknown"
        if self.web_view:
            try:
                current_url = self.web_view.url().toString()
            except:
                pass
        
        print(f"   URL: {current_url}")
        
        # Show error message
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Page Crashed")
        msg.setText(f"The page crashed ({status_text}).")
        msg.setInformativeText(f"This page may be too complex or resource-intensive.\n\nURL: {current_url}\n\nTry opening it in your external browser instead.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        
        # Go back to chat
        self.back_requested.emit()
    
    def load_url(self, url: str):
        """Load a URL in the web view"""
        if not self.web_view:
            print("⚠️ WebView not initialized")
            return
        
        # Normalize URL
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        try:
            self.web_view.setUrl(QUrl(url))
            self.url_bar.setText(url)
        except Exception as e:
            print(f"Error loading URL: {e}")
            self.back_requested.emit()
    
    def _load_url_from_bar(self):
        """Load URL from the URL bar"""
        url = self.url_bar.text().strip()
        if url:
            self.load_url(url)
    
    def _go_back(self):
        """Navigate back"""
        if self.web_view and self.web_view.history().canGoBack():
            try:
                self.web_view.back()
            except Exception as e:
                print(f"Back navigation error: {e}")
    
    def _go_forward(self):
        """Navigate forward"""
        if self.web_view and self.web_view.history().canGoForward():
            try:
                self.web_view.forward()
            except Exception as e:
                print(f"Forward navigation error: {e}")
    
    def _reload(self):
        """Reload current page"""
        if self.web_view:
            try:
                self.web_view.reload()
            except Exception as e:
                print(f"Reload error: {e}")
    
    def _open_external(self):
        """Open current URL in external browser"""
        import webbrowser
        if self.web_view:
            url = self.web_view.url().toString()
            if url and url != "about:blank":
                try:
                    webbrowser.open(url)
                except Exception as e:
                    print(f"Failed to open URL in external browser: {e}")
    
    def _on_url_changed(self, url: QUrl):
        """Update URL bar when URL changes"""
        try:
            self.url_bar.setText(url.toString())
            self._update_navigation_buttons()
        except Exception as e:
            print(f"URL change error: {e}")
    
    def _on_load_started(self):
        """Handle load started - show loading icon"""
        self.is_loading = True
        try:
            from helpers.create import _render_svg_icon
            self.reload_button.setIcon(_render_svg_icon(
                self.icons_path / "loader.svg", 
                self.reload_button._icon_size
            ))
            self.reload_button.setEnabled(False)
        except Exception as e:
            print(f"Load started error: {e}")
    
    def _on_load_finished(self, success: bool):
        """Handle load finished - restore reload icon"""
        self.is_loading = False
        try:
            from helpers.create import _render_svg_icon
            self.reload_button.setIcon(_render_svg_icon(
                self.icons_path / "reload.svg", 
                self.reload_button._icon_size
            ))
            self.reload_button.setEnabled(True)
            
            # Show blocked ads count if any
            if self.ad_blocker:
                try:
                    stats = self.ad_blocker.get_stats()
                    if stats and isinstance(stats, dict) and stats.get('blocked', 0) > 0:
                        print(f"🛡️ Blocked {stats.get('blocked', 0)} ads/trackers")
                except Exception as e:
                    print(f"Ad blocker stats error: {e}")
            
            if not success:
                print(f"⚠️ Failed to load page")
                
                # Show error dialog
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle("Page Load Failed")
                msg.setText("Failed to load the page.")
                msg.setInformativeText("The page may be unavailable. Try opening it in your external browser.")
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg.exec()
            
            self._update_navigation_buttons()
        except Exception as e:
            print(f"Load finished error: {e}")
    
    def _update_navigation_buttons(self):
        """Update navigation button states"""
        try:
            if self.web_view and self.web_view.history():
                self.browser_back_button.setEnabled(self.web_view.history().canGoBack())
                self.browser_forward_button.setEnabled(self.web_view.history().canGoForward())
        except Exception as e:
            print(f"Button update error: {e}")