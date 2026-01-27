"""GNOME Shell extension overlay wrapper.

This module communicates with the postured-overlay GNOME Shell extension
via D-Bus to control fullscreen dimming overlays on GNOME Wayland.
"""

import subprocess
import sys

from PyQt6.QtCore import QObject, QTimer


def check_gnome_extension() -> bool:
    """Check if postured GNOME extension is running and available.

    Returns:
        True if the extension is available via D-Bus.
    """
    try:
        result = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.postured.Overlay",
                "--object-path",
                "/org/postured/Overlay",
                "--method",
                "org.freedesktop.DBus.Properties.Get",
                "org.postured.Overlay1",
                "Available",
            ],
            capture_output=True,
            timeout=2,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


class GnomeOverlay(QObject):
    """Manages overlay via GNOME Shell extension D-Bus interface."""

    EASE_IN_RATE = 0.015  # Opacity increase per tick (~1/64)
    EASE_OUT_RATE = 0.047  # Opacity decrease per tick (~3/64)
    TRANSITION_INTERVAL_MS = 33  # ~30 FPS

    def __init__(self, parent=None):
        super().__init__(parent)
        self._debug = getattr(parent, "debug", False) if parent else False

        self.current_opacity = 0.0
        self.target_opacity = 0.0

        self.transition_timer = QTimer(self)
        self.transition_timer.timeout.connect(self._update_opacity)
        self.transition_timer.start(self.TRANSITION_INTERVAL_MS)

        self._log("Connected to org.postured.Overlay")

    def _log(self, message: str):
        """Print debug message."""
        if self._debug:
            print(f"[postured] GNOME     | {message}", file=sys.stderr, flush=True)

    def _send_opacity(self, opacity: float):
        """Send opacity to GNOME extension via D-Bus."""
        try:
            subprocess.run(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.postured.Overlay",
                    "--object-path",
                    "/org/postured/Overlay",
                    "--method",
                    "org.postured.Overlay1.SetOpacity",
                    str(opacity),
                ],
                capture_output=True,
                timeout=1,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Silently ignore failures

    def set_target_opacity(self, opacity: float):
        """Set target opacity (0.0 to 1.0). Transition happens smoothly."""
        old_target = self.target_opacity
        self.target_opacity = max(0.0, min(1.0, opacity))

        # Log significant target changes (> 0.05)
        if self._debug and abs(old_target - self.target_opacity) > 0.05:
            direction = "harder" if self.target_opacity > old_target else "softer"
            print(
                f"[postured] GNOME     | dimming {direction}: {old_target:.2f} -> {self.target_opacity:.2f}",
                file=sys.stderr,
                flush=True,
            )

    def _update_opacity(self):
        """Update opacity towards target (called by timer)."""
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
                    f"[postured] GNOME     | dimming started (target: {self.target_opacity:.2f})",
                    file=sys.stderr,
                    flush=True,
                )
            elif self.current_opacity == 0.0 and old_opacity > 0:
                print(
                    "[postured] GNOME     | dimming stopped",
                    file=sys.stderr,
                    flush=True,
                )

        # Send to extension
        self._send_opacity(self.current_opacity)

    def cleanup(self):
        """Clean up resources."""
        self.transition_timer.stop()

        # Tell extension to reset opacity
        try:
            subprocess.run(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.postured.Overlay",
                    "--object-path",
                    "/org/postured/Overlay",
                    "--method",
                    "org.postured.Overlay1.Quit",
                ],
                capture_output=True,
                timeout=1,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
