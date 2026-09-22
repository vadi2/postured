from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


class TrayIcon(QObject):
    """System tray icon with menu."""

    enable_toggled = pyqtSignal(bool)
    camera_changed = pyqtSignal(int)
    lock_when_away_toggled = pyqtSignal(bool)
    notification_mode_changed = pyqtSignal(str)  # "dim_screen" or "led_blink"
    profile_changed = pyqtSignal(str)  # "sitting" or "standing"
    preview_requested = pyqtSignal()
    quit_requested = pyqtSignal()

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

        self.preview_action = QAction("📷 Posture Monitor & Tuning...", self.menu)
        self.preview_action.triggered.connect(self.preview_requested.emit)
        self.menu.addAction(self.preview_action)

        self.menu.addSeparator()

        self.enable_action = QAction("Enabled", self.menu)
        self.enable_action.setCheckable(True)
        self.enable_action.setChecked(True)
        self.enable_action.triggered.connect(
            lambda checked: self.enable_toggled.emit(checked)
        )
        self.menu.addAction(self.enable_action)

        # Profile menu (Sitting / Standing)
        self.profile_menu = self.menu.addMenu("Profile")
        self.sitting_action = QAction("Sitting", self.profile_menu)
        self.sitting_action.setCheckable(True)
        self.sitting_action.setChecked(True)
        self.sitting_action.triggered.connect(
            lambda: self._on_profile_selected("sitting")
        )
        self.profile_menu.addAction(self.sitting_action)

        self.standing_action = QAction("Standing", self.profile_menu)
        self.standing_action.setCheckable(True)
        self.standing_action.setChecked(False)
        self.standing_action.triggered.connect(
            lambda: self._on_profile_selected("standing")
        )
        self.profile_menu.addAction(self.standing_action)

        self.menu.addSeparator()

        self.camera_menu = self.menu.addMenu("Camera")

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

    def update_monitor_calibrations(self, calibrated_monitor_ids: set[str]):
        """Retained for backwards compatibility."""

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
        """Retained for backwards compatibility."""

    def set_notification_mode(self, mode: str):
        """Update notification mode checkbox states."""
        self.dim_screen_action.setChecked(mode == "dim_screen")
        self.led_blink_action.setChecked(mode == "led_blink")

    def _on_profile_selected(self, profile: str):
        self.set_profile(profile)
        self.profile_changed.emit(profile)

    def set_profile(self, profile: str):
        """Update checked state of profile menu actions."""
        self.sitting_action.setChecked(profile == "sitting")
        self.standing_action.setChecked(profile == "standing")
