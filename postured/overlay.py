import os
import sys

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QObject
from PyQt6.QtGui import QPainter, QColor


class OverlayWindow(QWidget):
    """Single full-screen overlay window."""

    MAX_OPACITY = 0.85

    def __init__(self, screen):
        super().__init__()
        self.opacity_level = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        geometry = screen.geometry()
        self.setGeometry(geometry)

    def set_opacity(self, level: float):
        """Set overlay darkness (0.0 = invisible, 1.0 = fully dark)."""
        self.opacity_level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event):
        if self.opacity_level <= 0:
            return
        painter = QPainter(self)
        color = QColor(0, 0, 0, int(self.opacity_level * 255 * self.MAX_OPACITY))
        painter.fillRect(self.rect(), color)


class QtOverlay(QObject):
    """Manages overlay windows across all monitors using Qt."""

    EASE_IN_RATE = 0.015  # Opacity increase per tick (~1/64)
    EASE_OUT_RATE = 0.047  # Opacity decrease per tick (~3/64)
    TRANSITION_INTERVAL_MS = 33  # ~30 FPS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.windows: list[OverlayWindow] = []
        self.current_opacity = 0.0
        self.target_opacity = 0.0
        self._debug = getattr(parent, "debug", False) if parent else False

        self.transition_timer = QTimer(self)
        self.transition_timer.timeout.connect(self._update_opacity)
        self.transition_timer.start(self.TRANSITION_INTERVAL_MS)

        self._create_windows()

    def _create_windows(self):
        app = QApplication.instance()
        for screen in app.screens():
            window = OverlayWindow(screen)
            window.show()
            self.windows.append(window)

    def set_target_opacity(self, opacity: float):
        """Set target opacity (0.0 to 1.0). Transition happens smoothly."""
        old_target = self.target_opacity
        self.target_opacity = max(0.0, min(1.0, opacity))
        # Log significant target changes (> 0.05)
        if self._debug and abs(old_target - self.target_opacity) > 0.05:
            direction = "harder" if self.target_opacity > old_target else "softer"
            print(
                f"[postured] OVERLAY   | dimming {direction}: {old_target:.2f} -> {self.target_opacity:.2f}",
                file=sys.stderr,
                flush=True,
            )

    def _update_opacity(self):
        if abs(self.current_opacity - self.target_opacity) < 0.001:
            return

        old_opacity = self.current_opacity
        if self.current_opacity < self.target_opacity:
            self.current_opacity = min(
                self.current_opacity + self.EASE_IN_RATE, self.target_opacity
            )
        else:
            self.current_opacity = max(
                self.current_opacity - self.EASE_OUT_RATE, self.target_opacity
            )

        # Log when dimming starts or stops
        if self._debug:
            if old_opacity == 0.0 and self.current_opacity > 0:
                print(
                    f"[postured] OVERLAY   | dimming started (target: {self.target_opacity:.2f})",
                    file=sys.stderr,
                    flush=True,
                )
            elif self.current_opacity == 0.0 and old_opacity > 0:
                print(
                    "[postured] OVERLAY   | dimming stopped",
                    file=sys.stderr,
                    flush=True,
                )

        for window in self.windows:
            window.set_opacity(self.current_opacity)

    def cleanup(self):
        self.transition_timer.stop()
        for window in self.windows:
            window.close()


def _is_wayland_session() -> bool:
    """Check if running in a Wayland session."""
    return os.environ.get("XDG_SESSION_TYPE") == "wayland"


def _check_layer_shell() -> tuple[bool, str]:
    """Check if gtk-layer-shell is available and supported by the compositor.

    Returns:
        Tuple of (is_available, reason_message)
    """
    import subprocess

    # Check both library availability AND compositor support
    # Exit codes: 0 = supported, 1 = compositor doesn't support, 2 = library not installed
    check_script = """
import sys
try:
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('GtkLayerShell', '0.1')
    from gi.repository import Gtk, GtkLayerShell
    Gtk.init(None)
    if GtkLayerShell.is_supported():
        sys.exit(0)
    else:
        sys.exit(1)
except (ValueError, ImportError):
    sys.exit(2)
"""
    try:
        result = subprocess.run(
            ["/usr/bin/python3", "-c", check_script],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, "supported"
        elif result.returncode == 1:
            return False, "compositor does not support layer-shell protocol (not wlroots-based)"
        else:
            return False, "gir1.2-gtklayershell-0.1 package not installed"
    except subprocess.TimeoutExpired:
        return False, "layer-shell check timed out"
    except FileNotFoundError:
        return False, "/usr/bin/python3 not found"


def create_overlay(parent=None):
    """Factory function to create the appropriate overlay backend.

    Priority:
    - X11: QtOverlay
    - Wayland + wlroots: LayerShellOverlay
    - Wayland + GNOME (extension installed): GnomeOverlay
    - Wayland fallback: QtOverlay
    """
    debug = getattr(parent, "debug", False) if parent else False

    def log(message: str):
        if debug:
            print(f"[postured] OVERLAY   | {message}", file=sys.stderr, flush=True)

    if not _is_wayland_session():
        log("X11 session detected, using Qt backend")
        return QtOverlay(parent)

    log("Wayland session detected")

    available, reason = _check_layer_shell()
    if available:
        log("layer-shell protocol supported, using layer-shell backend")

        from .layer_shell_overlay import LayerShellOverlay

        return LayerShellOverlay(parent)

    log(f"layer-shell: {reason}")

    # Try GNOME extension (GNOME Wayland)
    if _check_gnome_extension():
        log("GNOME extension available, using D-Bus backend")

        from .gnome_overlay import GnomeOverlay

        return GnomeOverlay(parent)

    # Check if running GNOME and suggest extension installation
    if _is_gnome_session():
        log(
            "GNOME detected but extension not installed. "
            "Install 'Postured Overlay' from https://extensions.gnome.org for proper overlay support"
        )

    log("Falling back to Qt backend (overlay may not work correctly on Wayland)")
    return QtOverlay(parent)


def _is_gnome_session() -> bool:
    """Check if running in a GNOME session."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    return "gnome" in desktop


def _check_gnome_extension() -> bool:
    """Check if postured GNOME extension is running."""
    from .gnome_overlay import check_gnome_extension

    return check_gnome_extension()
