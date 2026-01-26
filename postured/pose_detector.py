import threading

import cv2
import mediapipe as mp
from collections import deque
from pathlib import Path
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    PoseLandmarker,
    PoseLandmarkerOptions,
    PoseLandmark,
    RunningMode,
)


class PoseWorker(QObject):
    """Worker that runs pose detection in a background thread."""

    pose_detected = pyqtSignal(float)  # nose_y
    no_detection = pyqtSignal()
    error = pyqtSignal(str)

    SMOOTHING_WINDOW = 5
    FRAME_INTERVAL_S = 0.1  # 10 FPS
    MAX_CONSECUTIVE_FAILURES = 30  # ~3 seconds before reporting camera lost
    RECOVERY_CHECK_INTERVAL_S = 5.0

    def __init__(self, model_path: Path, camera_index: int):
        super().__init__()
        self.model_path = model_path
        self.camera_index = camera_index
        self._stop_event = threading.Event()
        self.nose_history: deque[float] = deque(maxlen=self.SMOOTHING_WINDOW)

    def run(self):
        """Main loop - runs in background thread."""
        if not self.model_path.exists():
            self.error.emit(f"Model file not found: {self.model_path}")
            return

        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        landmarker = PoseLandmarker.create_from_options(options)

        capture = cv2.VideoCapture(self.camera_index)
        if not capture.isOpened():
            self.error.emit("Failed to open camera")
            landmarker.close()
            return

        self._stop_event.clear()
        frame_timestamp = 0
        consecutive_failures = 0
        camera_lost = False

        while not self._stop_event.is_set():
            ret, frame = capture.read()
            if not ret:
                consecutive_failures += 1
                if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    if not camera_lost:
                        camera_lost = True
                        self.error.emit("Camera disconnected or unavailable")
                    self._stop_event.wait(self.RECOVERY_CHECK_INTERVAL_S)
                else:
                    self._stop_event.wait(self.FRAME_INTERVAL_S)
                continue

            if camera_lost:
                camera_lost = False
            consecutive_failures = 0

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            frame_timestamp += int(self.FRAME_INTERVAL_S * 1000)
            results = landmarker.detect_for_video(mp_image, frame_timestamp)

            if results.pose_landmarks:
                landmarks = results.pose_landmarks[0]
                nose = landmarks[PoseLandmark.NOSE]
                smoothed_y = self._smooth(nose.y)
                self.pose_detected.emit(smoothed_y)
            else:
                self.no_detection.emit()

            self._stop_event.wait(self.FRAME_INTERVAL_S)

        capture.release()
        landmarker.close()

    def stop(self):
        self._stop_event.set()

    def _smooth(self, raw_y: float) -> float:
        self.nose_history.append(raw_y)
        return sum(self.nose_history) / len(self.nose_history)


class PoseDetector(QObject):
    """Captures camera frames and detects pose using MediaPipe in a background thread."""

    pose_detected = pyqtSignal(float)  # nose_y: 0.0 (top) to 1.0 (bottom)
    no_detection = pyqtSignal()
    camera_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread: QThread | None = None
        self.worker: PoseWorker | None = None
        self.model_path = Path(__file__).parent.parent / "resources" / "pose_landmarker_lite.task"

    def start(self, camera_index: int = 0):
        if self.thread is not None:
            self.stop()

        self.thread = QThread()
        self.worker = PoseWorker(self.model_path, camera_index)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.pose_detected.connect(self.pose_detected)
        self.worker.no_detection.connect(self.no_detection)
        self.worker.error.connect(self.camera_error)

        self.thread.start()

    def stop(self):
        if self.worker:
            self.worker.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
            self.worker = None

    @staticmethod
    def available_cameras() -> list[tuple[int, str]]:
        """Return list of (index, name) for available cameras."""
        import subprocess
        import re

        cameras = []
        for i in range(10):
            device = f"/dev/video{i}"
            try:
                result = subprocess.run(
                    ["v4l2-ctl", "-d", device, "--all"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode != 0:
                    continue

                output = result.stdout
                # Check if device has video capture capability (not just metadata)
                device_caps_match = re.search(
                    r"Device Caps\s*:.*?\n((?:\t\t.*\n)*)", output
                )
                if not device_caps_match:
                    continue
                device_caps = device_caps_match.group(1)
                if "Video Capture" not in device_caps:
                    continue

                # Extract camera name
                name_match = re.search(r"Card type\s*:\s*(.+)", output)
                name = name_match.group(1).strip().rstrip(":") if name_match else f"Camera {i}"

                cameras.append((i, name))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                # v4l2-ctl not available, fall back to OpenCV detection
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    cameras.append((i, f"Camera {i}"))
                    cap.release()

        return cameras
