"""D-Bus service for postured."""

import logging

from PyQt6.QtCore import pyqtSlot, pyqtClassInfo
from PyQt6.QtDBus import QDBusAbstractAdaptor, QDBusConnection, QDBusMessage

logger = logging.getLogger(__name__)


@pyqtClassInfo("D-Bus Interface", "io.github.vadi2.postured1")
@pyqtClassInfo(
    "D-Bus Introspection",
    """
<interface name="io.github.vadi2.postured1">
  <method name="Pause"/>
  <method name="Resume"/>
  <method name="GetStatus">
    <arg type="a{sv}" direction="out" name="status"/>
  </method>
  <method name="GetProfile">
    <arg type="s" direction="out" name="profile"/>
  </method>
  <method name="SetProfile">
    <arg type="s" direction="in" name="profile"/>
  </method>
  <method name="ShowPreview"/>
  <signal name="StatusChanged">
    <arg type="a{sv}" name="status"/>
  </signal>
</interface>
""",
)
class PosturedDBusAdaptor(QDBusAbstractAdaptor):
    """D-Bus adaptor exposing posture status and control methods."""

    def __init__(self, app):
        super().__init__(app)
        self._app = app

    def _get_state_string(self) -> str:
        if not self._app.is_enabled:
            return "paused"
        if self._app.is_calibrating:
            return "calibrating"
        if self._app.consecutive_no_detection >= self._app.AWAY_THRESHOLD:
            return "away"
        if self._app.is_slouching:
            return "slouching"
        return "good"

    def _build_status_dict(self) -> dict:
        return {
            "state": self._get_state_string(),
            "enabled": self._app.is_enabled,
            "is_slouching": self._app.is_slouching,
            "profile": getattr(self._app.settings, "current_profile", "sitting"),
        }

    @pyqtSlot()
    def Pause(self):
        """Stop monitoring and clear overlay."""
        if self._app.is_enabled:
            self._app.tray.enable_toggled.emit(False)

    @pyqtSlot()
    def Resume(self):
        """Start monitoring."""
        if not self._app.is_enabled and not self._app.is_calibrating:
            self._app.tray.enable_toggled.emit(True)

    @pyqtSlot(result="QVariantMap")
    def GetStatus(self) -> dict:
        """Return current status as a dict."""
        return self._build_status_dict()

    @pyqtSlot(result=str)
    def GetProfile(self) -> str:
        """Return the active posture profile (e.g. 'sitting' or 'standing')."""
        return getattr(self._app.settings, "current_profile", "sitting")

    @pyqtSlot(str)
    def SetProfile(self, profile: str):
        """Set the active posture profile ('sitting' or 'standing')."""
        if hasattr(self._app, "set_profile"):
            self._app.set_profile(profile)

    @pyqtSlot()
    def ShowPreview(self):
        """Display the live posture monitor and tuning window."""
        if hasattr(self._app, "show_preview_window"):
            self._app.show_preview_window()

    def emit_status_changed(self):
        """Emit StatusChanged signal on D-Bus."""
        status = self._build_status_dict()
        msg = QDBusMessage.createSignal(
            "/io/github/vadi2/postured",
            "io.github.vadi2.postured1",
            "StatusChanged",
        )
        msg.setArguments([status])
        QDBusConnection.sessionBus().send(msg)


def register_dbus_service(app) -> PosturedDBusAdaptor | None:
    """Register the D-Bus service and return the adaptor."""
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        logger.warning("Could not connect to session D-Bus")
        return None

    if not bus.registerService("io.github.vadi2.postured"):
        logger.warning("Could not register D-Bus service (already running?)")
        return None

    adaptor = PosturedDBusAdaptor(app)

    if not bus.registerObject("/io/github/vadi2/postured", app):
        logger.warning("Could not register D-Bus object")
        return None

    return adaptor
