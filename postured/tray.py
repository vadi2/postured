from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QAction, QDesktopServices
from PyQt6.QtCore import QObject, pyqtSignal, QUrl

from .settings import get_monitor_id


class TrayIcon(QObject):
    """System tray icon with menu."""

    enable_toggled = pyqtSignal(bool)
    recalibrate_requested = pyqtSignal()  # Recalibrate all monitors
    recalibrate_monitor_requested = pyqtSignal(
        str
    )  # Recalibrate specific monitor by ID
    sensitivity_changed = pyqtSignal(float)
    camera_changed = pyqtSignal(int)
    lock_when_away_toggled = pyqtSignal(bool)
    notification_mode_changed = pyqtSignal(str)  # "dim_screen" or "led_blink"
    quit_requested = pyqtSignal()

    SENSITIVITY_OPTIONS = [
        ("Low", 0.6),
        ("Medium", 0.85),
        ("High", 1.0),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self._get_icon("good"))
        self.tray.setToolTip("Postured")

        self.menu = QMenu()
        self._build_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.show()

    def _get_icon(self, state: str) -> QIcon:
        # Use theme icons as fallback
        icons = {
            "good": "user-available",
            "slouching": "user-busy",
            "away": "user-away",
        }
        return QIcon.fromTheme(icons.get(state, "user-available"))

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

        # Recalibrate - simple action for single monitor, submenu for multiple
        self.recalibrate_action = QAction("Recalibrate", self.menu)
        self.recalibrate_action.triggered.connect(self.recalibrate_requested.emit)
        self.menu.addAction(self.recalibrate_action)

        self.recalibrate_menu = self.menu.addMenu("Recalibrate")
        self._calibrated_monitors: set[str] = set()
        self._rebuild_recalibrate_menu()

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

        # Notification mode options (mutually exclusive)
        self.dim_screen_action = QAction("Dim screen when slouching", self.menu)
        self.dim_screen_action.setCheckable(True)
        self.dim_screen_action.setChecked(True)
        self.dim_screen_action.triggered.connect(
            lambda: self._on_notification_mode_changed("dim_screen")
        )
        self.menu.addAction(self.dim_screen_action)

        self.led_blink_action = QAction("Blink LED when slouching", self.menu)
        self.led_blink_action.setCheckable(True)
        self.led_blink_action.setChecked(False)
        self.led_blink_action.triggered.connect(
            lambda: self._on_notification_mode_changed("led_blink")
        )
        self.menu.addAction(self.led_blink_action)

        # GNOME extension install prompt (hidden by default)
        self.install_extension_action = QAction(
            "Better overlay (install extension)...", self.menu
        )
        self.install_extension_action.triggered.connect(self._open_extension_page)
        self.install_extension_action.setVisible(False)
        self.menu.addAction(self.install_extension_action)

        self.menu.addSeparator()

        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        self.menu.addAction(quit_action)

    def _on_sensitivity_changed(self, value: float):
        for action, v in self.sensitivity_actions:
            action.setChecked(v == value)
        self.sensitivity_changed.emit(value)

    def _rebuild_recalibrate_menu(self):
        """Rebuild the recalibrate UI based on monitor count."""
        app = QApplication.instance()
        screens = app.screens() if app else []

        if len(screens) <= 1:
            # Single monitor: show simple action, hide submenu
            self.recalibrate_action.setVisible(True)
            self.recalibrate_menu.menuAction().setVisible(False)
        else:
            # Multiple monitors: hide simple action, show submenu
            self.recalibrate_action.setVisible(False)
            self.recalibrate_menu.menuAction().setVisible(True)

            self.recalibrate_menu.clear()

            # "All Monitors" option
            all_action = QAction("All Monitors", self.recalibrate_menu)
            all_action.triggered.connect(self.recalibrate_requested.emit)
            self.recalibrate_menu.addAction(all_action)

            self.recalibrate_menu.addSeparator()

            # Individual monitor options
            for i, screen in enumerate(screens):
                monitor_id = get_monitor_id(screen)
                is_calibrated = monitor_id in self._calibrated_monitors

                # Format: "HDMI-1 (Primary) [✓]" or "DP-2 [ ]"
                label = screen.name()
                if i == 0:
                    label += " (Primary)"
                label += " [✓]" if is_calibrated else " [ ]"

                action = QAction(label, self.recalibrate_menu)
                action.triggered.connect(
                    lambda checked,
                    mid=monitor_id: self.recalibrate_monitor_requested.emit(mid)
                )
                self.recalibrate_menu.addAction(action)

    def update_monitor_calibrations(self, calibrated_monitor_ids: set[str]):
        """Update which monitors are calibrated and rebuild menu."""
        self._calibrated_monitors = calibrated_monitor_ids
        self._rebuild_recalibrate_menu()

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

    def show_gnome_extension_prompt(self, show: bool = True):
        """Show or hide the GNOME extension install prompt."""
        self.install_extension_action.setVisible(show)

    def _open_extension_page(self):
        """Open the GNOME extensions page for postured-overlay."""
        QDesktopServices.openUrl(
            QUrl("https://extensions.gnome.org/extension/8010/postured-overlay/")
        )

    def _on_notification_mode_changed(self, mode: str):
        """Handle notification mode radio button selection."""
        self.dim_screen_action.setChecked(mode == "dim_screen")
        self.led_blink_action.setChecked(mode == "led_blink")
        self.notification_mode_changed.emit(mode)

    def set_lock_when_away(self, enabled: bool):
        """Update the lock when away checkbox state."""
        self.lock_away_action.setChecked(enabled)

    def set_sensitivity(self, value: float):
        """Update the sensitivity radio button selection."""
        for action, v in self.sensitivity_actions:
            action.setChecked(v == value)

    def set_notification_mode(self, mode: str):
        """Update notification mode checkbox states."""
        self.dim_screen_action.setChecked(mode == "dim_screen")
        self.led_blink_action.setChecked(mode == "led_blink")
