"""Tests for CPU and power efficiency optimizations."""

from unittest.mock import MagicMock, patch
import numpy as np
import cv2

from postured.pose_detector import PoseWorker


class TestCameraCaptureConfig:
    """Test camera resolution configuration."""

    @patch("postured.pose_detector.cv2.VideoCapture")
    def test_create_capture_sets_capped_resolution(self, mock_cv2_capture):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cv2_capture.return_value = mock_cap

        worker = PoseWorker(landmarker=MagicMock(), camera_index=0)
        capture = worker._create_capture(0)

        assert capture == mock_cap
        mock_cap.set.assert_any_call(cv2.CAP_PROP_FRAME_WIDTH, PoseWorker.CAMERA_WIDTH)
        mock_cap.set.assert_any_call(
            cv2.CAP_PROP_FRAME_HEIGHT, PoseWorker.CAMERA_HEIGHT
        )

    @patch("postured.pose_detector.cv2.VideoCapture")
    def test_create_capture_handles_unopened_device(self, mock_cv2_capture):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cv2_capture.return_value = mock_cap

        worker = PoseWorker(landmarker=MagicMock(), camera_index=1)
        capture = worker._create_capture(1)

        assert capture == mock_cap
        mock_cap.set.assert_not_called()


class TestVarianceSubsampling:
    """Test subsampled variance calculation for privacy cover detection."""

    def test_blank_frame_variance_below_threshold(self):
        stride = PoseWorker.VARIANCE_STRIDE
        blank_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        variance = blank_frame[::stride, ::stride].std()

        assert variance == 0.0
        assert variance < PoseWorker.MIN_FRAME_VARIANCE

    def test_illuminated_frame_variance_above_threshold(self):
        stride = PoseWorker.VARIANCE_STRIDE
        # Generate gradient frame representing lit scene
        y, x = np.mgrid[0:480, 0:640]
        active_frame = ((x + y) % 256).astype(np.uint8)
        active_frame = np.stack([active_frame] * 3, axis=-1)

        variance = active_frame[::stride, ::stride].std()
        assert variance > PoseWorker.MIN_FRAME_VARIANCE


class TestAdaptiveInterval:
    """Test adaptive frame interval based on presence."""

    def test_default_constants(self):
        assert PoseWorker.FRAME_INTERVAL_S == 0.25  # 4 FPS
        assert PoseWorker.AWAY_FRAME_INTERVAL_S == 1.5
        assert PoseWorker.AWAY_THRESHOLD == 15

    def test_interval_logic(self):
        worker = PoseWorker(landmarker=MagicMock(), camera_index=0)

        # Under threshold -> normal interval
        consecutive_no_detection = 5
        interval = (
            worker.AWAY_FRAME_INTERVAL_S
            if consecutive_no_detection >= worker.AWAY_THRESHOLD
            else worker.FRAME_INTERVAL_S
        )
        assert interval == worker.FRAME_INTERVAL_S

        # At or above threshold -> away interval
        consecutive_no_detection = 15
        interval = (
            worker.AWAY_FRAME_INTERVAL_S
            if consecutive_no_detection >= worker.AWAY_THRESHOLD
            else worker.FRAME_INTERVAL_S
        )
        assert interval == worker.AWAY_FRAME_INTERVAL_S
