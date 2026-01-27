# <img src="postured/resources/icons/postured.svg" alt="" width="32"> postured

[![Matrix](https://img.shields.io/badge/Matrix-%23postured-000000?logo=matrix&logoColor=white)](https://matrix.to/#/#postured:matrix.org)

A Linux app that dims your screen when you slouch. Optionally locks your screen when you step away.

Uses your webcam and MediaPipe pose detection to monitor your posture. When slouching is detected, the screen dims as a reminder to sit up straight. Runs locally with minimal CPU usage.

## Install

```bash
pip install postured
```

Or with uv:

```bash
uv pip install postured
```

## Usage

```
postured
```

Requires [notifications support](https://extensions.gnome.org/extension/615/appindicator-support/) on Gnome Shell.

## Settings

Right-click the tray icon to access:

- Sensitivity - affects detection threshold and dim intensity; higher values trigger on smaller posture deviations and dim the screen more
- Lock when away - lock screen when you step away from the camera

## D-Bus Interface

Control postured via D-Bus for pause/resume and status queries.

<details>
<summary>Show commands</summary>

```bash
# Pause/Resume
busctl --user call org.postured.Postured /org/postured/Postured org.postured.Postured1 Pause
busctl --user call org.postured.Postured /org/postured/Postured org.postured.Postured1 Resume

# Get status
busctl --user call org.postured.Postured /org/postured/Postured org.postured.Postured1 GetStatus
```

</details>

## Requirements

- Python 3.11+
- Linux
- Webcam

## Credits

Inspired by [posturr](https://github.com/tldev/posturr) - check it out if you're on macOS.

## License

MIT
