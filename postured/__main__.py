import sys
import shutil
from pathlib import Path
from PyQt6.QtWidgets import QApplication
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
    if len(sys.argv) > 1 and sys.argv[1] == "--install-desktop":
        install_desktop()
        return

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running with just tray icon

    postured = Application()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
