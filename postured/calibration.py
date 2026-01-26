import math
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush


class CalibrationWindow(QWidget):
    """Full-screen calibration overlay with pulsing target rings."""

    calibration_complete = pyqtSignal(float, float, float)  # min_y, max_y, avg_y
    calibration_cancelled = pyqtSignal()

    CORNERS = ["TOP-LEFT", "TOP-RIGHT", "BOTTOM-RIGHT", "BOTTOM-LEFT"]
    MARGIN = 120

    def __init__(self, screen_index: int = 0):
        super().__init__()
        self.screen_index = screen_index
        self.current_step = 0
        self.captured_values: list[float] = []
        self.current_nose_y = 0.5
        self.pulse_phase = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        screens = QApplication.instance().screens()
        if screen_index < len(screens):
            screen = screens[screen_index]
            self.setGeometry(screen.geometry())

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._animate)

    def start(self):
        self.current_step = 0
        self.captured_values = []
        self.animation_timer.start(16)  # ~60 FPS
        self.showFullScreen()
        self.activateWindow()
        self.setFocus()

    def update_nose_y(self, y: float):
        """Called by pose detector during calibration."""
        self.current_nose_y = y

    def _get_corner_position(self, corner: str) -> QPointF:
        w, h = self.width(), self.height()
        m = self.MARGIN
        positions = {
            "TOP-LEFT": QPointF(m, m),
            "TOP-RIGHT": QPointF(w - m, m),
            "BOTTOM-RIGHT": QPointF(w - m, h - m),
            "BOTTOM-LEFT": QPointF(m, h - m),
        }
        return positions[corner]

    def _animate(self):
        self.pulse_phase += 0.08
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 217))

        if self.current_step < len(self.CORNERS):
            corner = self.CORNERS[self.current_step]
            center = self._get_corner_position(corner)
            self._draw_pulsing_ring(painter, center)

        self._draw_instructions(painter)

    def _draw_pulsing_ring(self, painter: QPainter, center: QPointF):
        base_radius = 50
        pulse_amount = 15
        radius = base_radius + math.sin(self.pulse_phase) * pulse_amount

        # Outer glow
        glow_alpha = int((0.3 + 0.2 * math.sin(self.pulse_phase)) * 255)
        painter.setBrush(QBrush(QColor(0, 255, 255, glow_alpha)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, radius + 25, radius + 25)

        # Main ring
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 255, 255, 230), 5))
        painter.drawEllipse(center, radius, radius)

        # Center dot
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, 10, 10)

    def _draw_instructions(self, painter: QPainter):
        painter.setPen(QColor(255, 255, 255))

        # Step indicator
        painter.setFont(QFont("Sans", 20))
        step_text = f"Step {self.current_step + 1} of {len(self.CORNERS)}"
        painter.drawText(
            self.rect().adjusted(0, 50, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            step_text,
        )

        # Main instruction
        painter.setFont(QFont("Sans", 32, QFont.Weight.DemiBold))
        if self.current_step < len(self.CORNERS):
            instruction = f"Look at the {self.CORNERS[self.current_step]} corner"
        else:
            instruction = "Calibration complete!"
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, instruction)

        # Hint
        painter.setFont(QFont("Sans", 18))
        painter.setPen(QColor(0, 255, 255))
        hint_rect = self.rect().adjusted(0, 0, 0, -self.height() // 2 + 50)
        painter.drawText(
            hint_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            "Press Space when ready  |  Escape to skip",
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._capture_position()
        elif event.key() == Qt.Key.Key_Escape:
            self._cancel()

    def _capture_position(self):
        self.captured_values.append(self.current_nose_y)
        self.current_step += 1

        if self.current_step >= len(self.CORNERS):
            self._complete()

    def _complete(self):
        self.animation_timer.stop()
        self.hide()

        min_y = min(self.captured_values)
        max_y = max(self.captured_values)
        avg_y = sum(self.captured_values) / len(self.captured_values)

        self.calibration_complete.emit(min_y, max_y, avg_y)

    def _cancel(self):
        self.animation_timer.stop()
        self.hide()
        self.calibration_cancelled.emit()
