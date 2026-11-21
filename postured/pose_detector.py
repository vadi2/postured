import math
import threading
import time

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

    pose_detected = pyqtSignal(
        float, float, float, bool, float, float, str, float, float, str, str
    )  # nose_y, nose_x, forward_offset, shoulders_detected, scale_ratio, neck_v_ratio, view_mode, side_forward, cva_deg, active_side, facing_dir
    preview_frame = pyqtSignal(object, object)  # (rgb_frame: np.ndarray, landmarks)
    no_detection = pyqtSignal()
    error = pyqtSignal(str)
    recovered = pyqtSignal()

    SMOOTHING_WINDOW = 5
    FRAME_INTERVAL_S = 0.25  # 4 FPS
    AWAY_FRAME_INTERVAL_S = 1.5  # Backoff polling interval when away
    AWAY_THRESHOLD = 15  # Consecutive no-detection frames before backing off
    MAX_CONSECUTIVE_FAILURES = 12  # ~3 seconds before reporting camera lost
    RECOVERY_CHECK_INTERVAL_S = 2.0
    MIN_FRAME_VARIANCE = 20.0  # detect blank frames (e.g. hardware privacy switch)
    VARIANCE_STRIDE = 16  # Subsample stride for fast variance computation
    CAMERA_WIDTH = 640
    CAMERA_HEIGHT = 480
    MIN_CONFIDENCE = 0.5

    def __init__(
        self, landmarker: PoseLandmarker, camera_index: int, debug: bool = False
    ):
        super().__init__()
        self.landmarker = landmarker
        self.camera_index = camera_index
        self.debug = debug
        self.enable_preview = False
        self.camera_view_mode = "auto"  # "auto", "front", "side"
        self._stop_event = threading.Event()
        self.nose_y_history: deque[float] = deque(maxlen=self.SMOOTHING_WINDOW)
        self.nose_x_history: deque[float] = deque(maxlen=self.SMOOTHING_WINDOW)
        self.forward_history: deque[float] = deque(maxlen=self.SMOOTHING_WINDOW)
        self.scale_history: deque[float] = deque(maxlen=self.SMOOTHING_WINDOW)
        self.neck_v_history: deque[float] = deque(maxlen=self.SMOOTHING_WINDOW)
        self.side_forward_history: deque[float] = deque(maxlen=self.SMOOTHING_WINDOW)
        self.cva_history: deque[float] = deque(maxlen=self.SMOOTHING_WINDOW)
        self.view_mode_history: deque[str] = deque(maxlen=7)

    def set_view_mode(self, mode: str):
        self.camera_view_mode = mode

    def set_preview_enabled(self, enabled: bool):
        self.enable_preview = enabled

    def _create_capture(self, camera_index: int) -> cv2.VideoCapture:
        """Create and configure camera capture with capped resolution."""
        capture = cv2.VideoCapture(camera_index)
        if capture.isOpened():
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.CAMERA_WIDTH)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.CAMERA_HEIGHT)
        return capture

    def run(self):
        """Main loop - runs in background thread."""
        capture = self._create_capture(self.camera_index)
        if not capture.isOpened():
            self.error.emit("Failed to open camera")
            return

        self._stop_event.clear()
        consecutive_failures = 0
        consecutive_no_detection = 0
        camera_lost = False

        while not self._stop_event.is_set():
            ret, frame = capture.read()
            frame_variance = (
                frame[:: self.VARIANCE_STRIDE, :: self.VARIANCE_STRIDE].std()
                if ret and frame is not None
                else 0.0
            )
            if not ret or frame_variance < self.MIN_FRAME_VARIANCE:
                consecutive_failures += 1
                if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    if not camera_lost:
                        camera_lost = True
                        if self.debug:
                            msg = (
                                f"Camera disconnected or unavailable "
                                f"(failures={consecutive_failures}/{self.MAX_CONSECUTIVE_FAILURES}, "
                                f"variance={frame_variance:.1f}/{self.MIN_FRAME_VARIANCE:.1f})"
                            )
                        else:
                            msg = "Camera disconnected or unavailable"
                        self.error.emit(msg)
                    self._stop_event.wait(self.RECOVERY_CHECK_INTERVAL_S)
                    # Reopen camera to detect hardware switch recovery
                    capture.release()
                    capture = self._create_capture(self.camera_index)
                else:
                    self._stop_event.wait(self.FRAME_INTERVAL_S)
                continue

            if camera_lost:
                camera_lost = False
                self.recovered.emit()
            consecutive_failures = 0

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            frame_timestamp = int(time.monotonic() * 1000)
            results = self.landmarker.detect_for_video(mp_image, frame_timestamp)

            if results.pose_landmarks:
                consecutive_no_detection = 0
                landmarks = results.pose_landmarks[0]
                nose = landmarks[PoseLandmark.NOSE]
                smoothed_y = self._smooth_y(nose.y)
                smoothed_x = self._smooth_x(nose.x)

                # Head-to-shoulder forward posture calculation
                left_shoulder = landmarks[PoseLandmark.LEFT_SHOULDER]
                right_shoulder = landmarks[PoseLandmark.RIGHT_SHOULDER]
                left_ear = landmarks[PoseLandmark.LEFT_EAR]
                right_ear = landmarks[PoseLandmark.RIGHT_EAR]

                ls_vis = (
                    left_shoulder.visibility
                    if left_shoulder.visibility is not None
                    else 1.0
                )
                rs_vis = (
                    right_shoulder.visibility
                    if right_shoulder.visibility is not None
                    else 1.0
                )
                le_vis = (
                    left_ear.visibility if left_ear.visibility is not None else 1.0
                )
                re_vis = (
                    right_ear.visibility if right_ear.visibility is not None else 1.0
                )

                # In side view, one shoulder may be occluded by neck/torso,
                # so detecting at least one shoulder with confidence is enough
                shoulders_detected = (ls_vis >= 0.35 and rs_vis >= 0.35) or (
                    ls_vis >= 0.5 or rs_vis >= 0.5
                )

                forward_offset = 0.0
                scale_ratio = 0.0
                neck_v_ratio = 0.0
                view_mode = "front"
                side_forward = 0.0
                cva_deg = 90.0
                active_side = "right"
                facing_dir = "left"

                if shoulders_detected:
                    shoulder_dx = abs(left_shoulder.x - right_shoulder.x)
                    shoulder_dy = abs(left_shoulder.y - right_shoulder.y)
                    shoulder_span = math.hypot(shoulder_dx, shoulder_dy)
                    if shoulder_span < 0.05:
                        shoulder_span = 0.2

                    shoulder_z_diff = abs(left_shoulder.z - right_shoulder.z)

                    # Determine view orientation
                    if self.camera_view_mode == "side":
                        view_mode = "side"
                    elif self.camera_view_mode == "front":
                        view_mode = "front"
                    else:
                        # Auto mode: side if depth disparity between shoulders is large (>0.25)
                        # or horizontal shoulder span is strongly compressed (<0.60 of 2D span)
                        # or ear visibility is strongly asymmetric (>0.35 difference)
                        raw_is_side = (
                            (shoulder_z_diff > 0.25)
                            or (shoulder_dx / max(0.01, shoulder_span) < 0.60)
                            or (abs(re_vis - le_vis) > 0.35)
                        )
                        self.view_mode_history.append("side" if raw_is_side else "front")
                        view_mode = (
                            "side"
                            if self.view_mode_history.count("side") > len(self.view_mode_history) / 2
                            else "front"
                        )

                    # 1. Front View Calculations
                    shoulder_z = (left_shoulder.z + right_shoulder.z) / 2.0
                    if le_vis >= 0.4 and re_vis >= 0.4:
                        head_z = (left_ear.z + right_ear.z) / 2.0
                        head_span = math.hypot(
                            left_ear.x - right_ear.x, left_ear.y - right_ear.y
                        )
                        head_mid_y = (left_ear.y + right_ear.y) / 2.0
                    elif le_vis >= 0.4:
                        head_z = left_ear.z
                        head_span = 0.45 * shoulder_span
                        head_mid_y = left_ear.y
                    elif re_vis >= 0.4:
                        head_z = right_ear.z
                        head_span = 0.45 * shoulder_span
                        head_mid_y = right_ear.y
                    else:
                        head_z = nose.z - 0.15 * shoulder_span
                        head_span = 0.45 * shoulder_span
                        head_mid_y = nose.y

                    raw_forward_offset = (shoulder_z - head_z) / shoulder_span
                    forward_offset = self._smooth_forward(raw_forward_offset)

                    shoulder_mid_y = (left_shoulder.y + right_shoulder.y) / 2.0
                    raw_scale_ratio = head_span / shoulder_span
                    raw_neck_v_ratio = (shoulder_mid_y - head_mid_y) / shoulder_span

                    scale_ratio = self._smooth_scale(raw_scale_ratio)
                    neck_v_ratio = self._smooth_neck_v(raw_neck_v_ratio)

                    # 2. Side View Calculations
                    # Identify active camera-facing side (closer in Z or higher visibility)
                    if (
                        right_shoulder.z > left_shoulder.z + 0.15
                        or rs_vis > ls_vis + 0.2
                    ):
                        active_side = "right"
                        active_shoulder = right_shoulder
                        active_ear = right_ear if re_vis >= 0.3 else nose
                    elif (
                        left_shoulder.z > right_shoulder.z + 0.15
                        or ls_vis > rs_vis + 0.2
                    ):
                        active_side = "left"
                        active_shoulder = left_shoulder
                        active_ear = left_ear if le_vis >= 0.3 else nose
                    else:
                        if re_vis >= le_vis:
                            active_side = "right"
                            active_shoulder = right_shoulder
                            active_ear = right_ear if re_vis >= 0.3 else nose
                        else:
                            active_side = "left"
                            active_shoulder = left_shoulder
                            active_ear = left_ear if le_vis >= 0.3 else nose

                    # Facing direction: camera on Right -> user looking at desk is facing Left
                    facing_factor = -1.0 if active_side == "right" else +1.0
                    facing_dir = "left" if facing_factor < 0 else "right"

                    neck_v = max(0.08, active_shoulder.y - active_ear.y)
                    plumb_dx = (active_ear.x - active_shoulder.x) * facing_factor
                    raw_side_forward = plumb_dx / neck_v
                    side_forward = self._smooth_side_forward(raw_side_forward)

                    raw_cva = math.degrees(
                        math.atan2(
                            active_shoulder.y - active_ear.y,
                            max(0.001, abs(active_ear.x - active_shoulder.x)),
                        )
                    )
                    cva_deg = self._smooth_cva(raw_cva)

                self.pose_detected.emit(
                    smoothed_y,
                    smoothed_x,
                    forward_offset,
                    shoulders_detected,
                    scale_ratio,
                    neck_v_ratio,
                    view_mode,
                    side_forward,
                    cva_deg,
                    active_side,
                    facing_dir,
                )
                if self.enable_preview:
                    self.preview_frame.emit(rgb_frame, landmarks)
            else:
                consecutive_no_detection += 1
                self.no_detection.emit()
                if self.enable_preview:
                    self.preview_frame.emit(rgb_frame, None)

            interval = (
                self.AWAY_FRAME_INTERVAL_S
                if consecutive_no_detection >= self.AWAY_THRESHOLD
                else self.FRAME_INTERVAL_S
            )
            self._stop_event.wait(interval)

        capture.release()

    def stop(self):
        self._stop_event.set()

    def _smooth_y(self, raw_y: float) -> float:
        self.nose_y_history.append(raw_y)
        return sum(self.nose_y_history) / len(self.nose_y_history)

    def _smooth_x(self, raw_x: float) -> float:
        self.nose_x_history.append(raw_x)
        return sum(self.nose_x_history) / len(self.nose_x_history)

    def _smooth_forward(self, raw_forward: float) -> float:
        self.forward_history.append(raw_forward)
        return sum(self.forward_history) / len(self.forward_history)

    def _smooth_scale(self, raw_scale: float) -> float:
        self.scale_history.append(raw_scale)
        return sum(self.scale_history) / len(self.scale_history)

    def _smooth_neck_v(self, raw_neck_v: float) -> float:
        self.neck_v_history.append(raw_neck_v)
        return sum(self.neck_v_history) / len(self.neck_v_history)

    def _smooth_side_forward(self, raw_side: float) -> float:
        self.side_forward_history.append(raw_side)
        return sum(self.side_forward_history) / len(self.side_forward_history)

    def _smooth_cva(self, raw_cva: float) -> float:
        self.cva_history.append(raw_cva)
        return sum(self.cva_history) / len(self.cva_history)


class PoseDetector(QObject):
    """Captures camera frames and detects pose using MediaPipe in a background thread."""

    pose_detected = pyqtSignal(
        float, float, float, bool, float, float, str, float, float, str, str
    )  # nose_y, nose_x, forward_offset, shoulders_detected, scale_ratio, neck_v_ratio, view_mode, side_forward, cva_deg, active_side, facing_dir
    preview_frame = pyqtSignal(object, object)
    no_detection = pyqtSignal()
    camera_error = pyqtSignal(str)
    camera_recovered = pyqtSignal()

    def __init__(self, parent=None, debug: bool = False):
        super().__init__(parent)
        self.thread: QThread | None = None
        self.worker: PoseWorker | None = None
        self.debug = debug
        self._preview_enabled: bool = False
        self._camera_view_mode: str = "auto"
        self._model_path = (
            Path(__file__).parent / "resources" / "pose_landmarker_lite.task"
        )
        self._landmarker: PoseLandmarker | None = None

    def _get_or_create_landmarker(self) -> PoseLandmarker:
        """Lazily create the landmarker on first use."""
        if self._landmarker is None:
            if not self._model_path.exists():
                raise FileNotFoundError(f"Model file not found: {self._model_path}")
            options = PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(self._model_path)),
                running_mode=RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=PoseWorker.MIN_CONFIDENCE,
                min_pose_presence_confidence=PoseWorker.MIN_CONFIDENCE,
                min_tracking_confidence=PoseWorker.MIN_CONFIDENCE,
            )
            self._landmarker = PoseLandmarker.create_from_options(options)
        return self._landmarker

    def start(self, camera_index: int = 0):
        if self.thread is not None:
            self.stop()

        try:
            landmarker = self._get_or_create_landmarker()
        except FileNotFoundError as e:
            self.camera_error.emit(str(e))
            return
        except Exception as e:
            self.camera_error.emit(f"Failed to load pose model: {e}")
            return

        self.thread = QThread()
        self.worker = PoseWorker(landmarker, camera_index, self.debug)
        self.worker.set_view_mode(self._camera_view_mode)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.pose_detected.connect(self.pose_detected)
        self.worker.preview_frame.connect(self.preview_frame)
        self.worker.no_detection.connect(self.no_detection)
        self.worker.error.connect(self.camera_error)
        self.worker.recovered.connect(self.camera_recovered)

        if self._preview_enabled:
            self.worker.set_preview_enabled(True)

        self.thread.start()

    def set_view_mode(self, mode: str):
        self._camera_view_mode = mode
        if self.worker:
            self.worker.set_view_mode(mode)

    def set_preview_enabled(self, enabled: bool):
        self._preview_enabled = enabled
        if self.worker:
            self.worker.set_preview_enabled(enabled)

    def stop(self):
        if self.worker:
            self.worker.stop()
        if self.thread:
            self.thread.quit()
            if not self.thread.wait(5000):
                self.thread.terminate()
            self.thread = None
            self.worker = None

    def close(self):
        """Close the landmarker (call on app shutdown)."""
        self.stop()
        if self._landmarker:
            self._landmarker.close()
            self._landmarker = None

    @staticmethod
    def available_cameras() -> list[tuple[int, str]]:
        """Return list of (index, name) for available cameras."""
        import subprocess
        import re
        import os

        cameras = []
        seen_devices = set()

        for i in range(10):
            device = f"/dev/video{i}"

            # Skip if device doesn't exist
            if not os.path.exists(device):
                continue

            sysfs_device = f"/sys/class/video4linux/video{i}/device"
            if os.path.islink(sysfs_device):
                physical_device = os.path.realpath(sysfs_device)
                if physical_device in seen_devices:
                    continue
                seen_devices.add(physical_device)

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

                name_match = re.search(r"Card type\s*:\s*(.+)", output)
                name = (
                    name_match.group(1).strip().rstrip(":")
                    if name_match
                    else f"Camera {i}"
                )

                cameras.append((i, name))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                # v4l2-ctl not available, fall back to OpenCV detection
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    name = f"Camera {i}"
                    name_path = f"/sys/class/video4linux/video{i}/name"
                    if os.path.exists(name_path):
                        try:
                            with open(name_path) as f:
                                name = f.read().strip().rstrip(":")
                        except OSError:
                            pass
                    cameras.append((i, name))
                    cap.release()

        return cameras
