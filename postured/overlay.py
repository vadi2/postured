from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QObject
from PyQt6.QtGui import QPainter, QColor


class OverlayWindow(QWidget):
    """Single full-screen overlay window."""

    MAX_OPACITY = 0.85

    def __init__(self, screen):
        super().__init__()
        self.opacity_level = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        geometry = screen.geometry()
        self.setGeometry(geometry)

    def set_opacity(self, level: float):
        """Set overlay darkness (0.0 = invisible, 1.0 = fully dark)."""
        self.opacity_level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event):
        if self.opacity_level <= 0:
            return
        painter = QPainter(self)
        color = QColor(0, 0, 0, int(self.opacity_level * 255 * self.MAX_OPACITY))
        painter.fillRect(self.rect(), color)


class Overlay(QObject):
    """Manages overlay windows across all monitors."""

    EASE_IN_RATE = 0.015    # Opacity increase per tick (~1/64)
    EASE_OUT_RATE = 0.047   # Opacity decrease per tick (~3/64)
    TRANSITION_INTERVAL_MS = 33  # ~30 FPS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.windows: list[OverlayWindow] = []
        self.current_opacity = 0.0
        self.target_opacity = 0.0

        self.transition_timer = QTimer(self)
        self.transition_timer.timeout.connect(self._update_opacity)
        self.transition_timer.start(self.TRANSITION_INTERVAL_MS)

        self._create_windows()

    def _create_windows(self):
        app = QApplication.instance()
        for screen in app.screens():
            window = OverlayWindow(screen)
            window.show()
            self.windows.append(window)

    def set_target_opacity(self, opacity: float):
        """Set target opacity (0.0 to 1.0). Transition happens smoothly."""
        self.target_opacity = max(0.0, min(1.0, opacity))

    def _update_opacity(self):
        if abs(self.current_opacity - self.target_opacity) < 0.001:
            return

        if self.current_opacity < self.target_opacity:
            self.current_opacity = min(
                self.current_opacity + self.EASE_IN_RATE,
                self.target_opacity
            )
        else:
            self.current_opacity = max(
                self.current_opacity - self.EASE_OUT_RATE,
                self.target_opacity
            )

        for window in self.windows:
            window.set_opacity(self.current_opacity)

    def cleanup(self):
        self.transition_timer.stop()
        for window in self.windows:
            window.close()
