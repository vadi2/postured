import subprocess
import sys

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtGui import QScreen
from PyQt6.QtWidgets import QApplication

from .calibration import CalibrationWindow
from .dbus_service import register_dbus_service
from .led_blinker import LedBlinker
from .overlay import create_overlay, needs_gnome_extension
from .pose_detector import PoseDetector
from .screen_lock import ScreenLockMonitor
from .settings import MonitorCalibration, Settings, get_monitor_id
from .tray import TrayIcon


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

    FRAME_THRESHOLD = 4
    AWAY_THRESHOLD = 15
    HYSTERESIS_FACTOR = 0.5
    DEAD_ZONE = 0.03
    FORWARD_THRESHOLD_BASE = 0.07

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
        self.preview_window = None

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
        self.tray.camera_changed.connect(self._on_camera_changed)
        self.tray.lock_when_away_toggled.connect(self._on_lock_away_toggled)
        self.tray.notification_mode_changed.connect(self._on_notification_mode_changed)
        self.tray.profile_changed.connect(self._on_profile_changed)
        self.tray.preview_requested.connect(self.show_preview_window)
        self.tray.quit_requested.connect(self._quit)

        # Screen hotplug handling
        app = QApplication.instance()
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._on_screen_removed)

        # Screen lock auto-pause
        self._screen_lock_monitor.screen_locked.connect(self._on_screen_lock_changed)

    def _start(self):
        cameras = PoseDetector.available_cameras()
        available_indices = [idx for idx, _ in cameras]
        active_camera = self.settings.camera_index

        # If saved camera_index is no longer valid, fallback to first available camera
        if cameras and active_camera not in available_indices:
            active_camera = available_indices[0]
            self.settings.camera_index = active_camera
            self.settings.sync()
            self.led_blinker.set_camera_index(active_camera)
            if self.debug:
                self._print_debug(
                    f"Saved camera index was unavailable, fell back to camera {active_camera}"
                )

        self.tray.update_cameras(cameras, active_camera)

        # Migrate legacy calibration if needed
        screens = QApplication.instance().screens()
        if screens:
            primary_id = get_monitor_id(screens[0])
            if self.settings.migrate_legacy_calibration(primary_id):
                self._load_monitor_calibrations()
                if self.debug:
                    self._print_debug(f"Migrated legacy calibration to {primary_id}")

        self._update_tray_calibrations()
        self.tray.set_profile(self.settings.current_profile)
        self.tray.set_lock_when_away(self.settings.lock_when_away)
        self.tray.set_notification_mode(self.settings.notification_mode)
        self.pose_detector.set_view_mode(self.settings.camera_view_mode)
        self.pose_detector.start(active_camera)

        profile_title = self.settings.current_profile.capitalize()
        if not self.settings.has_any_calibration():
            self.start_calibration()
        else:
            self.tray.set_status(f"Monitoring ({profile_title})")

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

    @pyqtSlot(str, float, float, float, float, float, float, float, float)
    def _on_monitor_calibration_complete(
        self,
        monitor_id: str,
        min_y: float,
        max_y: float,
        avg_y: float,
        good_forward: float = 0.55,
        good_scale: float = 0.40,
        good_neck: float = 0.32,
        good_side: float = 0.0,
        good_cva: float = 65.0,
    ):
        """Handle calibration completion for a single monitor."""
        # In MediaPipe, higher Y = lower in frame = slouching
        # So min_y = good posture (looking up), max_y = bad posture (looking down)
        calibration = MonitorCalibration(
            monitor_id=monitor_id,
            good_posture_y=min_y,
            bad_posture_y=max_y,
            is_calibrated=True,
            good_forward_offset=good_forward,
            good_head_scale=good_scale,
            good_neck_ratio=good_neck,
            good_side_forward=good_side,
            good_cva=good_cva,
        )
        self.settings.set_monitor_calibration(calibration)
        self.monitor_calibrations[monitor_id] = calibration
        self.settings.sync()

        if self.debug:
            self._print_debug(
                f"Monitor {monitor_id} calibrated: good_y={min_y:.4f} bad_y={max_y:.4f} "
                f"good_f={good_forward:.2f} good_s={good_scale:.2f} good_n={good_neck:.2f} "
                f"good_side={good_side:.2f} good_cva={good_cva:.1f}°"
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

    @pyqtSlot(float, float, float, bool, float, float, str, float, float, str, str)
    def _on_pose_detected(
        self,
        nose_y: float,
        nose_x: float,
        forward_offset: float = 0.0,
        shoulders_detected: bool = False,
        scale_ratio: float = 0.0,
        neck_v_ratio: float = 0.0,
        view_mode: str = "front",
        side_forward: float = 0.0,
        cva_deg: float = 90.0,
        active_side: str = "none",
        facing_dir: str = "none",
    ):
        if self.is_calibrating or not self.is_enabled:
            return

        self.consecutive_no_detection = 0
        self._screen_locked_this_away = False

        # Update monitor detection
        screens = QApplication.instance().screens()
        self.current_monitor_id = self.monitor_detector.update(nose_x, screens)

        # Get calibration for current monitor
        calibration = self._get_active_calibration()
        self._evaluate_posture(
            nose_y,
            calibration,
            forward_offset,
            shoulders_detected,
            scale_ratio,
            neck_v_ratio,
            view_mode,
            side_forward,
            cva_deg,
            active_side,
            facing_dir,
        )

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
        self,
        current_y: float,
        calibration: MonitorCalibration | None,
        forward_offset: float = 0.0,
        shoulders_detected: bool = False,
        scale_ratio: float = 0.0,
        neck_v_ratio: float = 0.0,
        view_mode: str = "front",
        side_forward: float = 0.0,
        cva_deg: float = 90.0,
        active_side: str = "none",
        facing_dir: str = "none",
    ):
        delta_z = 0.0
        delta_scale = 0.0
        delta_neck = 0.0
        forward_slouch = 0.0
        good_forward = 0.55
        good_scale = 0.40
        good_neck = 0.32
        good_side_forward = 0.0
        good_cva = 65.0

        if view_mode == "side":
            good_side_forward = (
                getattr(calibration, "good_side_forward", 0.0)
                if calibration
                else 0.0
            )
            good_cva = (
                getattr(calibration, "good_cva", 65.0)
                if calibration
                else 65.0
            )

            delta_side = side_forward - good_side_forward
            forward_slouch = delta_side

            threshold_scale = 1.5 - 0.5 * self.settings.sensitivity
            enter_threshold = 0.08 * threshold_scale
            exit_threshold = enter_threshold * self.HYSTERESIS_FACTOR
            threshold = exit_threshold if self.is_slouching else enter_threshold

            # Recline gate: If ear is behind the shoulder plumb line by >= 0.05 norm units,
            # user is reclining back into their chair. Slouching is impossible.
            if delta_side <= -0.05:
                is_bad_posture = False
                slouch_severity = 0.0
            else:
                cva_slouch = (cva_deg > 0.0 and cva_deg < 50.0)
                plumb_slouch = delta_side > threshold

                if plumb_slouch or cva_slouch:
                    is_bad_posture = True
                    if plumb_slouch:
                        excess = delta_side - enter_threshold
                        slouch_severity = max(0.0, min(1.0, excess / 0.10))
                    else:
                        slouch_severity = max(0.0, min(1.0, (50.0 - cva_deg) / 20.0))
                else:
                    is_bad_posture = False
                    slouch_severity = 0.0

            uncalibrated_suffix = "" if calibration and getattr(calibration, "is_calibrated", False) else " (uncalibrated)"
        elif shoulders_detected:
            # Baseline upright forward posture (0.55 by default)
            good_forward = (
                getattr(calibration, "good_forward_offset", 0.55)
                if calibration
                else 0.55
            )
            good_scale = (
                getattr(calibration, "good_head_scale", 0.40)
                if calibration
                else 0.40
            )
            good_neck = (
                getattr(calibration, "good_neck_ratio", 0.32)
                if calibration
                else 0.32
            )

            threshold_scale = 1.5 - 0.5 * self.settings.sensitivity
            enter_threshold = self.FORWARD_THRESHOLD_BASE * threshold_scale
            exit_threshold = enter_threshold * self.HYSTERESIS_FACTOR
            threshold = exit_threshold if self.is_slouching else enter_threshold

            delta_z = forward_offset - good_forward

            base_s = max(0.1, good_scale)
            delta_scale = (scale_ratio - base_s) / base_s if scale_ratio > 0.0 else 0.0

            base_n = max(0.1, good_neck)
            delta_neck = (base_n - neck_v_ratio) / base_n if neck_v_ratio > 0.0 else 0.0

            # Recline gate: If head is clearly behind upright baseline, user is leaning back
            # Completely suppress slouching when reclined
            if delta_z <= -0.05:
                forward_slouch = delta_z
            else:
                forward_slouch = (
                    delta_z
                    + 0.5 * max(0.0, delta_scale)
                    + 0.5 * max(0.0, delta_neck)
                )

            if forward_slouch <= 0.0:
                # Leaning back or sitting upright at or behind baseline
                is_bad_posture = False
                slouch_severity = 0.0
            else:
                is_bad_posture = forward_slouch > threshold
                if is_bad_posture:
                    excess = forward_slouch - enter_threshold
                    slouch_severity = max(0.0, min(1.0, excess / 0.10))
                else:
                    slouch_severity = 0.0
            uncalibrated_suffix = ""
        else:
            # Fallback to vertical nose Y evaluation when shoulders are not visible
            if calibration:
                good_y = calibration.good_posture_y
                bad_y = calibration.bad_posture_y
                uncalibrated_suffix = ""
            else:
                good_y = self.settings.DEFAULTS["good_posture_y"]
                bad_y = self.settings.DEFAULTS["bad_posture_y"]
                uncalibrated_suffix = " (uncalibrated)"

            posture_range = max(0.08, abs(bad_y - good_y))

            slouch_amount = current_y - bad_y
            base_threshold = self.DEAD_ZONE * posture_range * self.settings.sensitivity

            enter_threshold = base_threshold
            exit_threshold = base_threshold * self.HYSTERESIS_FACTOR

            threshold = exit_threshold if self.is_slouching else enter_threshold
            is_bad_posture = slouch_amount > threshold

            if is_bad_posture:
                severity = (slouch_amount - enter_threshold) / posture_range
                slouch_severity = max(0.0, min(1.0, severity))
            else:
                slouch_severity = 0.0

        if is_bad_posture:
            self.consecutive_bad_frames += 1
            self.consecutive_good_frames = 0

            if self.consecutive_bad_frames >= self.FRAME_THRESHOLD:
                was_slouching = self.is_slouching
                self.is_slouching = True

                if self.settings.notification_mode == "dim_screen":
                    eased_severity = slouch_severity * slouch_severity
                    opacity = 0.25 + eased_severity * 0.75
                    self.overlay.set_target_opacity(opacity)

                profile_suffix = f" ({self.settings.current_profile.capitalize()})"
                self.tray.set_status(f"Slouching{profile_suffix}{uncalibrated_suffix}")
                self.tray.set_posture_state("slouching")

                if not was_slouching:
                    self._emit_dbus_status()
                    if self.settings.notification_mode == "led_blink":
                        self.led_blinker.on_slouching_started()
        else:
            self.consecutive_good_frames += 1
            self.consecutive_bad_frames = 0

            if self.consecutive_good_frames >= self.FRAME_THRESHOLD:
                was_slouching = self.is_slouching
                self.is_slouching = False

                if self.settings.notification_mode == "dim_screen":
                    self.overlay.set_target_opacity(0)

                profile_suffix = f" ({self.settings.current_profile.capitalize()})"
                self.tray.set_status(
                    f"Good posture{profile_suffix}{uncalibrated_suffix}"
                )
                self.tray.set_posture_state("good")

                if was_slouching:
                    self._emit_dbus_status()
                    if self.settings.notification_mode == "led_blink":
                        self.led_blinker.on_slouching_stopped()

        # Debug logging
        if self.debug:
            current_state = "slouching" if self.is_slouching else "good"
            if current_state != self._last_debug_state:
                self._last_debug_state = current_state
                if view_mode == "side":
                    mode_str = f"SIDE ({active_side.upper()}/{facing_dir.upper()})"
                    metric = forward_slouch
                else:
                    mode_str = "SHOULDERS" if shoulders_detected else "VERTICAL"
                    metric = forward_slouch if shoulders_detected else current_y
                self._print_debug(
                    f"State changed to: {current_state.upper()} ({mode_str}: val={metric:.2f})"
                )

            self._debug_frame_counter = getattr(self, "_debug_frame_counter", 0) + 1
            if self._debug_frame_counter % 12 == 0:
                if view_mode == "side":
                    self._print_debug(
                        f"POLL | state={current_state.upper()} | side={forward_slouch:+.2f} "
                        f"(dx={side_forward:+.2f}, cva={cva_deg:.1f}°, {active_side}/{facing_dir}, thresh={threshold:.2f})"
                    )
                elif shoulders_detected:
                    self._print_debug(
                        f"POLL | state={current_state.upper()} | fused={forward_slouch:+.2f} "
                        f"(dZ={delta_z:+.2f}, dScale={delta_scale:+.2f}, dNeck={delta_neck:+.2f}, thresh={threshold:.2f})"
                    )
                else:
                    self._print_debug(
                        f"POLL | state={current_state.upper()} | nose_y={current_y:.2f} (slouch={slouch_amount:+.2f}, thresh={threshold:.2f})"
                    )

        if self.preview_window and self.preview_window.isVisible():
            if view_mode == "side":
                tracking_mode = f"Side Profile ({active_side.title()}, Facing {facing_dir.title()})"
            else:
                tracking_mode = (
                    "Fused 3-Signal"
                    if shoulders_detected and forward_offset > 0
                    else ("Nose Fallback" if not shoulders_detected else "Searching...")
                )
            self.preview_window.update_metrics(
                forward_offset=forward_offset if shoulders_detected else 0.0,
                good_forward=good_forward,
                enter_threshold=enter_threshold,
                exit_threshold=exit_threshold,
                is_slouching=self.is_slouching,
                shoulders_detected=shoulders_detected,
                tracking_mode=tracking_mode,
                bad_frames=self.consecutive_bad_frames,
                frame_threshold=self.FRAME_THRESHOLD,
                delta_z=delta_z if shoulders_detected else 0.0,
                scale_ratio=scale_ratio if shoulders_detected else 0.0,
                good_scale=good_scale,
                delta_scale=delta_scale if shoulders_detected else 0.0,
                neck_v_ratio=neck_v_ratio if shoulders_detected else 0.0,
                good_neck=good_neck,
                delta_neck=delta_neck if shoulders_detected else 0.0,
                forward_slouch=forward_slouch,
                view_mode=view_mode,
                side_forward=side_forward,
                good_side_forward=good_side_forward,
                cva_deg=cva_deg,
                good_cva=good_cva,
                active_side=active_side,
                facing_dir=facing_dir,
            )

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

    def show_preview_window(self):
        """Display the Live Posture Monitor and Detection Tuning Window."""
        if self.preview_window is None:
            from .preview_window import PostureMonitorWindow

            self.preview_window = PostureMonitorWindow(self)
            self.preview_window.upright_calibrated.connect(self._on_upright_calibrated)
            self.preview_window.sensitivity_changed.connect(self._on_sensitivity_changed)
            self.preview_window.profile_switched.connect(self.set_profile)
            self.preview_window.view_mode_changed.connect(self.set_view_mode)
            self.pose_detector.preview_frame.connect(self.preview_window.update_frame)

        self.preview_window.show()
        self.preview_window.activateWindow()
        self.preview_window.raise_()

    @pyqtSlot(float, float, float, float, float)
    def _on_upright_calibrated(
        self,
        baseline_val: float,
        baseline_scale: float = 0.40,
        baseline_neck: float = 0.32,
        baseline_side: float = 0.0,
        baseline_cva: float = 65.0,
    ):
        """Save calibrated upright baseline for current monitor and profile."""
        current_id = self.current_monitor_id
        screens = QApplication.instance().screens()
        if not current_id and screens:
            current_id = get_monitor_id(screens[0])
        current_id = current_id or "default"

        cal = self.monitor_calibrations.get(current_id)
        if cal:
            cal.good_forward_offset = baseline_val
            cal.good_head_scale = baseline_scale
            cal.good_neck_ratio = baseline_neck
            cal.good_side_forward = baseline_side
            cal.good_cva = baseline_cva
        else:
            cal = MonitorCalibration(
                monitor_id=current_id,
                good_posture_y=self.settings.DEFAULTS["good_posture_y"],
                bad_posture_y=self.settings.DEFAULTS["bad_posture_y"],
                is_calibrated=True,
                good_forward_offset=baseline_val,
                good_head_scale=baseline_scale,
                good_neck_ratio=baseline_neck,
                good_side_forward=baseline_side,
                good_cva=baseline_cva,
            )
            self.monitor_calibrations[current_id] = cal

        self.settings.set_monitor_calibration(cal)
        self.settings.sync()
        if self.debug:
            self._print_debug(
                f"Upright baseline set to F={baseline_val:.2f}, S={baseline_scale:.2f}, V={baseline_neck:.2f}, "
                f"Side={baseline_side:.2f}, CVA={baseline_cva:.1f}° for monitor {current_id} ({self.settings.current_profile})"
            )

    @pyqtSlot(str)
    def set_view_mode(self, mode: str):
        """Set camera view mode ('auto', 'front', 'side')."""
        if mode not in ("auto", "front", "side"):
            return
        self.settings.camera_view_mode = mode
        self.settings.sync()
        self.pose_detector.set_view_mode(mode)
        if self.debug:
            self._print_debug(f"Camera view mode set to: {mode}")

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

    @pyqtSlot(str)
    def _on_profile_changed(self, profile: str):
        self.set_profile(profile)

    def set_profile(self, profile: str):
        """Switch active posture profile ('sitting' or 'standing')."""
        if profile not in ("sitting", "standing"):
            return

        self.settings.current_profile = profile
        self.settings.sync()
        self._load_monitor_calibrations()
        self._update_tray_calibrations()
        self.tray.set_profile(profile)

        profile_title = profile.capitalize()
        if not self.settings.has_any_calibration(profile):
            self.tray.set_status(f"Monitoring ({profile_title}, Uncalibrated)")
        else:
            self.tray.set_status(f"Monitoring ({profile_title})")

        self._emit_dbus_status()
        if self.debug:
            self._print_debug(f"Profile switched to: {profile}")

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
