import cv2
import mediapipe as mp
from collections import deque
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    PoseLandmarker,
    PoseLandmarkerOptions,
    PoseLandmark,
    RunningMode,
)


class PoseDetector(QObject):
    """Captures camera frames and detects pose using MediaPipe."""

    pose_detected = pyqtSignal(float)  # nose_y: 0.0 (top) to 1.0 (bottom)
    no_detection = pyqtSignal()
    camera_error = pyqtSignal(str)

    SMOOTHING_WINDOW = 5
    FRAME_INTERVAL_MS = 100  # 10 FPS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.landmarker = None
        self.capture = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._process_frame)
        self.nose_history: deque[float] = deque(maxlen=self.SMOOTHING_WINDOW)
        self.frame_timestamp = 0

        # Find model file
        self.model_path = Path(__file__).parent.parent / "resources" / "pose_landmarker_lite.task"

    def start(self, camera_index: int = 0):
        if not self.model_path.exists():
            self.camera_error.emit(f"Model file not found: {self.model_path}")
            return

        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.landmarker = PoseLandmarker.create_from_options(options)

        self.capture = cv2.VideoCapture(camera_index)
        if not self.capture.isOpened():
            self.camera_error.emit("Failed to open camera")
            return

        self.frame_timestamp = 0
        self.timer.start(self.FRAME_INTERVAL_MS)

    def stop(self):
        self.timer.stop()
        if self.capture:
            self.capture.release()
            self.capture = None
        if self.landmarker:
            self.landmarker.close()
            self.landmarker = None

    def _process_frame(self):
        if not self.capture or not self.landmarker:
            return
        ret, frame = self.capture.read()
        if not ret:
            return

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        self.frame_timestamp += self.FRAME_INTERVAL_MS
        results = self.landmarker.detect_for_video(mp_image, self.frame_timestamp)

        if results.pose_landmarks and len(results.pose_landmarks) > 0:
            landmarks = results.pose_landmarks[0]
            nose = landmarks[PoseLandmark.NOSE]
            smoothed_y = self._smooth(nose.y)
            self.pose_detected.emit(smoothed_y)
        else:
            self.no_detection.emit()

    def _smooth(self, raw_y: float) -> float:
        self.nose_history.append(raw_y)
        return sum(self.nose_history) / len(self.nose_history)

    @staticmethod
    def available_cameras() -> list[tuple[int, str]]:
        """Return list of (index, name) for available cameras."""
        cameras = []
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cameras.append((i, f"Camera {i}"))
                cap.release()
        return cameras
