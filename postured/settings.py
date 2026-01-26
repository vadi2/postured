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


def get_monitor_id(screen: "QScreen") -> str:
    """Generate a stable monitor ID from screen properties."""
    return f"{screen.name()}_{screen.geometry().width()}x{screen.geometry().height()}"


class Settings:
    """Application settings using Qt's QSettings.

    Stores config in ~/.config/postured/postured.conf (on Linux).
    """

    DEFAULTS = {
        "sensitivity": 0.85,
        "camera_index": 0,
        "lock_when_away": False,
        "good_posture_y": 0.4,
        "bad_posture_y": 0.6,
        "is_calibrated": False,
    }

    def __init__(self):
        self._settings = QSettings("postured", "postured")

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

    def get_monitor_calibration(self, monitor_id: str) -> MonitorCalibration | None:
        """Get calibration data for a specific monitor."""
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

        self._settings.endGroup()
        self._settings.endGroup()

        return MonitorCalibration(
            monitor_id=monitor_id,
            good_posture_y=max(0.0, min(1.0, good_y)),
            bad_posture_y=max(0.0, min(1.0, bad_y)),
            is_calibrated=True,
        )

    def set_monitor_calibration(self, calibration: MonitorCalibration) -> None:
        """Store calibration data for a specific monitor."""
        self._settings.beginGroup("monitors")
        self._settings.beginGroup(calibration.monitor_id)

        self._settings.setValue("good_posture_y", calibration.good_posture_y)
        self._settings.setValue("bad_posture_y", calibration.bad_posture_y)
        self._settings.setValue("is_calibrated", calibration.is_calibrated)

        self._settings.endGroup()
        self._settings.endGroup()

    def get_all_monitor_calibrations(self) -> list[MonitorCalibration]:
        """Get calibration data for all calibrated monitors."""
        calibrations = []

        self._settings.beginGroup("monitors")
        monitor_ids = self._settings.childGroups()
        self._settings.endGroup()

        for monitor_id in monitor_ids:
            calibration = self.get_monitor_calibration(monitor_id)
            if calibration is not None:
                calibrations.append(calibration)

        return calibrations

    def has_any_calibration(self) -> bool:
        """Check if any monitor has been calibrated."""
        # Check per-monitor calibrations
        calibrations = self.get_all_monitor_calibrations()
        if calibrations:
            return True

        # Fall back to legacy global calibration
        return self.is_calibrated

    def migrate_legacy_calibration(self, primary_monitor_id: str) -> bool:
        """Migrate legacy global calibration to primary monitor.

        Returns True if migration was performed, False otherwise.
        """
        # Only migrate if there's legacy calibration and no per-monitor data
        if not self.is_calibrated:
            return False

        existing = self.get_monitor_calibration(primary_monitor_id)
        if existing is not None:
            return False  # Already has per-monitor calibration

        # Migrate legacy values to primary monitor
        calibration = MonitorCalibration(
            monitor_id=primary_monitor_id,
            good_posture_y=self.good_posture_y,
            bad_posture_y=self.bad_posture_y,
            is_calibrated=True,
        )
        self.set_monitor_calibration(calibration)
        self.sync()
        return True
