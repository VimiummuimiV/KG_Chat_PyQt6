from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
)


class PopupNotification(QWidget):
    def __init__(self, title: str, message: str, parent=None, duration: int = 15000):
        super().__init__(parent)

        self.duration = duration  # milliseconds

        # Window behavior: frameless, always on top, no focus stealing
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.BypassWindowManagerHint
        )

        # IMPORTANT:
        # Do NOT use WA_TranslucentBackground, otherwise QSS background is ignored
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("popup_notification")

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        # Title
        self.title_label = QLabel(title)
        self.title_label.setObjectName("popup_title")

        # Message
        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("popup_message")

        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)

        # Start invisible (for fade-in)
        self.setWindowOpacity(0.0)
        self.show()

        # Delay positioning & animation until styles/layout are resolved
        QTimer.singleShot(0, self._position)
        QTimer.singleShot(0, self._animate_in)
        QTimer.singleShot(self.duration, self._animate_out)

    def _position(self):
        screen = self.screen().availableGeometry()

        width = min(int(screen.width() * 0.4), 400)
        height = self.sizeHint().height()

        x = screen.x() + (screen.width() - width) // 2
        y = screen.y() + 20  # top margin

        self.setGeometry(x, y, width, height)

    def _animate_in(self):
        end_rect = self.geometry()
        start_rect = end_rect.adjusted(0, -20, 0, -20)

        self.slide_anim = QPropertyAnimation(self, b"geometry")
        self.slide_anim.setDuration(300)
        self.slide_anim.setStartValue(start_rect)
        self.slide_anim.setEndValue(end_rect)
        self.slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.slide_anim.start()

        self.fade_in = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in.setDuration(300)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.start()

    def _animate_out(self):
        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(800)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.finished.connect(self.close)
        self.fade_out.start()

    def mousePressEvent(self, event):
        self.close()
        if self.parent():
            self.parent().raise_()
            self.parent().activateWindow()
