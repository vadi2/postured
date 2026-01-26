import argparse
import shutil
import signal
import socket
import sys
from pathlib import Path
from PyQt6.QtCore import QSocketNotifier
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMessageBox
from .app import Application


def install_desktop():
    """Install desktop integration files for the current user."""
    resources = Path(__file__).parent / "resources"

    # Install .desktop file
    applications_dir = Path.home() / ".local" / "share" / "applications"
    applications_dir.mkdir(parents=True, exist_ok=True)
    desktop_src = resources / "postured.desktop"
    desktop_dest = applications_dir / "postured.desktop"
    shutil.copy2(desktop_src, desktop_dest)
    print(f"Installed {desktop_dest}")

    # Install icon
    icons_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
    icons_dir.mkdir(parents=True, exist_ok=True)
    icon_src = resources / "icons" / "postured.svg"
    icon_dest = icons_dir / "postured.svg"
    shutil.copy2(icon_src, icon_dest)
    print(f"Installed {icon_dest}")

    print("Desktop integration installed. You may need to log out and back in for changes to take effect.")


def main():
    parser = argparse.ArgumentParser(description="Posture monitoring with screen dimming")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode to show tracking information",
    )
    parser.add_argument(
        "--install-desktop",
        action="store_true",
        help="Install desktop integration files",
    )
    args = parser.parse_args()

    if args.install_desktop:
        install_desktop()
        return

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running with just tray icon

    # Check system tray availability before starting
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            "Postured",
            "System tray is not available.\n\n"
            "Postured requires a system tray to run. Please ensure your "
            "desktop environment has a system tray or status notifier service."
        )
        sys.exit(1)

    postured = Application(debug=args.debug)

    # Set up Unix signal handling for graceful shutdown.
    # Python's set_wakeup_fd() writes the signal number to a fd when a signal
    # arrives, and QSocketNotifier wakes Qt's event loop to handle it safely.
    rsock, wsock = socket.socketpair()
    rsock.setblocking(False)
    wsock.setblocking(False)
    signal.set_wakeup_fd(wsock.fileno())

    def handle_signal():
        sig = rsock.recv(1)[0]
        if sig in (signal.SIGINT, signal.SIGTERM):
            postured.shutdown()
            app.quit()

    # Register handlers (required for set_wakeup_fd to trigger on these signals)
    signal.signal(signal.SIGINT, lambda *args: None)
    signal.signal(signal.SIGTERM, lambda *args: None)

    notifier = QSocketNotifier(rsock.fileno(), QSocketNotifier.Type.Read, app)
    notifier.activated.connect(handle_signal)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
