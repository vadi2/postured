import subprocess
import sys

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtWidgets import QApplication

from .pose_detector import PoseDetector
from .overlay import Overlay
from .calibration import CalibrationWindow
from .tray import TrayIcon
from .settings import Settings
from .dbus_service import register_dbus_service


class Application(QObject):
    """Main application controller."""

    FRAME_THRESHOLD = 8
    AWAY_THRESHOLD = 15
    HYSTERESIS_FACTOR = 0.5
    DEAD_ZONE = 0.03

    def __init__(self, debug: bool = False):
        super().__init__()

        self.debug = debug
        self._last_debug_state: str | None = None
        self.settings = Settings()

        if self.debug:
            self._print_debug("Debug mode enabled")
            self._print_debug(f"Calibrated: {self.settings.is_calibrated}")
            self._print_debug(f"Good posture Y: {self.settings.good_posture_y:.4f}")
            self._print_debug(f"Bad posture Y: {self.settings.bad_posture_y:.4f}")
            self._print_debug(f"Sensitivity: {self.settings.sensitivity:.2f}")

        self.pose_detector = PoseDetector(self, debug=self.debug)
        self.overlay = Overlay(self)
        self.tray = TrayIcon(self)
        self.calibration: CalibrationWindow | None = None

        self.is_enabled = True
        self.is_calibrating = False
        self.is_slouching = False
        self.consecutive_bad_frames = 0
        self.consecutive_good_frames = 0
        self.consecutive_no_detection = 0
        self._screen_locked_this_away = False

        self._dbus_adaptor = register_dbus_service(self)

        self._connect_signals()
        self._start()

    def _connect_signals(self):
        self.pose_detector.pose_detected.connect(self._on_pose_detected)
        self.pose_detector.no_detection.connect(self._on_no_detection)
        self.pose_detector.camera_error.connect(self._on_camera_error)
        self.pose_detector.camera_recovered.connect(self._on_camera_recovered)

        self.tray.enable_toggled.connect(self._on_enable_toggled)
        self.tray.recalibrate_requested.connect(self.start_calibration)
        self.tray.sensitivity_changed.connect(self._on_sensitivity_changed)
        self.tray.camera_changed.connect(self._on_camera_changed)
        self.tray.lock_when_away_toggled.connect(self._on_lock_away_toggled)
        self.tray.quit_requested.connect(self._quit)

    def _start(self):
        cameras = PoseDetector.available_cameras()
        self.tray.update_cameras(cameras, self.settings.camera_index)

        self.pose_detector.start(self.settings.camera_index)

        if not self.settings.is_calibrated:
            self.start_calibration()
        else:
            self.tray.set_status("Monitoring")

    def _emit_dbus_status(self):
        if self._dbus_adaptor:
            self._dbus_adaptor.emit_status_changed()

    def _print_debug(self, message: str):
        """Print debug message to stderr."""
        print(f"[postured] {message}", file=sys.stderr, flush=True)

    def start_calibration(self):
        if self.is_calibrating:
            return

        self.is_calibrating = True
        self.is_enabled = False
        self.overlay.set_target_opacity(0)
        self.tray.set_status("Calibrating...")

        self.calibration = CalibrationWindow()
        self.calibration.calibration_complete.connect(self._on_calibration_complete)
        self.calibration.calibration_cancelled.connect(self._on_calibration_cancelled)

        # Forward pose data to calibration window
        self.pose_detector.pose_detected.connect(self.calibration.update_nose_y)

        self.calibration.start()

    @pyqtSlot(float, float, float)
    def _on_calibration_complete(self, min_y: float, max_y: float, avg_y: float):
        # In MediaPipe, higher Y = lower in frame = slouching
        # So min_y = good posture (looking up), max_y = bad posture (looking down)
        self.settings.good_posture_y = min_y
        self.settings.bad_posture_y = max_y
        self.settings.is_calibrated = True
        self.settings.sync()

        if self.debug:
            self._print_debug(f"Calibration complete: good_y={min_y:.4f} bad_y={max_y:.4f} range={max_y - min_y:.4f}")

        self._finish_calibration()
        self.tray.set_status("Calibrated")

    @pyqtSlot()
    def _on_calibration_cancelled(self):
        self.settings.is_calibrated = True
        self._finish_calibration()
        self.tray.set_status("Using defaults")

    def _finish_calibration(self):
        self.is_calibrating = False
        self.is_enabled = True
        self.consecutive_bad_frames = 0
        self.consecutive_good_frames = 0

        if self.calibration:
            self.pose_detector.pose_detected.disconnect(self.calibration.update_nose_y)
            self.calibration.deleteLater()
            self.calibration = None

        self._emit_dbus_status()

    @pyqtSlot(float)
    def _on_pose_detected(self, nose_y: float):
        if self.is_calibrating or not self.is_enabled:
            return

        self.consecutive_no_detection = 0
        self._screen_locked_this_away = False
        self._evaluate_posture(nose_y)

    @pyqtSlot()
    def _on_no_detection(self):
        if self.is_calibrating or not self.is_enabled:
            return

        self.consecutive_no_detection += 1
        self.consecutive_bad_frames = 0
        self.consecutive_good_frames = 0

        if self.consecutive_no_detection >= self.AWAY_THRESHOLD:
            if self.debug and self.consecutive_no_detection == self.AWAY_THRESHOLD:
                self._print_debug(f"AWAY      | no_detect_frames={self.consecutive_no_detection}")

            if self.settings.lock_when_away and not self._screen_locked_this_away:
                if self.debug:
                    self._print_debug("Locking screen (away)")
                self._lock_screen()
                self._screen_locked_this_away = True

    def _evaluate_posture(self, current_y: float):
        posture_range = abs(self.settings.bad_posture_y - self.settings.good_posture_y)
        if posture_range < 0.01:
            posture_range = 0.2

        # Slouching = nose Y is ABOVE bad_posture_y (lower in frame = higher Y value)
        slouch_amount = current_y - self.settings.bad_posture_y

        base_threshold = self.DEAD_ZONE * posture_range * self.settings.sensitivity

        # Hysteresis
        enter_threshold = base_threshold
        exit_threshold = base_threshold * self.HYSTERESIS_FACTOR

        threshold = exit_threshold if self.is_slouching else enter_threshold
        is_bad_posture = slouch_amount > threshold

        if is_bad_posture:
            self.consecutive_bad_frames += 1
            self.consecutive_good_frames = 0

            if self.consecutive_bad_frames >= self.FRAME_THRESHOLD:
                was_slouching = self.is_slouching
                self.is_slouching = True

                # Calculate blur intensity
                severity = (slouch_amount - enter_threshold) / posture_range
                severity = max(0.0, min(1.0, severity))
                eased_severity = severity * severity  # Quadratic ease-in

                opacity = 0.03 + eased_severity * 0.97 * self.settings.sensitivity
                self.overlay.set_target_opacity(opacity)

                self.tray.set_status("Slouching")
                self.tray.set_posture_state('slouching')

                if self.debug:
                    self._print_debug(
                        f"SLOUCHING | nose_y={current_y:.4f} slouch={slouch_amount:+.4f} "
                        f"thresh={threshold:.4f} severity={severity:.2f} opacity={opacity:.2f} "
                        f"bad_frames={self.consecutive_bad_frames}"
                    )

                if not was_slouching:
                    self._emit_dbus_status()
        else:
            self.consecutive_good_frames += 1
            self.consecutive_bad_frames = 0

            self.overlay.set_target_opacity(0)

            if self.consecutive_good_frames >= self.FRAME_THRESHOLD:
                was_slouching = self.is_slouching
                self.is_slouching = False
                self.tray.set_status("Good posture")
                self.tray.set_posture_state('good')

                if self.debug and was_slouching:
                    self._print_debug(
                        f"GOOD      | nose_y={current_y:.4f} slouch={slouch_amount:+.4f} "
                        f"thresh={threshold:.4f} good_frames={self.consecutive_good_frames}"
                    )

                if was_slouching:
                    self._emit_dbus_status()

        # Debug: print continuous tracking info (state changes)
        if self.debug:
            current_state = "slouching" if self.is_slouching else "good"
            if current_state != self._last_debug_state:
                self._last_debug_state = current_state
                self._print_debug(f"State changed to: {current_state.upper()}")

    @pyqtSlot(bool)
    def _on_enable_toggled(self, enabled: bool):
        self.is_enabled = enabled
        self.tray.set_enabled(enabled)
        if self.debug:
            self._print_debug(f"Monitoring {'enabled' if enabled else 'disabled'}")
        if not enabled:
            self.overlay.set_target_opacity(0)
            self.tray.set_status("Disabled")
            self.pose_detector.stop()
        else:
            self.tray.set_status("Monitoring")
            self.pose_detector.start(self.settings.camera_index)
        self._emit_dbus_status()

    @pyqtSlot(float)
    def _on_sensitivity_changed(self, value: float):
        self.settings.sensitivity = value
        self.settings.sync()
        if self.debug:
            self._print_debug(f"Sensitivity changed to: {value:.2f}")

    @pyqtSlot(int)
    def _on_camera_changed(self, index: int):
        if index == self.settings.camera_index:
            return
        self.settings.camera_index = index
        self.settings.sync()
        self.pose_detector.stop()
        self.pose_detector.start(index)
        self.start_calibration()

    @pyqtSlot(bool)
    def _on_lock_away_toggled(self, enabled: bool):
        self.settings.lock_when_away = enabled
        self.settings.sync()
        if not enabled:
            self._screen_locked_this_away = False

    def _lock_screen(self):
        """Lock the screen using loginctl (Freedesktop standard)."""
        try:
            subprocess.run(['loginctl', 'lock-session'], check=False)
        except FileNotFoundError:
            pass  # loginctl not available on this system

    @pyqtSlot(str)
    def _on_camera_error(self, message: str):
        if self.debug:
            self._print_debug(f"Camera error: {message}")
        self.tray.set_status(f"Camera error: {message}")

    @pyqtSlot()
    def _on_camera_recovered(self):
        if self.debug:
            self._print_debug("Camera recovered")
        self.tray.set_status("Monitoring")

    def shutdown(self):
        """Clean up resources for graceful shutdown."""
        self.pose_detector.stop()
        self.overlay.cleanup()

    def _quit(self):
        self.shutdown()
        QApplication.instance().quit()
