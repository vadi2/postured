"""Tests for Settings class."""

import pytest


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
