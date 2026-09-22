from unittest.mock import MagicMock, Mock

import numpy as np
from PyQt6.QtCore import QObject


class MockApp(QObject):
    """Mock Application object for testing PostureMonitorWindow."""

    def __init__(self):
        super().__init__()
        self.settings = MagicMock()
        self.settings.sensitivity = 0.60
        self.settings.current_profile = "sitting"
        self.settings.DEFAULTS = {
            "good_posture_y": 0.4,
            "bad_posture_y": 0.6,
        }
        self.is_slouching = False
        self.pose_detector = MagicMock()
        self.current_monitor_id = "HDMI-0_1920x1080"
        self.monitor_calibrations = {}


class TestPreviewWindow:
    """Test suite for PostureMonitorWindow."""

    def test_window_initialization(self, qapp):
        """Window initializes properly with all components."""
        from postured.preview_window import PostureMonitorWindow

        app = MockApp()
        win = PostureMonitorWindow(app)

        assert win.canvas is not None
        assert win.gauge is not None
        assert win.btn_set_baseline is not None
        assert win.sens_slider is not None
        assert win.sitting_radio.isChecked() is True
        assert win.standing_radio.isChecked() is False

    def test_update_metrics(self, qapp):
        """update_metrics updates numerical and gauge readouts."""
        from postured.preview_window import PostureMonitorWindow

        app = MockApp()
        win = PostureMonitorWindow(app)

        win.update_metrics(
            forward_offset=0.72,
            good_forward=0.70,
            enter_threshold=0.10,
            exit_threshold=0.05,
            is_slouching=False,
            shoulders_detected=True,
            tracking_mode="Shoulders + Ears",
            bad_frames=2,
            frame_threshold=4,
        )

        assert win.val_forward.text() == "0.72"
        assert win.val_baseline.text() == "0.70"
        assert win.val_delta.text() == "+0.02"
        assert win.val_thresh.text() == "+0.10"
        assert "GOOD POSTURE" in win.state_label.text()
        assert "2 / 4" in win.debounce_label.text()
        assert win.gauge.current_forward == 0.72

    def test_update_frame_renders_without_crash(self, qapp):
        """update_frame handles RGB numpy array and landmarks smoothly."""
        from postured.preview_window import PostureMonitorWindow

        app = MockApp()
        win = PostureMonitorWindow(app)

        # Create dummy 64x64 frame
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        win.update_frame(frame, None)

        assert win.canvas.last_pixmap is not None

    def test_set_baseline_button_emits_signal(self, qapp):
        """Clicking 'Set Current as Upright Baseline' emits signal with current value."""
        from postured.preview_window import PostureMonitorWindow

        app = MockApp()
        win = PostureMonitorWindow(app)

        win.update_metrics(
            forward_offset=0.74,
            good_forward=0.70,
            enter_threshold=0.10,
            exit_threshold=0.05,
            is_slouching=False,
            shoulders_detected=True,
            tracking_mode="Shoulders + Ears",
            bad_frames=0,
            frame_threshold=4,
        )

        emitted_val = []
        win.upright_calibrated.connect(lambda val, *args: emitted_val.append((val, *args)))

        win.btn_set_baseline.click()
        assert len(emitted_val) == 1
        assert abs(emitted_val[0][0] - 0.74) < 0.001
        assert "Baseline set to 0.74" in win.feedback_label.text()

    def test_preview_toggle_on_show_and_close(self, qapp):
        """Showing and closing window toggles preview mode on pose_detector."""
        from postured.preview_window import PostureMonitorWindow

        app = MockApp()
        win = PostureMonitorWindow(app)

        win.show()
        app.pose_detector.set_preview_enabled.assert_called_with(True)

        win.close()
        app.pose_detector.set_preview_enabled.assert_called_with(False)

    def test_side_view_metrics_update(self, qapp):
        """update_metrics in side view displays CVA angle and plumb offset."""
        from postured.preview_window import PostureMonitorWindow

        app = MockApp()
        win = PostureMonitorWindow(app)

        win.update_metrics(
            forward_offset=0.0,
            good_forward=0.0,
            enter_threshold=0.08,
            exit_threshold=0.04,
            is_slouching=False,
            shoulders_detected=True,
            tracking_mode="Side Profile (Right, Facing Left)",
            bad_frames=0,
            frame_threshold=4,
            view_mode="side",
            side_forward=0.02,
            good_side_forward=0.0,
            cva_deg=78.5,
            good_cva=65.0,
            active_side="right",
            facing_dir="left",
        )

        assert "78.5°" in win.val_cva.text()
        assert "+0.02" in win.val_forward.text()
        assert "Side Profile" in win.val_mode.text()

    def test_view_mode_radio_emits_signal(self, qapp):
        """Toggling view mode radio emits view_mode_changed signal."""
        from postured.preview_window import PostureMonitorWindow

        app = MockApp()
        app.settings.camera_view_mode = "auto"
        win = PostureMonitorWindow(app)

        emitted = []
        win.view_mode_changed.connect(emitted.append)

        win.side_view_radio.setChecked(True)
        assert "side" in emitted


class TestPoseDetectorPreviewSignals:
    """Test preview signal emission and enable flag in PoseDetector."""

    def test_detector_set_preview_enabled(self):
        """PoseDetector delegates preview flag to worker."""
        from postured.pose_detector import PoseDetector

        detector = PoseDetector()
        mock_worker = Mock()
        detector.worker = mock_worker

        detector.set_preview_enabled(True)
        assert detector._preview_enabled is True
        mock_worker.set_preview_enabled.assert_called_once_with(True)
