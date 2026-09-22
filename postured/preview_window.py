from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
)

from postured.pose_detector import PoseLandmark

if TYPE_CHECKING:
    from postured.app import Application


class VideoSkeletonCanvas(QWidget := QLabel):
    """Renders the live camera frame with a stick-figure skeleton overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "background-color: #12121a; border-radius: 10px; border: 1px solid #2a2a3c;"
        )

        self.last_pixmap: QPixmap | None = None
        self.last_landmarks: list | None = None
        self.is_slouching: bool = False
        self.shoulders_detected: bool = False
        self.tracking_mode: str = "Searching..."
        self.view_mode: str = "front"
        self.active_side: str = "none"
        self.facing_dir: str = "none"
        self.cva_deg: float = 90.0
        self.side_forward: float = 0.0

    def update_frame(
        self,
        rgb_frame,
        landmarks,
        is_slouching: bool,
        shoulders_detected: bool,
        tracking_mode: str,
        view_mode: str = "front",
        active_side: str = "none",
        facing_dir: str = "none",
        cva_deg: float = 90.0,
        side_forward: float = 0.0,
    ):
        self.last_landmarks = landmarks
        self.is_slouching = is_slouching
        self.shoulders_detected = shoulders_detected
        self.tracking_mode = tracking_mode
        self.view_mode = view_mode
        self.active_side = active_side
        self.facing_dir = facing_dir
        self.cva_deg = cva_deg
        self.side_forward = side_forward

        if rgb_frame is not None:
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            qimg = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            self.last_pixmap = QPixmap.fromImage(qimg)

        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        if self.last_pixmap:
            scaled = self.last_pixmap.scaled(
                w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            ox = (w - scaled.width()) // 2
            oy = (h - scaled.height()) // 2
            painter.drawPixmap(ox, oy, scaled)
            canvas_w, canvas_h = scaled.width(), scaled.height()
        else:
            ox, oy = 0, 0
            canvas_w, canvas_h = w, h
            painter.setPen(QColor(150, 150, 180))
            painter.setFont(QFont("Sans", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for camera feed...")

        # Draw skeleton overlay if landmarks exist
        if self.last_landmarks:
            self._draw_skeleton(painter, ox, oy, canvas_w, canvas_h)

        # Draw status banner overlay in top-left
        self._draw_status_badge(painter, ox + 14, oy + 14)

    def _draw_status_badge(self, painter: QPainter, x: int, y: int):
        badge_w, badge_h = 160, 32
        bg_color = QColor(220, 50, 50, 200) if self.is_slouching else QColor(34, 197, 94, 200)
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(x, y, badge_w, badge_h, 6, 6)

        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Sans", 10, QFont.Weight.Bold))
        text = "● SLOUCHING" if self.is_slouching else "● GOOD POSTURE"
        painter.drawText(x, y, badge_w, badge_h, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_skeleton(self, painter: QPainter, ox: int, oy: int, cw: int, ch: int):
        lm = self.last_landmarks
        def to_pt(idx: int) -> QPointF:
            p = lm[idx]
            return QPointF(ox + p.x * cw, oy + p.y * ch)

        nose = to_pt(PoseLandmark.NOSE)
        left_shoulder = to_pt(PoseLandmark.LEFT_SHOULDER)
        right_shoulder = to_pt(PoseLandmark.RIGHT_SHOULDER)
        left_ear = to_pt(PoseLandmark.LEFT_EAR)
        right_ear = to_pt(PoseLandmark.RIGHT_EAR)

        color_primary = QColor(239, 68, 68) if self.is_slouching else QColor(56, 189, 248)
        color_accent = QColor(251, 146, 60) if self.is_slouching else QColor(52, 211, 153)

        if self.view_mode == "side":
            # Active side landmarks for sagittal profile view
            is_right = (self.active_side == "right")
            active_shoulder = right_shoulder if is_right else left_shoulder
            active_ear = right_ear if is_right else left_ear

            # Vertical plumb line passing through active shoulder (cyan dashed)
            plumb_top = QPointF(active_shoulder.x(), max(float(oy), active_shoulder.y() - 140.0))
            plumb_bottom = QPointF(active_shoulder.x(), min(float(oy + ch), active_shoulder.y() + 80.0))
            painter.setPen(QPen(QColor(6, 182, 212), 2, Qt.PenStyle.DashLine))
            painter.drawLine(plumb_top, plumb_bottom)

            # Horizontal plumb-offset bar (ear to plumb line)
            painter.setPen(QPen(QColor(245, 158, 11), 2, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(active_shoulder.x(), active_ear.y()), active_ear)

            # Cervical spine vector: shoulder to ear
            painter.setPen(QPen(color_primary, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(active_shoulder, active_ear)

            # Gaze vector: ear to nose
            painter.setPen(QPen(color_accent, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(active_ear, nose)

            # Joint dots
            painter.setBrush(QColor(255, 255, 255))
            painter.setPen(QPen(color_primary, 2))
            painter.drawEllipse(active_shoulder, 8, 8)

            painter.setPen(QPen(color_accent, 2))
            painter.drawEllipse(active_ear, 6, 6)

            painter.setBrush(QColor(245, 158, 11))
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawEllipse(nose, 6, 6)

            # CVA angle badge near shoulder
            cva_text = f"CVA: {self.cva_deg:.1f}°"
            painter.setFont(QFont("Sans", 9, QFont.Weight.Bold))
            painter.setPen(QColor(6, 182, 212))
            painter.drawText(
                int(active_shoulder.x() - 40),
                int(active_shoulder.y() + 25),
                120,
                20,
                Qt.AlignmentFlag.AlignLeft,
                cva_text,
            )
        else:
            # Front view skeleton
            if self.shoulders_detected:
                painter.setPen(QPen(color_primary, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(left_shoulder, right_shoulder)

                shoulder_mid = QPointF(
                    (left_shoulder.x() + right_shoulder.x()) / 2.0,
                    (left_shoulder.y() + right_shoulder.y()) / 2.0,
                )

                # Draw neck / spine line
                head_mid = QPointF(
                    (left_ear.x() + right_ear.x()) / 2.0,
                    (left_ear.y() + right_ear.y()) / 2.0,
                )
                painter.setPen(QPen(color_accent, 3, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(shoulder_mid, head_mid)

                # Ear-to-ear bar
                painter.setPen(QPen(color_accent, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(left_ear, right_ear)

                # Joint dots
                painter.setBrush(QColor(255, 255, 255))
                painter.setPen(QPen(color_primary, 2))
                for pt in (left_shoulder, right_shoulder):
                    painter.drawEllipse(pt, 7, 7)

                painter.setPen(QPen(color_accent, 2))
                for pt in (left_ear, right_ear):
                    painter.drawEllipse(pt, 5, 5)

            # Nose indicator
            painter.setBrush(QColor(245, 158, 11))
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawEllipse(nose, 6, 6)


class ForwardDisplacementGauge(QFrame):
    """Horizontal gauge showing Forward Head Offset, Baseline, and Slouch Threshold."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setStyleSheet(
            "background-color: #1a1a26; border-radius: 8px; border: 1px solid #2e2e44;"
        )

        self.current_forward: float = 0.55
        self.baseline: float = 0.55
        self.enter_threshold: float = 0.08
        self.exit_threshold: float = 0.04
        self.is_slouching: bool = False
        self.min_val: float = 0.10
        self.max_val: float = 1.30

    def update_metrics(
        self,
        current_forward: float,
        baseline: float,
        enter_threshold: float,
        exit_threshold: float,
        is_slouching: bool,
    ):
        self.current_forward = current_forward
        self.baseline = baseline
        self.enter_threshold = enter_threshold
        self.exit_threshold = exit_threshold
        self.is_slouching = is_slouching

        span = max(0.40, enter_threshold * 4.0)
        self.min_val = min(self.current_forward - 0.10, self.baseline - span * 0.4)
        self.max_val = max(self.current_forward + 0.10, self.baseline + span * 0.8)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        margin = 35
        track_y = h // 2
        track_w = w - 2 * margin

        def val_to_x(val: float) -> float:
            clamped = max(self.min_val, min(self.max_val, val))
            den = max(0.001, self.max_val - self.min_val)
            frac = (clamped - self.min_val) / den
            return margin + frac * track_w

        # Draw background track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(40, 40, 60))
        painter.drawRoundedRect(margin, track_y - 6, track_w, 12, 6, 6)

        # Baseline point
        bx = val_to_x(self.baseline)
        tx = val_to_x(self.baseline + self.enter_threshold)

        # Safe region (Green)
        painter.setBrush(QColor(34, 197, 94, 140))
        painter.drawRoundedRect(int(val_to_x(self.min_val)), track_y - 6, int(max(0, tx - margin)), 12, 6, 6)

        # Danger region (Red/Orange)
        if tx < margin + track_w:
            painter.setBrush(QColor(239, 68, 68, 160))
            painter.drawRoundedRect(int(tx), track_y - 6, int(margin + track_w - tx), 12, 6, 6)

        # Baseline marker (Blue line)
        painter.setPen(QPen(QColor(56, 189, 248), 3, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(bx, track_y - 18), QPointF(bx, track_y + 18))

        # Threshold trigger marker (Red line)
        painter.setPen(QPen(QColor(239, 68, 68), 3))
        painter.drawLine(QPointF(tx, track_y - 18), QPointF(tx, track_y + 18))

        # Current needle
        cx = val_to_x(self.current_forward)
        needle_color = QColor(239, 68, 68) if self.is_slouching else QColor(255, 255, 255)
        painter.setBrush(needle_color)
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        painter.drawEllipse(QPointF(cx, track_y), 9, 9)

        # Text labels below
        painter.setFont(QFont("Sans", 9))
        painter.setPen(QColor(56, 189, 248))
        painter.drawText(int(bx - 40), track_y - 22, 80, 16, Qt.AlignmentFlag.AlignCenter, f"Base {self.baseline:.2f}")

        painter.setPen(QColor(239, 68, 68))
        thresh_val = self.baseline + self.enter_threshold
        painter.drawText(int(tx - 40), track_y + 20, 80, 16, Qt.AlignmentFlag.AlignCenter, f"Slouch {thresh_val:.2f}")

        painter.setPen(QColor(255, 255, 255))
        painter.drawText(int(cx - 40), track_y + 20 if cx < tx else track_y - 22, 80, 16, Qt.AlignmentFlag.AlignCenter, f"You {self.current_forward:.2f}")


class PostureMonitorWindow(QDialog):
    """Interactive Posture Detection and Calibration Window."""

    upright_calibrated = pyqtSignal(float, float, float, float, float)
    sensitivity_changed = pyqtSignal(float)
    profile_switched = pyqtSignal(str)
    view_mode_changed = pyqtSignal(str)

    def __init__(self, app: "Application"):
        super().__init__()
        self.app = app
        self.setWindowTitle("postured - Live Posture Monitor & Detection Tuning")
        self.resize(960, 680)
        self.setStyleSheet("""
            QDialog {
                background-color: #0e0e16;
                color: #e2e8f0;
            }
            QLabel {
                color: #cbd5e1;
            }
            QGroupBox {
                border: 1px solid #27273a;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 14px;
                font-weight: bold;
                color: #94a3b8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #27273a;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #3b82f6;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            QRadioButton {
                color: #e2e8f0;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
            }
        """)

        self.canvas = VideoSkeletonCanvas(self)
        self.gauge = ForwardDisplacementGauge(self)
        self._init_ui()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # Left Column: Video & Gauge
        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        left_col.addWidget(self.canvas, stretch=1)

        gauge_group = QGroupBox("Live Forward Head Displacement")
        gauge_layout = QVBoxLayout(gauge_group)
        gauge_layout.addWidget(self.gauge)
        left_col.addWidget(gauge_group)

        main_layout.addLayout(left_col, stretch=6)

        # Right Column: Detection Logic & Controls
        right_col = QVBoxLayout()
        right_col.setSpacing(14)

        # Status Summary Card
        status_group = QGroupBox("Detection Status")
        status_layout = QVBoxLayout(status_group)

        self.state_label = QLabel("State: GOOD")
        self.state_label.setFont(QFont("Sans", 13, QFont.Weight.Bold))
        self.state_label.setStyleSheet("color: #22c55e;")
        status_layout.addWidget(self.state_label)

        self.debounce_label = QLabel("Debounce: 0 / 4 frames")
        self.debounce_label.setStyleSheet("color: #94a3b8;")
        status_layout.addWidget(self.debounce_label)

        right_col.addWidget(status_group)

        # Camera Placement Card
        view_group = QGroupBox("Camera Placement & View Mode")
        view_layout = QHBoxLayout(view_group)
        self.auto_view_radio = QRadioButton("Auto-Detect")
        self.front_view_radio = QRadioButton("Front View")
        self.side_view_radio = QRadioButton("Side Profile")

        self.view_btn_group = QButtonGroup(self)
        self.view_btn_group.addButton(self.auto_view_radio)
        self.view_btn_group.addButton(self.front_view_radio)
        self.view_btn_group.addButton(self.side_view_radio)

        current_view = self.app.settings.camera_view_mode
        self.auto_view_radio.setChecked(current_view == "auto")
        self.front_view_radio.setChecked(current_view == "front")
        self.side_view_radio.setChecked(current_view == "side")

        self.auto_view_radio.toggled.connect(lambda ch: self._on_view_mode_toggled("auto", ch))
        self.front_view_radio.toggled.connect(lambda ch: self._on_view_mode_toggled("front", ch))
        self.side_view_radio.toggled.connect(lambda ch: self._on_view_mode_toggled("side", ch))

        view_layout.addWidget(self.auto_view_radio)
        view_layout.addWidget(self.front_view_radio)
        view_layout.addWidget(self.side_view_radio)
        right_col.addWidget(view_group)

        # Numerical Breakdown Card
        metrics_group = QGroupBox("Live Metrics Breakdown")
        metrics_layout = QGridLayout(metrics_group)
        metrics_layout.setColumnStretch(1, 1)

        metrics_layout.addWidget(QLabel("Camera / Tracking Mode:"), 0, 0)
        self.val_mode = QLabel("Searching...")
        self.val_mode.setFont(QFont("Sans", 9, QFont.Weight.Bold))
        metrics_layout.addWidget(self.val_mode, 0, 1, Qt.AlignmentFlag.AlignRight)

        metrics_layout.addWidget(QLabel("Displacement / Plumb (F):"), 1, 0)
        self.val_forward = QLabel("0.55")
        self.val_forward.setFont(QFont("Monospace", 10, QFont.Weight.Bold))
        metrics_layout.addWidget(self.val_forward, 1, 1, Qt.AlignmentFlag.AlignRight)

        metrics_layout.addWidget(QLabel("Upright Baseline (F₀):"), 2, 0)
        self.val_baseline = QLabel("0.55")
        self.val_baseline.setFont(QFont("Monospace", 10, QFont.Weight.Bold))
        self.val_baseline.setStyleSheet("color: #38bdf8;")
        metrics_layout.addWidget(self.val_baseline, 2, 1, Qt.AlignmentFlag.AlignRight)

        metrics_layout.addWidget(QLabel("CVA Angle:"), 3, 0)
        self.val_cva = QLabel("—")
        self.val_cva.setFont(QFont("Monospace", 10, QFont.Weight.Bold))
        metrics_layout.addWidget(self.val_cva, 3, 1, Qt.AlignmentFlag.AlignRight)

        metrics_layout.addWidget(QLabel("Head Scale Ratio (S):"), 4, 0)
        self.val_scale = QLabel("0.40")
        self.val_scale.setFont(QFont("Monospace", 10, QFont.Weight.Bold))
        metrics_layout.addWidget(self.val_scale, 4, 1, Qt.AlignmentFlag.AlignRight)

        metrics_layout.addWidget(QLabel("Neck Height Ratio (V):"), 5, 0)
        self.val_neck = QLabel("0.32")
        self.val_neck.setFont(QFont("Monospace", 10, QFont.Weight.Bold))
        metrics_layout.addWidget(self.val_neck, 5, 1, Qt.AlignmentFlag.AlignRight)

        metrics_layout.addWidget(QLabel("Slouch Delta (Δ):"), 6, 0)
        self.val_delta = QLabel("+0.00")
        self.val_delta.setFont(QFont("Monospace", 10, QFont.Weight.Bold))
        metrics_layout.addWidget(self.val_delta, 6, 1, Qt.AlignmentFlag.AlignRight)

        metrics_layout.addWidget(QLabel("Trigger Threshold:"), 7, 0)
        self.val_thresh = QLabel("+0.08")
        self.val_thresh.setFont(QFont("Monospace", 10, QFont.Weight.Bold))
        self.val_thresh.setStyleSheet("color: #ef4444;")
        metrics_layout.addWidget(self.val_thresh, 7, 1, Qt.AlignmentFlag.AlignRight)

        right_col.addWidget(metrics_group)

        # One-Click Calibration Card
        calib_group = QGroupBox("Quick Calibration")
        calib_layout = QVBoxLayout(calib_group)
        calib_desc = QLabel("Sit upright in your normal desk posture, then click:")
        calib_desc.setWordWrap(True)
        calib_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        calib_layout.addWidget(calib_desc)

        self.btn_set_baseline = QPushButton("🎯 Set Current as Upright Baseline")
        self.btn_set_baseline.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                font-size: 12px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        self.btn_set_baseline.clicked.connect(self._on_set_baseline_clicked)
        calib_layout.addWidget(self.btn_set_baseline)

        self.feedback_label = QLabel("")
        self.feedback_label.setStyleSheet("color: #34d399; font-weight: bold; font-size: 11px;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        calib_layout.addWidget(self.feedback_label)

        right_col.addWidget(calib_group)

        # Sensitivity Slider
        sens_group = QGroupBox("Slouch Sensitivity")
        sens_layout = QVBoxLayout(sens_group)

        self.sens_slider = QSlider(Qt.Orientation.Horizontal)
        self.sens_slider.setRange(10, 100)
        initial_sens = int(self.app.settings.sensitivity * 100)
        self.sens_slider.setValue(initial_sens)
        self.sens_slider.valueChanged.connect(self._on_slider_changed)
        sens_layout.addWidget(self.sens_slider)

        self.sens_val_label = QLabel(
            f"Sensitivity: {initial_sens / 100:.2f} (Relaxed ⟵ ⟶ Strict)"
        )
        self.sens_val_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        sens_layout.addWidget(self.sens_val_label)

        right_col.addWidget(sens_group)

        # Profile Switcher
        prof_group = QGroupBox("Desk Profile")
        prof_layout = QHBoxLayout(prof_group)
        self.sitting_radio = QRadioButton("Sitting")
        self.standing_radio = QRadioButton("Standing")

        self.prof_btn_group = QButtonGroup(self)
        self.prof_btn_group.addButton(self.sitting_radio)
        self.prof_btn_group.addButton(self.standing_radio)

        current_prof = self.app.settings.current_profile
        self.sitting_radio.setChecked(current_prof == "sitting")
        self.standing_radio.setChecked(current_prof == "standing")

        self.sitting_radio.toggled.connect(lambda ch: self._on_profile_toggled("sitting", ch))
        self.standing_radio.toggled.connect(lambda ch: self._on_profile_toggled("standing", ch))

        prof_layout.addWidget(self.sitting_radio)
        prof_layout.addWidget(self.standing_radio)
        right_col.addWidget(prof_group)

        right_col.addStretch(1)

        # Close / Done Button
        btn_close = QPushButton("Done (Close Window)")
        btn_close.setStyleSheet("background-color: #334155; padding: 10px;")
        btn_close.clicked.connect(self.close)
        right_col.addWidget(btn_close)

        main_layout.addLayout(right_col, stretch=4)

    @pyqtSlot(object, object)
    def update_frame(self, rgb_frame, landmarks):
        tracking_mode = self.val_mode.text()
        self.canvas.update_frame(
            rgb_frame,
            landmarks,
            self.app.is_slouching,
            bool(landmarks and len(landmarks) >= 13),
            tracking_mode,
            view_mode=getattr(self, "_last_view_mode", "front"),
            active_side=getattr(self, "_last_active_side", "none"),
            facing_dir=getattr(self, "_last_facing_dir", "none"),
            cva_deg=getattr(self, "_last_cva", 90.0),
            side_forward=getattr(self, "_last_side", 0.0),
        )

    def update_metrics(
        self,
        forward_offset: float,
        good_forward: float,
        enter_threshold: float,
        exit_threshold: float,
        is_slouching: bool,
        shoulders_detected: bool,
        tracking_mode: str,
        bad_frames: int,
        frame_threshold: int,
        delta_z: float = 0.0,
        scale_ratio: float = 0.0,
        good_scale: float = 0.40,
        delta_scale: float = 0.0,
        neck_v_ratio: float = 0.0,
        good_neck: float = 0.32,
        delta_neck: float = 0.0,
        forward_slouch: float = 0.0,
        view_mode: str = "front",
        side_forward: float = 0.0,
        good_side_forward: float = 0.0,
        cva_deg: float = 90.0,
        good_cva: float = 65.0,
        active_side: str = "none",
        facing_dir: str = "none",
    ):
        self._last_forward = forward_offset
        self._last_scale = scale_ratio if scale_ratio > 0 else good_scale
        self._last_neck = neck_v_ratio if neck_v_ratio > 0 else good_neck
        self._last_side = side_forward
        self._last_cva = cva_deg
        self._last_view_mode = view_mode
        self._last_active_side = active_side
        self._last_facing_dir = facing_dir

        if view_mode == "side":
            delta = forward_slouch
            disp_forward = side_forward
            disp_baseline = good_side_forward
            self.val_forward.setText(f"{disp_forward:+.2f} (norm dx)")
            self.val_baseline.setText(f"{disp_baseline:+.2f}")
            self.val_cva.setText(f"{cva_deg:.1f}°")
            self.val_cva.setStyleSheet(
                "color: #38bdf8;" if cva_deg >= 55.0 else ("color: #ef4444;" if cva_deg < 50.0 else "color: #f59e0b;")
            )
        else:
            delta = (
                forward_slouch
                if (forward_slouch != 0.0 or delta_z != 0.0)
                else (forward_offset - good_forward)
            )
            disp_forward = forward_offset
            disp_baseline = good_forward
            self.val_forward.setText(f"{disp_forward:.2f}")
            self.val_baseline.setText(f"{disp_baseline:.2f}")
            self.val_cva.setText("—")
            self.val_cva.setStyleSheet("color: #94a3b8;")

        if scale_ratio > 0:
            self.val_scale.setText(f"{scale_ratio:.2f} ({delta_scale:+.0%})")
        else:
            self.val_scale.setText(f"{good_scale:.2f}")

        if neck_v_ratio > 0:
            self.val_neck.setText(f"{neck_v_ratio:.2f} ({delta_neck:+.0%})")
        else:
            self.val_neck.setText(f"{good_neck:.2f}")

        self.val_delta.setText(f"{delta:+.2f}")
        self.val_thresh.setText(f"+{enter_threshold:.2f}")
        self.val_mode.setText(tracking_mode)

        # Delta color styling
        if delta > enter_threshold:
            self.val_delta.setStyleSheet("color: #ef4444; font-weight: bold;")
        elif delta <= 0.0:
            self.val_delta.setStyleSheet("color: #38bdf8; font-weight: bold;")
        else:
            self.val_delta.setStyleSheet("color: #22c55e; font-weight: bold;")

        # Status & debounce labels
        if is_slouching:
            self.state_label.setText("State: SLOUCHING")
            self.state_label.setStyleSheet("color: #ef4444;")
            self.debounce_label.setText(f"Active Alert (exit threshold: +{exit_threshold:.2f})")
        else:
            self.state_label.setText("State: GOOD POSTURE")
            self.state_label.setStyleSheet("color: #22c55e;")
            self.debounce_label.setText(f"Slouch Debounce: {bad_frames} / {frame_threshold} frames")

        # Update gauge with effective forward score
        effective_forward = disp_baseline + delta
        self.gauge.update_metrics(
            effective_forward, disp_baseline, enter_threshold, exit_threshold, is_slouching
        )

    def _on_set_baseline_clicked(self):
        cur_f = getattr(self, "_last_forward", 0.55)
        cur_s = getattr(self, "_last_scale", 0.40)
        cur_n = getattr(self, "_last_neck", 0.32)
        cur_side = getattr(self, "_last_side", 0.0)
        cur_cva = getattr(self, "_last_cva", 65.0)
        self.upright_calibrated.emit(cur_f, cur_s, cur_n, cur_side, cur_cva)
        if getattr(self, "_last_view_mode", "front") == "side":
            self.feedback_label.setText(f"✓ Baseline set to {cur_side:+.2f}! (CVA: {cur_cva:.0f}°)")
        else:
            self.feedback_label.setText(f"✓ Baseline set to {cur_f:.2f}!")

    def _on_slider_changed(self, value: int):
        sens = value / 100.0
        self.sens_val_label.setText(f"Sensitivity: {sens:.2f} (Relaxed ⟵ ⟶ Strict)")
        self.sensitivity_changed.emit(sens)

    def _on_profile_toggled(self, profile: str, checked: bool):
        if checked:
            self.profile_switched.emit(profile)

    def _on_view_mode_toggled(self, mode: str, checked: bool):
        if checked:
            self.view_mode_changed.emit(mode)

    def showEvent(self, event):
        super().showEvent(event)
        self.app.pose_detector.set_preview_enabled(True)

    def closeEvent(self, event):
        self.app.pose_detector.set_preview_enabled(False)
        super().closeEvent(event)
