#!/usr/bin/env python3
"""GTK3 layer-shell worker for Wayland screen dimming overlays.

This script runs as a subprocess and communicates via stdin/stdout JSON messages.
It uses gtk-layer-shell to create fullscreen overlays on the OVERLAY layer.

Commands (stdin):
    {"cmd": "set_opacity", "value": 0.5}
    {"cmd": "quit"}

Responses (stdout):
    {"status": "ready", "monitors": ["DP-1", "HDMI-1"]}
    {"status": "error", "message": "..."}
"""

import json
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
except ValueError:
    print(
        json.dumps({"status": "error", "message": "gtk-layer-shell not available"}),
        flush=True,
    )
    sys.exit(1)

from gi.repository import Gtk, Gdk, GLib


MAX_OPACITY = 0.85


class OverlayWindow(Gtk.Window):
    """Single fullscreen overlay window using layer-shell."""

    def __init__(self, monitor: Gdk.Monitor):
        super().__init__()
        self.opacity_level = 0.0
        self.monitor = monitor
        self.monitor_name = monitor.get_model() or "unknown"

        # Set up layer-shell
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_monitor(self, monitor)
        GtkLayerShell.set_exclusive_zone(self, -1)  # Don't reserve space
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)

        # Anchor to all edges for fullscreen
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)

        # Transparent background
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Drawing area for the overlay
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect("draw", self._on_draw)
        self.add(self.drawing_area)

        self.show_all()
        self._debug(f"Created overlay for {self.monitor_name}")

    def _debug(self, message: str):
        """Print debug message to stderr."""
        print(f"[postured-worker] {message}", file=sys.stderr, flush=True)

    def set_opacity(self, level: float):
        """Set overlay darkness (0.0 = invisible, 1.0 = fully dark)."""
        self.opacity_level = max(0.0, min(1.0, level))
        self.drawing_area.queue_draw()

    def _on_draw(self, widget, cr):
        """Draw the overlay."""
        if self.opacity_level <= 0:
            # Clear to transparent
            cr.set_source_rgba(0, 0, 0, 0)
            cr.set_operator(1)  # CAIRO_OPERATOR_SOURCE
            cr.paint()
            return

        # Draw semi-transparent black overlay
        alpha = self.opacity_level * MAX_OPACITY
        cr.set_source_rgba(0, 0, 0, alpha)
        cr.set_operator(1)  # CAIRO_OPERATOR_SOURCE
        cr.paint()


class LayerShellWorker:
    """Manages overlay windows and handles commands."""

    def __init__(self):
        self.windows: list[OverlayWindow] = []
        self._create_windows()
        self._start_stdin_reader()

    def _create_windows(self):
        """Create overlay windows for all monitors."""
        display = Gdk.Display.get_default()
        monitors = []

        for i in range(display.get_n_monitors()):
            monitor = display.get_monitor(i)
            window = OverlayWindow(monitor)
            self.windows.append(window)
            monitors.append(monitor.get_model() or f"monitor-{i}")

        # Report ready
        print(json.dumps({"status": "ready", "monitors": monitors}), flush=True)

    def _start_stdin_reader(self):
        """Start a thread to read commands from stdin."""
        thread = threading.Thread(target=self._read_stdin, daemon=True)
        thread.start()

    def _read_stdin(self):
        """Read JSON commands from stdin."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                cmd = json.loads(line)
                GLib.idle_add(self._handle_command, cmd)
            except json.JSONDecodeError as e:
                print(
                    f"[postured-worker] Invalid JSON: {e}",
                    file=sys.stderr,
                    flush=True,
                )

    def _handle_command(self, cmd: dict):
        """Handle a command from stdin (called in GTK main thread)."""
        action = cmd.get("cmd")

        if action == "set_opacity":
            value = cmd.get("value", 0.0)
            for window in self.windows:
                window.set_opacity(value)

        elif action == "quit":
            Gtk.main_quit()

        return False  # Remove from idle queue


def main():
    # Initialize GTK
    Gtk.init(None)

    # Check if we're on Wayland
    display = Gdk.Display.get_default()
    if display is None:
        print(
            json.dumps({"status": "error", "message": "No display available"}),
            flush=True,
        )
        sys.exit(1)

    # Check layer-shell support
    if not GtkLayerShell.is_supported():
        print(
            json.dumps(
                {"status": "error", "message": "layer-shell protocol not supported"}
            ),
            flush=True,
        )
        sys.exit(1)

    worker = LayerShellWorker()
    Gtk.main()


if __name__ == "__main__":
    main()
