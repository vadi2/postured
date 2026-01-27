"""Shared pytest fixtures for postured tests."""

from dataclasses import dataclass, field
from collections import deque

import pytest


@dataclass
class MockAppState:
    """Mimics Application state for isolated algorithm testing."""

    # Settings
    good_posture_y: float = 0.4
    bad_posture_y: float = 0.6
    sensitivity: float = 0.85
    lock_when_away: bool = False
    is_calibrated: bool = True

    # State
    is_enabled: bool = True
    is_calibrating: bool = False
    is_slouching: bool = False
    consecutive_bad_frames: int = 0
    consecutive_good_frames: int = 0
    consecutive_no_detection: int = 0

    # Constants
    FRAME_THRESHOLD: int = 8
    AWAY_THRESHOLD: int = 15
    HYSTERESIS_FACTOR: float = 0.5
    DEAD_ZONE: float = 0.03


@dataclass
class MockOverlayState:
    """Mimics Overlay state for isolated opacity testing."""

    current_opacity: float = 0.0
    target_opacity: float = 0.0

    EASE_IN_RATE: float = 0.015
    EASE_OUT_RATE: float = 0.047


@dataclass
class MockCalibrationState:
    """Mimics CalibrationWindow state for calibration testing."""

    current_step: int = 0
    captured_values: list = field(default_factory=list)
    current_nose_y: float = 0.5

    CORNERS: list = field(
        default_factory=lambda: ["TOP-LEFT", "TOP-RIGHT", "BOTTOM-RIGHT", "BOTTOM-LEFT"]
    )


@dataclass
class MockPoseWorkerState:
    """Mimics PoseWorker state for smoothing tests."""

    nose_y_history: deque = field(default_factory=lambda: deque(maxlen=5))
    nose_x_history: deque = field(default_factory=lambda: deque(maxlen=5))
    SMOOTHING_WINDOW: int = 5


@dataclass
class MockMonitorDetectorState:
    """Mimics MonitorDetector state for gaze detection tests."""

    _current_monitor_id: str | None = None
    _pending_monitor_id: str | None = None
    _pending_frames: int = 0
    HYSTERESIS_FRAMES: int = 5


@pytest.fixture
def mock_app_state():
    """Provides a fresh MockAppState for each test."""
    return MockAppState()


@pytest.fixture
def mock_overlay_state():
    """Provides a fresh MockOverlayState for each test."""
    return MockOverlayState()


@pytest.fixture
def mock_calibration_state():
    """Provides a fresh MockCalibrationState for each test."""
    return MockCalibrationState()


@pytest.fixture
def mock_pose_worker_state():
    """Provides a fresh MockPoseWorkerState for each test."""
    return MockPoseWorkerState()


@pytest.fixture
def mock_monitor_detector_state():
    """Provides a fresh MockMonitorDetectorState for each test."""
    return MockMonitorDetectorState()


@pytest.fixture
def mock_qsettings(tmp_path, monkeypatch):
    """Patch QSettings to use a temp file for isolated config testing."""
    config_file = tmp_path / "postured.conf"

    # We need to patch the QSettings constructor to use our temp path
    original_qsettings = None
    try:
        from PyQt6.QtCore import QSettings

        original_qsettings = QSettings
    except ImportError:
        pytest.skip("PyQt6 not available")

    class MockQSettings(original_qsettings):
        def __init__(self, *args, **kwargs):
            # Use IniFormat with our temp path
            super().__init__(str(config_file), original_qsettings.Format.IniFormat)

    monkeypatch.setattr("PyQt6.QtCore.QSettings", MockQSettings)
    return config_file
