import math
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QScreen

from .settings import get_monitor_id


class CalibrationWindow(QWidget):
    """Full-screen calibration overlay with pulsing target rings."""

    # Emitted after each monitor's calibration completes
    calibration_complete = pyqtSignal(
        str, float, float, float
    )  # monitor_id, min_y, max_y, avg_y
    # Emitted when all monitors are calibrated
    all_calibrations_complete = pyqtSignal()
    calibration_cancelled = pyqtSignal()

    CORNERS = ["TOP-LEFT", "TOP-RIGHT", "BOTTOM-RIGHT", "BOTTOM-LEFT"]
    MARGIN = 120

    def __init__(self, screens_to_calibrate: list[QScreen] | None = None):
        super().__init__()

        # Get screens to calibrate (default to all screens)
        all_screens = QApplication.instance().screens()
        if screens_to_calibrate is None:
            self.screens = all_screens
        else:
            self.screens = screens_to_calibrate

        self.current_screen_index = 0
        self.current_step = 0
        self.captured_values: list[float] = []
        self.current_nose_y = 0.5
        self.pulse_phase = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Position on first screen
        if self.screens:
            self._move_to_screen(self.screens[0])

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._animate)

    def _move_to_screen(self, screen: QScreen) -> None:
        """Move calibration window to specified screen."""
        self.setGeometry(screen.geometry())

    @property
    def _current_screen(self) -> QScreen | None:
        """Get the currently calibrating screen."""
        if self.current_screen_index < len(self.screens):
            return self.screens[self.current_screen_index]
        return None

    @property
    def _current_monitor_id(self) -> str | None:
        """Get the monitor ID of the current screen."""
        screen = self._current_screen
        if screen:
            return get_monitor_id(screen)
        return None

    def start(self):
        self.current_screen_index = 0
        self.current_step = 0
        self.captured_values = []
        if self.screens:
            self._move_to_screen(self.screens[0])
        self.animation_timer.start(16)  # ~60 FPS
        self.showFullScreen()
        self.activateWindow()
        self.setFocus()

    def update_nose_y(self, y: float, x: float = 0.0):
        """Called by pose detector during calibration.

        Args:
            y: Nose Y position (used for calibration)
            x: Nose X position (ignored during calibration)
        """
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

        # Monitor indicator (if multiple monitors)
        if len(self.screens) > 1:
            painter.setFont(QFont("Sans", 16))
            screen = self._current_screen
            monitor_name = screen.name() if screen else "Unknown"
            monitor_text = f"Monitor {self.current_screen_index + 1} of {len(self.screens)}: {monitor_name}"
            painter.drawText(
                self.rect().adjusted(0, 20, 0, 0),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                monitor_text,
            )

        # Step indicator
        painter.setFont(QFont("Sans", 20))
        step_text = f"Step {self.current_step + 1} of {len(self.CORNERS)}"
        top_offset = 60 if len(self.screens) > 1 else 50
        painter.drawText(
            self.rect().adjusted(0, top_offset, 0, 0),
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
            self._complete_current_screen()

    def _complete_current_screen(self):
        """Complete calibration for current screen and move to next or finish."""
        min_y = min(self.captured_values)
        max_y = max(self.captured_values)
        avg_y = sum(self.captured_values) / len(self.captured_values)

        monitor_id = self._current_monitor_id
        if monitor_id:
            self.calibration_complete.emit(monitor_id, min_y, max_y, avg_y)

        # Move to next screen
        self.current_screen_index += 1
        if self.current_screen_index < len(self.screens):
            # Reset for next screen
            self.current_step = 0
            self.captured_values = []
            self._move_to_screen(self.screens[self.current_screen_index])
            self.showFullScreen()
            self.activateWindow()
            self.setFocus()
        else:
            # All screens calibrated
            self._finish_all()

    def _finish_all(self):
        """All monitors have been calibrated."""
        self.animation_timer.stop()
        self.hide()
        self.all_calibrations_complete.emit()

    def _cancel(self):
        self.animation_timer.stop()
        self.hide()
        self.calibration_cancelled.emit()
