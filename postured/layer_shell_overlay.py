"""Layer-shell overlay wrapper for Wayland compositors.

This module spawns a GTK3 subprocess that uses gtk-layer-shell to create
fullscreen overlays. Communication happens via stdin/stdout JSON messages.
"""

import json
import os
import sys

from PyQt6.QtCore import QObject, QTimer, QProcess


class LayerShellOverlay(QObject):
    """Manages layer-shell overlay windows via subprocess."""

    EASE_IN_RATE = 0.015  # Opacity increase per tick (~1/64)
    EASE_OUT_RATE = 0.047  # Opacity decrease per tick (~3/64)
    TRANSITION_INTERVAL_MS = 33  # ~30 FPS

    def __init__(self, parent=None):
        super().__init__(parent)
        self._debug = getattr(parent, "debug", False) if parent else False
        self._process: QProcess | None = None
        self._ready = False
        self._monitors: list[str] = []

        self.current_opacity = 0.0
        self.target_opacity = 0.0

        self.transition_timer = QTimer(self)
        self.transition_timer.timeout.connect(self._update_opacity)
        self.transition_timer.start(self.TRANSITION_INTERVAL_MS)

        self._start_worker()

    def _log(self, message: str):
        """Print debug message."""
        if self._debug:
            print(f"[postured] LAYERSHELL | {message}", file=sys.stderr, flush=True)

    def _start_worker(self):
        """Start the layer-shell worker subprocess."""
        worker_path = os.path.join(os.path.dirname(__file__), "layer_shell_worker.py")
        self._log(f"Starting worker: {worker_path}")

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

        # Use system Python for GTK/GObject access (not uv-managed Python)
        self._process.start("/usr/bin/python3", [worker_path])

    def _on_stdout(self):
        """Handle stdout from worker."""
        if not self._process:
            return

        while self._process.canReadLine():
            line = self._process.readLine().data().decode().strip()
            if not line:
                continue

            try:
                msg = json.loads(line)
                self._handle_message(msg)
            except json.JSONDecodeError:
                self._log(f"Invalid JSON from worker: {line}")

    def _on_stderr(self):
        """Forward worker stderr to our stderr."""
        if not self._process:
            return

        data = self._process.readAllStandardError().data().decode()
        if data:
            sys.stderr.write(data)
            sys.stderr.flush()

    def _handle_message(self, msg: dict):
        """Handle a message from the worker."""
        status = msg.get("status")

        if status == "ready":
            self._ready = True
            self._monitors = msg.get("monitors", [])
            self._log(f"Worker ready with monitors: {self._monitors}")

        elif status == "error":
            error_msg = msg.get("message", "unknown error")
            self._log(f"Worker error: {error_msg}")

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        """Handle worker process exit."""
        self._ready = False
        if exit_status == QProcess.ExitStatus.CrashExit:
            self._log(f"Worker crashed with code {exit_code}")
        else:
            self._log(f"Worker exited with code {exit_code}")

    def _on_error(self, error: QProcess.ProcessError):
        """Handle worker process error."""
        self._ready = False
        error_strings = {
            QProcess.ProcessError.FailedToStart: "failed to start",
            QProcess.ProcessError.Crashed: "crashed",
            QProcess.ProcessError.Timedout: "timed out",
            QProcess.ProcessError.WriteError: "write error",
            QProcess.ProcessError.ReadError: "read error",
            QProcess.ProcessError.UnknownError: "unknown error",
        }
        self._log(f"Worker error: {error_strings.get(error, 'unknown')}")

    def _send_command(self, cmd: dict):
        """Send a command to the worker."""
        if not self._process or self._process.state() != QProcess.ProcessState.Running:
            return

        line = json.dumps(cmd) + "\n"
        self._process.write(line.encode())

    def set_target_opacity(self, opacity: float):
        """Set target opacity (0.0 to 1.0). Transition happens smoothly."""
        old_target = self.target_opacity
        self.target_opacity = max(0.0, min(1.0, opacity))

        # Log significant target changes (> 0.05)
        if self._debug and abs(old_target - self.target_opacity) > 0.05:
            direction = "harder" if self.target_opacity > old_target else "softer"
            print(
                f"[postured] LAYERSHELL | dimming {direction}: {old_target:.2f} -> {self.target_opacity:.2f}",
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
                    f"[postured] LAYERSHELL | dimming started (target: {self.target_opacity:.2f})",
                    file=sys.stderr,
                    flush=True,
                )
            elif self.current_opacity == 0.0 and old_opacity > 0:
                print(
                    "[postured] LAYERSHELL | dimming stopped",
                    file=sys.stderr,
                    flush=True,
                )

        # Send to worker
        self._send_command({"cmd": "set_opacity", "value": self.current_opacity})

    def cleanup(self):
        """Clean up resources."""
        self.transition_timer.stop()

        if self._process:
            self._send_command({"cmd": "quit"})
            self._process.waitForFinished(1000)

            if self._process.state() == QProcess.ProcessState.Running:
                self._process.terminate()
                self._process.waitForFinished(500)

            if self._process.state() == QProcess.ProcessState.Running:
                self._process.kill()

            self._process = None
