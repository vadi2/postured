from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QSettings

if TYPE_CHECKING:
    from PyQt6.QtGui import QScreen


@dataclass
class MonitorCalibration:
    """Per-monitor calibration data."""

    monitor_id: str  # e.g., "HDMI-1_1920x1080"
    good_posture_y: float
    bad_posture_y: float
    is_calibrated: bool = True
    good_forward_offset: float = 0.55
    good_head_scale: float = 0.40
    good_neck_ratio: float = 0.32
    good_side_forward: float = 0.0
    good_cva: float = 65.0


def get_monitor_id(screen: "QScreen") -> str:
    """Generate a stable monitor ID from screen properties."""
    return f"{screen.name()}_{screen.geometry().width()}x{screen.geometry().height()}"


class Settings:
    """Application settings using Qt's QSettings.

    Stores config in ~/.config/postured/postured.conf (on Linux).
    """

    DEFAULTS = {
        "current_profile": "sitting",
        "sensitivity": 0.85,
        "camera_index": 0,
        "camera_view_mode": "auto",  # "auto", "front", "side"
        "lock_when_away": False,
        "notification_mode": "dim_screen",  # "dim_screen" or "led_blink"
        "good_posture_y": 0.4,
        "bad_posture_y": 0.6,
        "is_calibrated": False,
    }

    def __init__(self):
        self._settings = QSettings("postured", "postured")

    @property
    def current_profile(self) -> str:
        value = str(
            self._settings.value("current_profile", self.DEFAULTS["current_profile"])
        )
        if value not in ("sitting", "standing"):
            return self.DEFAULTS["current_profile"]
        return value

    @current_profile.setter
    def current_profile(self, value: str):
        if value in ("sitting", "standing"):
            self._settings.setValue("current_profile", value)

    @property
    def sensitivity(self) -> float:
        value = float(self._settings.value("sensitivity", self.DEFAULTS["sensitivity"]))
        return max(0.1, min(1.0, value))

    @sensitivity.setter
    def sensitivity(self, value: float):
        self._settings.setValue("sensitivity", value)

    @property
    def camera_index(self) -> int:
        value = int(self._settings.value("camera_index", self.DEFAULTS["camera_index"]))
        return max(0, value)

    @camera_index.setter
    def camera_index(self, value: int):
        self._settings.setValue("camera_index", value)

    @property
    def lock_when_away(self) -> bool:
        return self._settings.value(
            "lock_when_away", self.DEFAULTS["lock_when_away"], type=bool
        )

    @lock_when_away.setter
    def lock_when_away(self, value: bool):
        self._settings.setValue("lock_when_away", value)

    @property
    def notification_mode(self) -> str:
        value = self._settings.value(
            "notification_mode", self.DEFAULTS["notification_mode"]
        )
        if value not in ("dim_screen", "led_blink"):
            return self.DEFAULTS["notification_mode"]
        return value

    @notification_mode.setter
    def notification_mode(self, value: str):
        self._settings.setValue("notification_mode", value)

    @property
    def camera_view_mode(self) -> str:
        value = str(
            self._settings.value(
                "camera_view_mode", self.DEFAULTS["camera_view_mode"]
            )
        )
        if value not in ("auto", "front", "side"):
            return "auto"
        return value

    @camera_view_mode.setter
    def camera_view_mode(self, value: str):
        self._settings.setValue("camera_view_mode", value)

    @property
    def good_posture_y(self) -> float:
        value = float(
            self._settings.value("good_posture_y", self.DEFAULTS["good_posture_y"])
        )
        return max(0.0, min(1.0, value))

    @good_posture_y.setter
    def good_posture_y(self, value: float):
        self._settings.setValue("good_posture_y", value)

    @property
    def bad_posture_y(self) -> float:
        value = float(
            self._settings.value("bad_posture_y", self.DEFAULTS["bad_posture_y"])
        )
        return max(0.0, min(1.0, value))

    @bad_posture_y.setter
    def bad_posture_y(self, value: float):
        self._settings.setValue("bad_posture_y", value)

    @property
    def is_calibrated(self) -> bool:
        return self._settings.value(
            "is_calibrated", self.DEFAULTS["is_calibrated"], type=bool
        )

    @is_calibrated.setter
    def is_calibrated(self, value: bool):
        self._settings.setValue("is_calibrated", value)

    def sync(self):
        """Force write settings to disk."""
        self._settings.sync()

    # Per-monitor calibration methods

    def _get_group_for_profile(self, profile: str) -> str:
        return f"profiles/{profile}/monitors"

    def get_monitor_calibration(
        self, monitor_id: str, profile: str | None = None
    ) -> MonitorCalibration | None:
        """Get calibration data for a specific monitor under given or current profile."""
        target_profile = profile or self.current_profile

        # First check the profile-specific group
        group = self._get_group_for_profile(target_profile)
        self._settings.beginGroup(group)
        self._settings.beginGroup(monitor_id)

        is_calibrated = self._settings.value("is_calibrated", False, type=bool)
        if is_calibrated:
            good_y = float(
                self._settings.value("good_posture_y", self.DEFAULTS["good_posture_y"])
            )
            bad_y = float(
                self._settings.value("bad_posture_y", self.DEFAULTS["bad_posture_y"])
            )
            good_forward = float(
                self._settings.value("good_forward_offset", 0.55)
            )
            good_scale = float(
                self._settings.value("good_head_scale", 0.40)
            )
            good_neck = float(
                self._settings.value("good_neck_ratio", 0.32)
            )
            good_side = float(
                self._settings.value("good_side_forward", 0.0)
            )
            good_cva = float(
                self._settings.value("good_cva", 65.0)
            )
            self._settings.endGroup()
            self._settings.endGroup()
            if abs(bad_y - good_y) >= 0.01:
                return MonitorCalibration(
                    monitor_id=monitor_id,
                    good_posture_y=max(0.0, min(1.0, good_y)),
                    bad_posture_y=max(0.0, min(1.0, bad_y)),
                    is_calibrated=True,
                    good_forward_offset=good_forward,
                    good_head_scale=good_scale,
                    good_neck_ratio=good_neck,
                    good_side_forward=good_side,
                    good_cva=good_cva,
                )

        self._settings.endGroup()
        self._settings.endGroup()

        # For "sitting" profile, fall back to legacy un-namespaced monitors group
        if target_profile == "sitting":
            self._settings.beginGroup("monitors")
            self._settings.beginGroup(monitor_id)
            is_calibrated = self._settings.value("is_calibrated", False, type=bool)
            if not is_calibrated:
                self._settings.endGroup()
                self._settings.endGroup()
                return None

            good_y = float(
                self._settings.value("good_posture_y", self.DEFAULTS["good_posture_y"])
            )
            bad_y = float(
                self._settings.value("bad_posture_y", self.DEFAULTS["bad_posture_y"])
            )
            good_forward = float(
                self._settings.value("good_forward_offset", 0.55)
            )
            good_scale = float(
                self._settings.value("good_head_scale", 0.40)
            )
            good_neck = float(
                self._settings.value("good_neck_ratio", 0.32)
            )
            good_side = float(
                self._settings.value("good_side_forward", 0.0)
            )
            good_cva = float(
                self._settings.value("good_cva", 65.0)
            )
            self._settings.endGroup()
            self._settings.endGroup()
            if abs(bad_y - good_y) >= 0.01:
                return MonitorCalibration(
                    monitor_id=monitor_id,
                    good_posture_y=max(0.0, min(1.0, good_y)),
                    bad_posture_y=max(0.0, min(1.0, bad_y)),
                    is_calibrated=True,
                    good_forward_offset=good_forward,
                    good_head_scale=good_scale,
                    good_neck_ratio=good_neck,
                    good_side_forward=good_side,
                    good_cva=good_cva,
                )

        return None

    def set_monitor_calibration(
        self, calibration: MonitorCalibration, profile: str | None = None
    ) -> None:
        """Store calibration data for a specific monitor under given or current profile."""
        target_profile = profile or self.current_profile
        group = self._get_group_for_profile(target_profile)

        self._settings.beginGroup(group)
        self._settings.beginGroup(calibration.monitor_id)

        self._settings.setValue("good_posture_y", calibration.good_posture_y)
        self._settings.setValue("bad_posture_y", calibration.bad_posture_y)
        self._settings.setValue("good_forward_offset", calibration.good_forward_offset)
        self._settings.setValue("good_head_scale", calibration.good_head_scale)
        self._settings.setValue("good_neck_ratio", calibration.good_neck_ratio)
        self._settings.setValue("good_side_forward", calibration.good_side_forward)
        self._settings.setValue("good_cva", calibration.good_cva)
        self._settings.setValue("is_calibrated", calibration.is_calibrated)

        self._settings.endGroup()
        self._settings.endGroup()

    def get_all_monitor_calibrations(
        self, profile: str | None = None
    ) -> list[MonitorCalibration]:
        """Get calibration data for all calibrated monitors under given or current profile."""
        target_profile = profile or self.current_profile
        calibrations = []

        group = self._get_group_for_profile(target_profile)
        self._settings.beginGroup(group)
        monitor_ids = self._settings.childGroups()
        self._settings.endGroup()

        for monitor_id in monitor_ids:
            calibration = self.get_monitor_calibration(monitor_id, target_profile)
            if calibration is not None:
                calibrations.append(calibration)

        # Fallback to legacy monitors group if sitting profile has no calibrations yet
        if not calibrations and target_profile == "sitting":
            self._settings.beginGroup("monitors")
            legacy_ids = self._settings.childGroups()
            self._settings.endGroup()
            for monitor_id in legacy_ids:
                calibration = self.get_monitor_calibration(monitor_id, "sitting")
                if calibration is not None:
                    calibrations.append(calibration)

        return calibrations

    def has_any_calibration(self, profile: str | None = None) -> bool:
        """Check if any monitor has been calibrated for the given or current profile."""
        calibrations = self.get_all_monitor_calibrations(profile)
        if calibrations:
            return True

        target_profile = profile or self.current_profile
        if target_profile == "sitting":
            return self.is_calibrated

        return False

    def migrate_legacy_calibration(
        self, primary_monitor_id: str, profile: str | None = None
    ) -> bool:
        """Migrate legacy global calibration to primary monitor.

        Returns True if migration was performed, False otherwise.
        """
        # Only migrate if there's legacy calibration and no per-monitor data
        if not self.is_calibrated:
            return False

        target_profile = profile or self.current_profile
        existing = self.get_monitor_calibration(primary_monitor_id, target_profile)
        if existing is not None:
            return False  # Already has per-monitor calibration

        # Migrate legacy values to primary monitor
        calibration = MonitorCalibration(
            monitor_id=primary_monitor_id,
            good_posture_y=self.good_posture_y,
            bad_posture_y=self.bad_posture_y,
            is_calibrated=True,
        )
        self.set_monitor_calibration(calibration, target_profile)
        self.sync()
        return True
