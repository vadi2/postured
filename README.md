# postured

A Linux app that dims your screen when you slouch.

Uses your webcam and MediaPipe pose detection to monitor your posture. When slouching is detected, the screen dims as a reminder to sit up straight.

## Install

```
uv pip install .
```

## Usage

```
postured
```

## D-Bus Interface

Control postured via D-Bus:

```bash
# Pause/Resume
busctl --user call org.postured.Postured /org/postured/Postured org.postured.Postured1 Pause
busctl --user call org.postured.Postured /org/postured/Postured org.postured.Postured1 Resume

# Get status
busctl --user call org.postured.Postured /org/postured/Postured org.postured.Postured1 GetStatus
```

## Requirements

- Python 3.11+
- Linux
- Webcam

## License

MIT
