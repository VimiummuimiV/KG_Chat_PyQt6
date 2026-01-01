from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve


class PopupNotification(QWidget):
    def __init__(self, title: str, message: str, parent=None, duration=5000):
        super().__init__(parent)

        self.duration = duration  # milliseconds
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.BypassWindowManagerHint  # avoids stealing focus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("popup_notification")

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        # Title label
        self.title_label = QLabel(title)
        self.title_label.setObjectName("popup_title")

        # Message label
        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("popup_message")

        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)

        # Position & animate
        self._position()
        self._animate_in()

        # Fade out timer
        QTimer.singleShot(self.duration, self._animate_out)

    def _position(self):
        screen = self.screen().availableGeometry()
        width = min(int(screen.width() * 0.4), 400)
        height = self.sizeHint().height()

        x = screen.x() + (screen.width() - width) // 2
        y = screen.y() + 20  # top margin
        self.setGeometry(x, y, width, height)

    def _animate_in(self):
        start_rect = self.geometry()
        start_rect.moveTop(start_rect.top() - 20)

        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(300)
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(self.geometry())
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

        # Fade in
        self.setWindowOpacity(0)
        self.fade_in = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in.setDuration(300)
        self.fade_in.setStartValue(0)
        self.fade_in.setEndValue(1)
        self.fade_in.start()

        self.show()

    def _animate_out(self):
        # Fade out
        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(800)
        self.fade_out.setStartValue(1)
        self.fade_out.setEndValue(0)
        self.fade_out.finished.connect(self.close)
        self.fade_out.start()

    def mousePressEvent(self, event):
        self.close()
        if self.parent():
            self.parent().raise_()
            self.parent().activateWindow()
