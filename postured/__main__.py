import argparse
import sys
from PyQt6.QtWidgets import QApplication
from .app import Application


def main():
    parser = argparse.ArgumentParser(description="Posture monitoring with screen dimming")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode to show tracking information",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running with just tray icon

    postured = Application(debug=args.debug)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
