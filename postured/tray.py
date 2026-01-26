from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QObject, pyqtSignal


class TrayIcon(QObject):
    """System tray icon with menu."""

    enable_toggled = pyqtSignal(bool)
    recalibrate_requested = pyqtSignal()
    sensitivity_changed = pyqtSignal(float)
    camera_changed = pyqtSignal(int)
    lock_when_away_toggled = pyqtSignal(bool)
    quit_requested = pyqtSignal()

    SENSITIVITY_OPTIONS = [
        ("Low", 0.6),
        ("Medium", 0.85),
        ("High", 1.0),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self._get_icon('good'))
        self.tray.setToolTip("Postured")

        self.menu = QMenu()
        self._build_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.show()

    def _get_icon(self, state: str) -> QIcon:
        # Use theme icons as fallback
        icons = {
            'good': 'user-available',
            'slouching': 'user-busy',
            'away': 'user-away',
        }
        return QIcon.fromTheme(icons.get(state, 'user-available'))

    def _build_menu(self):
        self.status_action = QAction("Status: Starting...", self.menu)
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)

        self.menu.addSeparator()

        self.enable_action = QAction("Enabled", self.menu)
        self.enable_action.setCheckable(True)
        self.enable_action.setChecked(True)
        self.enable_action.triggered.connect(
            lambda checked: self.enable_toggled.emit(checked)
        )
        self.menu.addAction(self.enable_action)

        recalibrate_action = QAction("Recalibrate", self.menu)
        recalibrate_action.triggered.connect(self.recalibrate_requested.emit)
        self.menu.addAction(recalibrate_action)

        self.camera_menu = self.menu.addMenu("Camera")

        sensitivity_menu = self.menu.addMenu("Sensitivity")
        self.sensitivity_actions = []
        for name, value in self.SENSITIVITY_OPTIONS:
            action = QAction(name, sensitivity_menu)
            action.setCheckable(True)
            action.setChecked(value == 0.85)  # Default: Medium
            action.triggered.connect(
                lambda checked, v=value: self._on_sensitivity_changed(v)
            )
            sensitivity_menu.addAction(action)
            self.sensitivity_actions.append((action, value))

        self.menu.addSeparator()

        self.lock_away_action = QAction("Lock when away", self.menu)
        self.lock_away_action.setCheckable(True)
        self.lock_away_action.setChecked(False)
        self.lock_away_action.triggered.connect(
            lambda checked: self.lock_when_away_toggled.emit(checked)
        )
        self.menu.addAction(self.lock_away_action)

        self.menu.addSeparator()

        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        self.menu.addAction(quit_action)

    def _on_sensitivity_changed(self, value: float):
        for action, v in self.sensitivity_actions:
            action.setChecked(v == value)
        self.sensitivity_changed.emit(value)

    def set_status(self, text: str):
        self.status_action.setText(f"Status: {text}")

    def set_enabled(self, enabled: bool):
        """Update the enabled checkbox state."""
        self.enable_action.setChecked(enabled)

    def set_posture_state(self, state: str):
        """Update icon based on posture state ('good', 'slouching', 'away')."""
        self.tray.setIcon(self._get_icon(state))

    def update_cameras(self, cameras: list[tuple[int, str]], current: int):
        self.camera_menu.clear()
        if not cameras:
            action = QAction("No cameras found", self.camera_menu)
            action.setEnabled(False)
            self.camera_menu.addAction(action)
            return
        single_camera = len(cameras) == 1
        for index, name in cameras:
            action = QAction(name, self.camera_menu)
            if single_camera:
                action.setEnabled(False)
            else:
                action.setCheckable(True)
                action.setChecked(index == current)
                action.triggered.connect(
                    lambda checked, i=index: self.camera_changed.emit(i)
                )
            self.camera_menu.addAction(action)
