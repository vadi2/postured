"""Tests for Sitting vs. Standing profiles."""

from unittest.mock import MagicMock
from PyQt6.QtCore import QObject


class MockParentApp(QObject):
    """QObject wrapper for PosturedDBusAdaptor parent requirement."""

    def __init__(self):
        super().__init__()
        self.settings = MagicMock()
        self.is_enabled = True
        self.is_calibrating = False
        self.is_slouching = False
        self.consecutive_no_detection = 0
        self.AWAY_THRESHOLD = 15
        self.set_profile = MagicMock()


class TestProfileSettings:
    """Test Settings profile management and calibration isolation."""

    def test_default_profile_is_sitting(self, mock_qsettings):
        from postured.settings import Settings

        settings = Settings()
        assert settings.current_profile == "sitting"

    def test_set_current_profile(self, mock_qsettings):
        from postured.settings import Settings

        settings = Settings()
        settings.current_profile = "standing"
        assert settings.current_profile == "standing"

        settings.current_profile = "invalid_profile"
        assert settings.current_profile == "standing"

    def test_per_profile_monitor_calibration_isolation(self, mock_qsettings):
        from postured.settings import Settings, MonitorCalibration

        settings = Settings()

        sitting_cal = MonitorCalibration(
            monitor_id="DP-1",
            good_posture_y=0.35,
            bad_posture_y=0.55,
            is_calibrated=True,
        )
        standing_cal = MonitorCalibration(
            monitor_id="DP-1",
            good_posture_y=0.20,
            bad_posture_y=0.40,
            is_calibrated=True,
        )

        settings.set_monitor_calibration(sitting_cal, profile="sitting")
        settings.set_monitor_calibration(standing_cal, profile="standing")

        # Query while sitting
        settings.current_profile = "sitting"
        retrieved_sitting = settings.get_monitor_calibration("DP-1")
        assert retrieved_sitting is not None
        assert retrieved_sitting.good_posture_y == 0.35
        assert retrieved_sitting.bad_posture_y == 0.55

        # Query while standing
        settings.current_profile = "standing"
        retrieved_standing = settings.get_monitor_calibration("DP-1")
        assert retrieved_standing is not None
        assert retrieved_standing.good_posture_y == 0.20
        assert retrieved_standing.bad_posture_y == 0.40

    def test_has_any_calibration_per_profile(self, mock_qsettings):
        from postured.settings import Settings, MonitorCalibration

        settings = Settings()
        cal = MonitorCalibration(
            monitor_id="HDMI-1",
            good_posture_y=0.4,
            bad_posture_y=0.6,
            is_calibrated=True,
        )

        settings.set_monitor_calibration(cal, profile="sitting")
        assert settings.has_any_calibration("sitting") is True
        assert settings.has_any_calibration("standing") is False


class TestProfileDBus:
    """Test D-Bus profile query and switch methods."""

    def test_dbus_get_profile(self, qapp):
        from postured.dbus_service import PosturedDBusAdaptor

        mock_app = MockParentApp()
        mock_app.settings.current_profile = "standing"

        adaptor = PosturedDBusAdaptor(mock_app)
        assert adaptor.GetProfile() == "standing"

    def test_dbus_set_profile(self, qapp):
        from postured.dbus_service import PosturedDBusAdaptor

        mock_app = MockParentApp()
        adaptor = PosturedDBusAdaptor(mock_app)

        adaptor.SetProfile("standing")
        mock_app.set_profile.assert_called_once_with("standing")

    def test_status_dict_includes_profile(self, qapp):
        from postured.dbus_service import PosturedDBusAdaptor

        mock_app = MockParentApp()
        mock_app.settings.current_profile = "sitting"

        adaptor = PosturedDBusAdaptor(mock_app)
        status = adaptor.GetStatus()
        assert "profile" in status
        assert status["profile"] == "sitting"
