"""Smoke test for Application startup.

This test verifies the Application can instantiate without crashing,
catching issues like missing @pyqtSlot decorators on D-Bus callbacks.
"""

from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_camera(monkeypatch):
    """Mock camera-related functionality to avoid hardware dependency."""
    monkeypatch.setattr(
        "postured.pose_detector.PoseDetector.start",
        Mock(),
    )
    monkeypatch.setattr(
        "postured.pose_detector.PoseDetector.available_cameras",
        Mock(return_value=[]),
    )


def test_application_startup(qapp, mock_qsettings, mock_camera):
    """Application starts without crashing.

    This smoke test catches initialization errors such as:
    - Missing @pyqtSlot decorators on D-Bus signal callbacks
    - Import errors
    - Incorrect signal/slot connections
    """
    from postured.app import Application

    app = Application(debug=False)

    # Verify key components initialized
    assert app.settings is not None
    assert app.tray is not None
    assert app.overlay is not None
    assert app.pose_detector is not None
    assert app._screen_lock_monitor is not None

    app.shutdown()
