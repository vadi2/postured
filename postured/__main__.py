import signal
import socket
import sys
from PyQt6.QtCore import QSocketNotifier
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMessageBox
from .app import Application


def main():
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

    postured = Application()

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
