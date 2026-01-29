from typing import TYPE_CHECKING
from PyQt6.QtCore import QObject, QTimer

if TYPE_CHECKING:
    from .pose_detector import PoseDetector


class LedBlinker(QObject):
    """Blinks camera LED by stopping/starting the camera."""

    BLINK_OFF_MS = 200  # LED off duration (camera stopped)
    BLINK_ON_MS = 200  # LED on duration (camera running)
    BLINK_COUNT = 2
    REPEAT_INTERVAL_S = 30

    def __init__(self, pose_detector: "PoseDetector", camera_index: int, parent=None):
        super().__init__(parent)
        self._pose_detector = pose_detector
        self._camera_index = camera_index
        self._blink_step = 0
        self._blink_in_progress = False
        self._is_slouching = False

        self._repeat_timer = QTimer(self)
        self._repeat_timer.timeout.connect(self._on_repeat)

    def blink(self):
        """Start a 2-blink sequence: off-on-off-on."""
        if self._blink_in_progress:
            return  # Don't interrupt ongoing blink
        self._blink_in_progress = True
        self._blink_step = 0
        self._do_blink_step()

    def _do_blink_step(self):
        """Execute one step of the blink sequence."""
        # Steps: 0=stop, 1=start, 2=stop, 3=start (done)
        if self._blink_step >= self.BLINK_COUNT * 2:
            self._blink_in_progress = False
            return  # Sequence complete, camera is running

        if self._blink_step % 2 == 0:
            # Stop camera (LED off)
            self._pose_detector.stop()
            QTimer.singleShot(self.BLINK_OFF_MS, self._advance_step)
        else:
            # Start camera (LED on)
            self._pose_detector.start(self._camera_index)
            QTimer.singleShot(self.BLINK_ON_MS, self._advance_step)

    def _advance_step(self):
        """Move to next blink step."""
        self._blink_step += 1
        self._do_blink_step()

    def _on_repeat(self):
        """Handle 30-second repeat timer."""
        if self._is_slouching:
            self.blink()

    def on_slouching_started(self):
        """Called when slouching is first detected."""
        self._is_slouching = True
        self.blink()
        self._repeat_timer.start(self.REPEAT_INTERVAL_S * 1000)

    def on_slouching_stopped(self):
        """Called when good posture is restored."""
        self._is_slouching = False
        self._repeat_timer.stop()
        # If blink in progress, let it complete (camera ends up running)

    def set_camera_index(self, index: int):
        """Update camera index for restarts."""
        self._camera_index = index
