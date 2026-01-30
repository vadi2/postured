import subprocess
import sys

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtGui import QScreen
from PyQt6.QtWidgets import QApplication

from .pose_detector import PoseDetector
from .overlay import create_overlay, needs_gnome_extension
from .calibration import CalibrationWindow
from .tray import TrayIcon
from .settings import Settings, MonitorCalibration, get_monitor_id
from .dbus_service import register_dbus_service
from .screen_lock import ScreenLockMonitor
from .led_blinker import LedBlinker


class MonitorDetector:
    """Determines which monitor the user is looking at based on nose X position."""

    HYSTERESIS_FRAMES = 5  # Frames before switching monitors

    def __init__(self):
        self._current_monitor_id: str | None = None
        self._pending_monitor_id: str | None = None
        self._pending_frames: int = 0

    def update(self, nose_x: float, screens: list[QScreen]) -> str | None:
        """Update monitor detection with new nose X position.

        Args:
            nose_x: Nose X position from camera (0.0=left, 1.0=right)
            screens: List of available screens

        Returns:
            Current monitor ID, or None if no screens available
        """
        if not screens:
            return None

        detected = self._detect_monitor(nose_x, screens)

        # Apply hysteresis
        if detected != self._current_monitor_id:
            if detected == self._pending_monitor_id:
                self._pending_frames += 1
                if self._pending_frames >= self.HYSTERESIS_FRAMES:
                    self._current_monitor_id = detected
                    self._pending_monitor_id = None
                    self._pending_frames = 0
            else:
                self._pending_monitor_id = detected
                self._pending_frames = 1
        else:
            self._pending_monitor_id = None
            self._pending_frames = 0

        return self._current_monitor_id

    def _detect_monitor(self, nose_x: float, screens: list[QScreen]) -> str:
        """Map nose X position to monitor ID.

        Camera is mirrored: left in camera = right on screen.
        """
        # Mirror the X coordinate
        mirrored_x = 1.0 - nose_x

        # Sort screens by X position (left to right)
        sorted_screens = sorted(screens, key=lambda s: s.geometry().x())

        # Calculate total desktop width
        total_width = sum(s.geometry().width() for s in sorted_screens)
        if total_width == 0:
            return get_monitor_id(sorted_screens[0])

        # Map mirrored_x to desktop coordinate
        desktop_x = mirrored_x * total_width

        # Find containing screen
        cumulative_x = 0
        for screen in sorted_screens:
            screen_width = screen.geometry().width()
            if desktop_x < cumulative_x + screen_width:
                return get_monitor_id(screen)
            cumulative_x += screen_width

        # Fallback to last screen
        return get_monitor_id(sorted_screens[-1])

    @property
    def current_monitor_id(self) -> str | None:
        """Currently detected monitor ID."""
        return self._current_monitor_id

    def reset(self) -> None:
        """Reset detection state."""
        self._current_monitor_id = None
        self._pending_monitor_id = None
        self._pending_frames = 0


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

        # Multi-monitor support
        self.monitor_detector = MonitorDetector()
        self.current_monitor_id: str | None = None
        self.monitor_calibrations: dict[str, MonitorCalibration] = {}
        self._load_monitor_calibrations()

        if self.debug:
            self._print_debug("Debug mode enabled")
            self._print_debug(f"Legacy calibrated: {self.settings.is_calibrated}")
            self._print_debug(f"Monitor calibrations: {len(self.monitor_calibrations)}")
            self._print_debug(f"Sensitivity: {self.settings.sensitivity:.2f}")

        self.pose_detector = PoseDetector(self, debug=self.debug)
        self.led_blinker = LedBlinker(
            self.pose_detector, self.settings.camera_index, self
        )
        self.overlay = create_overlay(self)
        self.tray = TrayIcon(self)
        self.tray.show_gnome_extension_prompt(needs_gnome_extension())
        self.calibration: CalibrationWindow | None = None
        self._calibrating_screens: list[QScreen] | None = None

        self.is_enabled = True
        self.is_calibrating = False
        self.is_slouching = False
        self.consecutive_bad_frames = 0
        self.consecutive_good_frames = 0
        self.consecutive_no_detection = 0
        self._screen_locked_this_away = False

        self._dbus_adaptor = register_dbus_service(self)

        # Screen lock detection for auto-pause
        self._screen_lock_monitor = ScreenLockMonitor(self)
        self._was_enabled_before_lock = False

        self._connect_signals()
        self._start()

    def _load_monitor_calibrations(self):
        """Load all monitor calibrations from settings."""
        self.monitor_calibrations.clear()
        for calibration in self.settings.get_all_monitor_calibrations():
            self.monitor_calibrations[calibration.monitor_id] = calibration

    def _get_calibrated_monitor_ids(self) -> set[str]:
        """Get set of calibrated monitor IDs."""
        return set(self.monitor_calibrations.keys())

    def _update_tray_calibrations(self):
        """Update tray menu with current calibration status."""
        self.tray.update_monitor_calibrations(self._get_calibrated_monitor_ids())

    def _connect_signals(self):
        self.pose_detector.pose_detected.connect(self._on_pose_detected)
        self.pose_detector.no_detection.connect(self._on_no_detection)
        self.pose_detector.camera_error.connect(self._on_camera_error)
        self.pose_detector.camera_recovered.connect(self._on_camera_recovered)

        self.tray.enable_toggled.connect(self._on_enable_toggled)
        self.tray.recalibrate_requested.connect(self.start_calibration)
        self.tray.recalibrate_monitor_requested.connect(self._on_recalibrate_monitor)
        self.tray.sensitivity_changed.connect(self._on_sensitivity_changed)
        self.tray.camera_changed.connect(self._on_camera_changed)
        self.tray.lock_when_away_toggled.connect(self._on_lock_away_toggled)
        self.tray.notification_mode_changed.connect(self._on_notification_mode_changed)
        self.tray.quit_requested.connect(self._quit)

        # Screen hotplug handling
        app = QApplication.instance()
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._on_screen_removed)

        # Screen lock auto-pause
        self._screen_lock_monitor.screen_locked.connect(self._on_screen_lock_changed)

    def _start(self):
        cameras = PoseDetector.available_cameras()
        self.tray.update_cameras(cameras, self.settings.camera_index)

        # Migrate legacy calibration if needed
        screens = QApplication.instance().screens()
        if screens:
            primary_id = get_monitor_id(screens[0])
            if self.settings.migrate_legacy_calibration(primary_id):
                self._load_monitor_calibrations()
                if self.debug:
                    self._print_debug(f"Migrated legacy calibration to {primary_id}")

        self._update_tray_calibrations()
        self.tray.set_sensitivity(self.settings.sensitivity)
        self.tray.set_lock_when_away(self.settings.lock_when_away)
        self.tray.set_notification_mode(self.settings.notification_mode)
        self.pose_detector.start(self.settings.camera_index)

        if not self.settings.has_any_calibration():
            self.start_calibration()
        else:
            self.tray.set_status("Monitoring")

    def _emit_dbus_status(self):
        if self._dbus_adaptor:
            self._dbus_adaptor.emit_status_changed()

    def _print_debug(self, message: str):
        """Print debug message to stderr."""
        print(f"[postured] {message}", file=sys.stderr, flush=True)

    def start_calibration(self, screens: list[QScreen] | None = None):
        """Start calibration for specified screens or all screens.

        Args:
            screens: List of screens to calibrate, or None for all screens.
        """
        if self.is_calibrating:
            return

        self.is_calibrating = True
        self.is_enabled = False
        self.overlay.set_target_opacity(0)
        self.tray.set_status("Calibrating...")

        # Determine which screens to calibrate
        if screens is None:
            screens = QApplication.instance().screens()
        self._calibrating_screens = screens

        self.calibration = CalibrationWindow(screens_to_calibrate=screens)
        self.calibration.calibration_complete.connect(
            self._on_monitor_calibration_complete
        )
        self.calibration.all_calibrations_complete.connect(
            self._on_all_calibrations_complete
        )
        self.calibration.calibration_cancelled.connect(self._on_calibration_cancelled)

        # Forward pose data to calibration window
        self.pose_detector.pose_detected.connect(self.calibration.update_nose_y)

        self.calibration.start()

    @pyqtSlot(str)
    def _on_recalibrate_monitor(self, monitor_id: str):
        """Recalibrate a specific monitor."""
        screens = QApplication.instance().screens()
        for screen in screens:
            if get_monitor_id(screen) == monitor_id:
                self.start_calibration([screen])
                return

    @pyqtSlot(str, float, float, float)
    def _on_monitor_calibration_complete(
        self, monitor_id: str, min_y: float, max_y: float, avg_y: float
    ):
        """Handle calibration completion for a single monitor."""
        # In MediaPipe, higher Y = lower in frame = slouching
        # So min_y = good posture (looking up), max_y = bad posture (looking down)
        calibration = MonitorCalibration(
            monitor_id=monitor_id,
            good_posture_y=min_y,
            bad_posture_y=max_y,
            is_calibrated=True,
        )
        self.settings.set_monitor_calibration(calibration)
        self.monitor_calibrations[monitor_id] = calibration
        self.settings.sync()

        if self.debug:
            self._print_debug(
                f"Monitor {monitor_id} calibrated: good_y={min_y:.4f} bad_y={max_y:.4f} range={max_y - min_y:.4f}"
            )

        self._update_tray_calibrations()

    @pyqtSlot()
    def _on_all_calibrations_complete(self):
        """Handle completion of all monitor calibrations."""
        self._finish_calibration()
        self.tray.set_status("Calibrated")

    @pyqtSlot()
    def _on_calibration_cancelled(self):
        # Mark as calibrated so we don't prompt again (user can use defaults)
        self.settings.is_calibrated = True
        self._finish_calibration()
        self.tray.set_status("Using defaults")

    def _finish_calibration(self):
        self.is_calibrating = False
        self.is_enabled = True
        self.consecutive_bad_frames = 0
        self.consecutive_good_frames = 0
        self._calibrating_screens = None

        if self.calibration:
            self.pose_detector.pose_detected.disconnect(self.calibration.update_nose_y)
            self.calibration.deleteLater()
            self.calibration = None

        self._update_tray_calibrations()
        self._emit_dbus_status()

    @pyqtSlot(float, float)
    def _on_pose_detected(self, nose_y: float, nose_x: float):
        if self.is_calibrating or not self.is_enabled:
            return

        self.consecutive_no_detection = 0
        self._screen_locked_this_away = False

        # Update monitor detection
        screens = QApplication.instance().screens()
        self.current_monitor_id = self.monitor_detector.update(nose_x, screens)

        # Get calibration for current monitor
        calibration = self._get_active_calibration()
        self._evaluate_posture(nose_y, calibration)

    def _get_active_calibration(self) -> MonitorCalibration | None:
        """Get calibration for the current monitor, or None for defaults."""
        if self.current_monitor_id:
            return self.monitor_calibrations.get(self.current_monitor_id)
        return None

    @pyqtSlot()
    def _on_no_detection(self):
        if self.is_calibrating or not self.is_enabled:
            return

        self.consecutive_no_detection += 1
        self.consecutive_bad_frames = 0
        self.consecutive_good_frames = 0

        if self.consecutive_no_detection >= self.AWAY_THRESHOLD:
            if self.debug and self.consecutive_no_detection == self.AWAY_THRESHOLD:
                self._print_debug(
                    f"AWAY      | no_detect_frames={self.consecutive_no_detection}"
                )

            if self.settings.lock_when_away and not self._screen_locked_this_away:
                if self.debug:
                    self._print_debug("Locking screen (away)")
                self._lock_screen()
                self._screen_locked_this_away = True

    def _evaluate_posture(
        self, current_y: float, calibration: MonitorCalibration | None
    ):
        # Use per-monitor calibration or fall back to global defaults
        if calibration:
            good_y = calibration.good_posture_y
            bad_y = calibration.bad_posture_y
            uncalibrated_suffix = ""
        else:
            # Fallback to global defaults
            good_y = self.settings.DEFAULTS["good_posture_y"]
            bad_y = self.settings.DEFAULTS["bad_posture_y"]
            uncalibrated_suffix = " (uncalibrated)"

        posture_range = abs(bad_y - good_y)
        if posture_range < 0.01:
            posture_range = 0.2

        # Slouching = nose Y is ABOVE bad_posture_y (lower in frame = higher Y value)
        slouch_amount = current_y - bad_y

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

                if self.settings.notification_mode == "dim_screen":
                    # Calculate blur intensity
                    severity = (slouch_amount - enter_threshold) / posture_range
                    severity = max(0.0, min(1.0, severity))
                    eased_severity = severity * severity  # Quadratic ease-in

                    opacity = 0.03 + eased_severity * 0.97 * self.settings.sensitivity
                    self.overlay.set_target_opacity(opacity)

                self.tray.set_status(f"Slouching{uncalibrated_suffix}")
                self.tray.set_posture_state("slouching")

                if not was_slouching:
                    self._emit_dbus_status()
                    if self.settings.notification_mode == "led_blink":
                        self.led_blinker.on_slouching_started()
        else:
            self.consecutive_good_frames += 1
            self.consecutive_bad_frames = 0

            if self.settings.notification_mode == "dim_screen":
                self.overlay.set_target_opacity(0)

            if self.consecutive_good_frames >= self.FRAME_THRESHOLD:
                was_slouching = self.is_slouching
                self.is_slouching = False
                self.tray.set_status(f"Good posture{uncalibrated_suffix}")
                self.tray.set_posture_state("good")

                if was_slouching:
                    self._emit_dbus_status()
                    if self.settings.notification_mode == "led_blink":
                        self.led_blinker.on_slouching_stopped()

        # Debug: only print state transitions
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
        self.led_blinker.set_camera_index(index)
        self.pose_detector.stop()
        self.pose_detector.start(index)
        self.start_calibration()

    @pyqtSlot(bool)
    def _on_lock_away_toggled(self, enabled: bool):
        self.settings.lock_when_away = enabled
        self.settings.sync()
        if not enabled:
            self._screen_locked_this_away = False

    @pyqtSlot(str)
    def _on_notification_mode_changed(self, mode: str):
        self.settings.notification_mode = mode
        self.settings.sync()
        # Clear overlay when switching to LED blink mode
        if mode == "led_blink":
            self.overlay.set_target_opacity(0)

    @pyqtSlot(bool)
    def _on_screen_lock_changed(self, is_locked: bool):
        """Handle screen lock/unlock for auto-pause."""
        if is_locked:
            if self.is_enabled and not self.is_calibrating:
                self._was_enabled_before_lock = True
                if self.debug:
                    self._print_debug("Screen locked - pausing monitoring")
                self.tray.enable_toggled.emit(False)
        else:
            if self._was_enabled_before_lock:
                self._was_enabled_before_lock = False
                if self.debug:
                    self._print_debug("Screen unlocked - resuming monitoring")
                self.tray.enable_toggled.emit(True)

    def _lock_screen(self):
        """Lock the screen using loginctl (Freedesktop standard)."""
        try:
            subprocess.run(["loginctl", "lock-session"], check=False)
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

    @pyqtSlot(QScreen)
    def _on_screen_added(self, screen: QScreen):
        """Handle new screen being connected."""
        monitor_id = get_monitor_id(screen)
        if self.debug:
            self._print_debug(f"Screen added: {monitor_id}")

        # Update overlay to include new screen
        self.overlay.cleanup()
        self.overlay = create_overlay(self)

        # Update tray menu
        self._update_tray_calibrations()

    @pyqtSlot(QScreen)
    def _on_screen_removed(self, screen: QScreen):
        """Handle screen being disconnected."""
        monitor_id = get_monitor_id(screen)
        if self.debug:
            self._print_debug(f"Screen removed: {monitor_id}")

        # Reset monitor detector if current monitor was removed
        if self.current_monitor_id == monitor_id:
            self.monitor_detector.reset()
            self.current_monitor_id = None

        # Update overlay
        self.overlay.cleanup()
        self.overlay = create_overlay(self)

        # Update tray menu
        self._update_tray_calibrations()

    def shutdown(self):
        """Clean up resources for graceful shutdown."""
        self.pose_detector.close()
        self.overlay.cleanup()

    def _quit(self):
        self.shutdown()
        QApplication.instance().quit()
