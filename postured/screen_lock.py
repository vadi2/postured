"""Screen lock detection for auto-pause functionality."""

import logging
import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

logger = logging.getLogger(__name__)


class ScreenLockMonitor(QObject):
    """Monitors screen lock state and emits signals on changes.

    Tries multiple D-Bus interfaces in order:
    1. org.gnome.ScreenSaver (GNOME)
    2. org.kde.screensaver (KDE)
    3. org.freedesktop.ScreenSaver (generic)
    4. org.freedesktop.login1 session (fallback)
    """

    screen_locked = pyqtSignal(bool)  # True = locked, False = unlocked

    # D-Bus services to try, in order of preference
    SCREENSAVER_SERVICES = [
        ("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver"),
        ("org.kde.screensaver", "/org/kde/ScreenSaver", "org.kde.screensaver"),
        (
            "org.freedesktop.ScreenSaver",
            "/org/freedesktop/ScreenSaver",
            "org.freedesktop.ScreenSaver",
        ),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False
        self._connection_type: str | None = None
        self._connect_to_signals()

    def _connect_to_signals(self):
        """Try connecting to screen lock signals."""
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            logger.warning("Could not connect to session D-Bus for screen lock")
            return

        # Try screensaver services first
        for service, path, interface in self.SCREENSAVER_SERVICES:
            if self._try_screensaver_connection(bus, service, path, interface):
                return

        # Fall back to logind
        self._try_logind_connection()

    def _try_screensaver_connection(
        self, bus: QDBusConnection, service: str, path: str, interface: str
    ) -> bool:
        """Try connecting to a screensaver D-Bus service."""
        # Check if service exists by trying to get its interface
        iface = QDBusInterface(service, path, interface, bus)
        if not iface.isValid():
            return False

        # Connect to ActiveChanged signal
        success = bus.connect(
            service,
            path,
            interface,
            "ActiveChanged",
            self._on_screensaver_active_changed,
        )

        if success:
            self._connected = True
            self._connection_type = service
            logger.info(f"Connected to screen lock signals via {service}")
            return True

        return False

    def _try_logind_connection(self):
        """Try connecting to logind session signals."""
        bus = QDBusConnection.systemBus()
        if not bus.isConnected():
            logger.warning("Could not connect to system D-Bus for logind")
            return

        # Get session path for current session
        session_path = self._get_session_path(bus)
        if not session_path:
            logger.warning("Could not determine logind session path")
            return

        # Connect to Lock and Unlock signals
        lock_success = bus.connect(
            "org.freedesktop.login1",
            session_path,
            "org.freedesktop.login1.Session",
            "Lock",
            self._on_logind_lock,
        )

        unlock_success = bus.connect(
            "org.freedesktop.login1",
            session_path,
            "org.freedesktop.login1.Session",
            "Unlock",
            self._on_logind_unlock,
        )

        if lock_success and unlock_success:
            self._connected = True
            self._connection_type = "logind"
            logger.info(f"Connected to screen lock signals via logind ({session_path})")
        else:
            logger.warning("Failed to connect to logind session signals")

    def _get_session_path(self, bus: QDBusConnection) -> str | None:
        """Get the D-Bus path for the current session."""
        # Try XDG_SESSION_ID first
        session_id = os.environ.get("XDG_SESSION_ID")
        if session_id:
            return f"/org/freedesktop/login1/session/{session_id}"

        # Fall back to auto
        return "/org/freedesktop/login1/session/auto"

    def _on_screensaver_active_changed(self, message: QDBusMessage):
        """Handle ActiveChanged signal from screensaver."""
        args = message.arguments()
        if args:
            is_locked = bool(args[0])
            logger.debug(f"Screen lock state changed: {is_locked}")
            self.screen_locked.emit(is_locked)

    def _on_logind_lock(self):
        """Handle Lock signal from logind."""
        logger.debug("Screen locked (logind)")
        self.screen_locked.emit(True)

    def _on_logind_unlock(self):
        """Handle Unlock signal from logind."""
        logger.debug("Screen unlocked (logind)")
        self.screen_locked.emit(False)

    @property
    def is_connected(self) -> bool:
        """Whether we're connected to a screen lock signal source."""
        return self._connected

    @property
    def connection_type(self) -> str | None:
        """The type of connection (service name or 'logind')."""
        return self._connection_type
