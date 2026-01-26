"""Tests for Settings class."""



def test_default_sensitivity(mock_qsettings):
    """Default sensitivity is returned when no config exists."""
    from postured.settings import Settings

    settings = Settings()
    assert settings.sensitivity == 0.85


def test_default_camera_index(mock_qsettings):
    """Default camera_index is returned when no config exists."""
    from postured.settings import Settings

    settings = Settings()
    assert settings.camera_index == 0


def test_default_lock_when_away(mock_qsettings):
    """Default lock_when_away is False when no config exists."""
    from postured.settings import Settings

    settings = Settings()
    assert settings.lock_when_away is False


def test_default_posture_values(mock_qsettings):
    """Default posture Y values are returned when no config exists."""
    from postured.settings import Settings

    settings = Settings()
    assert settings.good_posture_y == 0.4
    assert settings.bad_posture_y == 0.6


def test_default_is_calibrated(mock_qsettings):
    """Default is_calibrated is False when no config exists."""
    from postured.settings import Settings

    settings = Settings()
    assert settings.is_calibrated is False


def test_sensitivity_clamps_low(mock_qsettings):
    """Sensitivity is clamped to minimum 0.1."""
    from postured.settings import Settings

    settings = Settings()
    settings.sensitivity = -0.5
    settings.sync()
    # Re-read to test clamping on read
    settings2 = Settings()
    assert settings2.sensitivity == 0.1


def test_sensitivity_clamps_high(mock_qsettings):
    """Sensitivity is clamped to maximum 1.0."""
    from postured.settings import Settings

    settings = Settings()
    settings.sensitivity = 2.0
    settings.sync()
    settings2 = Settings()
    assert settings2.sensitivity == 1.0


def test_camera_index_clamps_negative(mock_qsettings):
    """Camera index is clamped to minimum 0."""
    from postured.settings import Settings

    settings = Settings()
    settings.camera_index = -5
    settings.sync()
    settings2 = Settings()
    assert settings2.camera_index == 0


def test_posture_y_clamps_low(mock_qsettings):
    """Posture Y values are clamped to minimum 0.0."""
    from postured.settings import Settings

    settings = Settings()
    settings.good_posture_y = -0.5
    settings.bad_posture_y = -0.3
    settings.sync()
    settings2 = Settings()
    assert settings2.good_posture_y == 0.0
    assert settings2.bad_posture_y == 0.0


def test_posture_y_clamps_high(mock_qsettings):
    """Posture Y values are clamped to maximum 1.0."""
    from postured.settings import Settings

    settings = Settings()
    settings.good_posture_y = 1.5
    settings.bad_posture_y = 2.0
    settings.sync()
    settings2 = Settings()
    assert settings2.good_posture_y == 1.0
    assert settings2.bad_posture_y == 1.0


def test_values_persist_after_set_get_cycle(mock_qsettings):
    """Values persist correctly after set/get cycle."""
    from postured.settings import Settings

    settings = Settings()
    settings.sensitivity = 0.5
    settings.camera_index = 2
    settings.lock_when_away = True
    settings.good_posture_y = 0.3
    settings.bad_posture_y = 0.7
    settings.is_calibrated = True
    settings.sync()

    # Create new instance to verify persistence
    settings2 = Settings()
    assert settings2.sensitivity == 0.5
    assert settings2.camera_index == 2
    assert settings2.lock_when_away is True
    assert settings2.good_posture_y == 0.3
    assert settings2.bad_posture_y == 0.7
    assert settings2.is_calibrated is True


def test_boolean_properties_type_conversion(mock_qsettings):
    """Boolean properties handle type conversion correctly."""
    from postured.settings import Settings

    settings = Settings()

    # Set True
    settings.lock_when_away = True
    settings.is_calibrated = True
    settings.sync()

    settings2 = Settings()
    assert settings2.lock_when_away is True
    assert settings2.is_calibrated is True
    assert isinstance(settings2.lock_when_away, bool)
    assert isinstance(settings2.is_calibrated, bool)

    # Set False
    settings2.lock_when_away = False
    settings2.is_calibrated = False
    settings2.sync()

    settings3 = Settings()
    assert settings3.lock_when_away is False
    assert settings3.is_calibrated is False


class TestMonitorCalibration:
    """Tests for per-monitor calibration storage."""

    def test_set_and_get_monitor_calibration(self, mock_qsettings):
        """Can store and retrieve monitor calibration."""
        from postured.settings import Settings, MonitorCalibration

        settings = Settings()
        calibration = MonitorCalibration(
            monitor_id="HDMI-1_1920x1080",
            good_posture_y=0.35,
            bad_posture_y=0.65,
            is_calibrated=True,
        )

        settings.set_monitor_calibration(calibration)
        settings.sync()

        # Retrieve with new settings instance
        settings2 = Settings()
        result = settings2.get_monitor_calibration("HDMI-1_1920x1080")

        assert result is not None
        assert result.monitor_id == "HDMI-1_1920x1080"
        assert result.good_posture_y == 0.35
        assert result.bad_posture_y == 0.65
        assert result.is_calibrated is True

    def test_get_nonexistent_calibration_returns_none(self, mock_qsettings):
        """Getting calibration for uncalibrated monitor returns None."""
        from postured.settings import Settings

        settings = Settings()
        result = settings.get_monitor_calibration("NONEXISTENT_1920x1080")

        assert result is None

    def test_get_all_monitor_calibrations(self, mock_qsettings):
        """Can retrieve all stored monitor calibrations."""
        from postured.settings import Settings, MonitorCalibration

        settings = Settings()

        # Store multiple calibrations
        cal1 = MonitorCalibration("HDMI-1_1920x1080", 0.35, 0.65, True)
        cal2 = MonitorCalibration("DP-2_1920x1080", 0.30, 0.60, True)
        settings.set_monitor_calibration(cal1)
        settings.set_monitor_calibration(cal2)
        settings.sync()

        # Retrieve all
        settings2 = Settings()
        calibrations = settings2.get_all_monitor_calibrations()

        assert len(calibrations) == 2
        monitor_ids = {c.monitor_id for c in calibrations}
        assert "HDMI-1_1920x1080" in monitor_ids
        assert "DP-2_1920x1080" in monitor_ids

    def test_has_any_calibration_with_monitor_calibrations(self, mock_qsettings):
        """has_any_calibration returns True when monitor calibrations exist."""
        from postured.settings import Settings, MonitorCalibration

        settings = Settings()
        # Use a unique monitor ID to avoid pollution from other tests
        unique_id = "UNIQUE-TEST-MONITOR_1920x1080"
        calibration = MonitorCalibration(unique_id, 0.35, 0.65, True)
        settings.set_monitor_calibration(calibration)
        settings.sync()

        settings2 = Settings()
        assert settings2.has_any_calibration() is True
        # Verify our specific calibration exists
        assert settings2.get_monitor_calibration(unique_id) is not None

    def test_has_any_calibration_with_legacy_calibration(self, mock_qsettings):
        """has_any_calibration returns True when legacy calibration exists."""
        from postured.settings import Settings

        settings = Settings()
        settings.is_calibrated = True
        settings.sync()

        settings2 = Settings()
        assert settings2.has_any_calibration() is True

    def test_migrate_legacy_calibration(self, mock_qsettings):
        """Legacy calibration is migrated to primary monitor."""
        from postured.settings import Settings

        # Use unique monitor ID to avoid pollution from other tests
        unique_id = "MIGRATE-TEST_1920x1080"

        settings = Settings()
        settings.good_posture_y = 0.38
        settings.bad_posture_y = 0.62
        settings.is_calibrated = True
        settings.sync()

        settings2 = Settings()
        # Verify precondition: no existing calibration for this unique ID
        assert settings2.get_monitor_calibration(unique_id) is None

        migrated = settings2.migrate_legacy_calibration(unique_id)

        assert migrated is True

        # Verify migration
        calibration = settings2.get_monitor_calibration(unique_id)
        assert calibration is not None
        assert calibration.good_posture_y == 0.38
        assert calibration.bad_posture_y == 0.62

    def test_migrate_legacy_calibration_skips_if_already_exists(self, mock_qsettings):
        """Migration skips if monitor already has calibration."""
        from postured.settings import Settings, MonitorCalibration

        settings = Settings()
        settings.is_calibrated = True
        settings.good_posture_y = 0.38
        settings.bad_posture_y = 0.62

        # Pre-existing per-monitor calibration
        existing = MonitorCalibration("HDMI-1_1920x1080", 0.30, 0.70, True)
        settings.set_monitor_calibration(existing)
        settings.sync()

        settings2 = Settings()
        migrated = settings2.migrate_legacy_calibration("HDMI-1_1920x1080")

        assert migrated is False

        # Verify existing calibration unchanged
        calibration = settings2.get_monitor_calibration("HDMI-1_1920x1080")
        assert calibration.good_posture_y == 0.30  # Not overwritten

    def test_migrate_legacy_calibration_skips_if_not_calibrated(self, mock_qsettings):
        """Migration skips if no legacy calibration exists."""
        from postured.settings import Settings

        # Use unique monitor ID to avoid pollution from other tests
        unique_id = "SKIP-MIGRATE-TEST_1920x1080"

        settings = Settings()
        # Explicitly set is_calibrated to False (the default)
        settings.is_calibrated = False
        settings.sync()

        settings2 = Settings()
        migrated = settings2.migrate_legacy_calibration(unique_id)

        assert migrated is False
        assert settings2.get_monitor_calibration(unique_id) is None

    def test_posture_values_clamped_on_read(self, mock_qsettings):
        """Monitor calibration values are clamped to 0.0-1.0."""
        from postured.settings import Settings, MonitorCalibration

        settings = Settings()
        # Store out-of-range values directly (simulating corrupt config)
        calibration = MonitorCalibration("TEST_1920x1080", -0.5, 1.5, True)
        settings.set_monitor_calibration(calibration)
        settings.sync()

        settings2 = Settings()
        result = settings2.get_monitor_calibration("TEST_1920x1080")

        assert result.good_posture_y == 0.0  # Clamped from -0.5
        assert result.bad_posture_y == 1.0  # Clamped from 1.5

    def test_update_existing_calibration(self, mock_qsettings):
        """Can update an existing monitor calibration."""
        from postured.settings import Settings, MonitorCalibration

        settings = Settings()

        # Initial calibration
        cal1 = MonitorCalibration("HDMI-1_1920x1080", 0.35, 0.65, True)
        settings.set_monitor_calibration(cal1)
        settings.sync()

        # Update calibration
        cal2 = MonitorCalibration("HDMI-1_1920x1080", 0.30, 0.70, True)
        settings.set_monitor_calibration(cal2)
        settings.sync()

        settings2 = Settings()
        result = settings2.get_monitor_calibration("HDMI-1_1920x1080")

        assert result.good_posture_y == 0.30
        assert result.bad_posture_y == 0.70
