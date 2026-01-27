"""Tests for monitor detection algorithm."""

from unittest.mock import MagicMock
from conftest import MockMonitorDetectorState


def create_mock_screen(name: str, x: int, width: int, height: int = 1080):
    """Create a mock QScreen with specified geometry."""
    screen = MagicMock()
    screen.name.return_value = name
    geometry = MagicMock()
    geometry.x.return_value = x
    geometry.width.return_value = width
    geometry.height.return_value = height
    screen.geometry.return_value = geometry
    return screen


def detect_monitor_algorithm(nose_x: float, screens: list) -> str:
    """Extracted monitor detection algorithm from MonitorDetector._detect_monitor()."""
    # Mirror the X coordinate (camera is mirrored)
    mirrored_x = 1.0 - nose_x

    # Sort screens by X position (left to right)
    sorted_screens = sorted(screens, key=lambda s: s.geometry().x())

    # Calculate total desktop width
    total_width = sum(s.geometry().width() for s in sorted_screens)
    if total_width == 0:
        return f"{sorted_screens[0].name()}_{sorted_screens[0].geometry().width()}x{sorted_screens[0].geometry().height()}"

    # Map mirrored_x to desktop coordinate
    desktop_x = mirrored_x * total_width

    # Find containing screen
    cumulative_x = 0
    for screen in sorted_screens:
        screen_width = screen.geometry().width()
        if desktop_x < cumulative_x + screen_width:
            return f"{screen.name()}_{screen.geometry().width()}x{screen.geometry().height()}"
        cumulative_x += screen_width

    # Fallback to last screen
    last = sorted_screens[-1]
    return f"{last.name()}_{last.geometry().width()}x{last.geometry().height()}"


def apply_hysteresis(state: MockMonitorDetectorState, detected: str) -> str | None:
    """Extracted hysteresis logic from MonitorDetector.update()."""
    if detected != state._current_monitor_id:
        if detected == state._pending_monitor_id:
            state._pending_frames += 1
            if state._pending_frames >= state.HYSTERESIS_FRAMES:
                state._current_monitor_id = detected
                state._pending_monitor_id = None
                state._pending_frames = 0
        else:
            state._pending_monitor_id = detected
            state._pending_frames = 1
    else:
        state._pending_monitor_id = None
        state._pending_frames = 0

    return state._current_monitor_id


class TestMonitorDetectionAlgorithm:
    """Test the core monitor detection algorithm."""

    def test_single_monitor_always_returns_same(self):
        """With single monitor, detection always returns that monitor."""
        screens = [create_mock_screen("HDMI-1", 0, 1920)]

        # Test various nose_x positions
        for nose_x in [0.0, 0.25, 0.5, 0.75, 1.0]:
            result = detect_monitor_algorithm(nose_x, screens)
            assert result == "HDMI-1_1920x1080"

    def test_dual_monitor_left_right(self):
        """Dual monitors: nose_x=1.0 (looking right in camera) = left screen."""
        # Two monitors side by side
        left_screen = create_mock_screen("HDMI-1", 0, 1920)
        right_screen = create_mock_screen("DP-2", 1920, 1920)
        screens = [left_screen, right_screen]

        # Camera is mirrored: looking right in camera (nose_x=1.0) means
        # looking at left side of desktop (mirrored_x=0.0)
        result = detect_monitor_algorithm(1.0, screens)
        assert result == "HDMI-1_1920x1080"

        # Looking left in camera (nose_x=0.0) means looking at right screen
        result = detect_monitor_algorithm(0.0, screens)
        assert result == "DP-2_1920x1080"

    def test_dual_monitor_center(self):
        """Center position detected correctly."""
        left_screen = create_mock_screen("HDMI-1", 0, 1920)
        right_screen = create_mock_screen("DP-2", 1920, 1920)
        screens = [left_screen, right_screen]

        # Center of camera view (0.5) = center of mirrored view (0.5)
        # Desktop center is at 1920 pixels, which is the boundary
        # 0.5 * 3840 = 1920, which should hit the second monitor
        result = detect_monitor_algorithm(0.5, screens)
        assert result == "DP-2_1920x1080"

        # Slightly right in camera (0.49) = 0.51 mirrored = left screen
        result = detect_monitor_algorithm(0.51, screens)
        assert result == "HDMI-1_1920x1080"

    def test_three_monitors(self):
        """Three monitors side by side."""
        left = create_mock_screen("DP-1", 0, 1920)
        center = create_mock_screen("HDMI-1", 1920, 1920)
        right = create_mock_screen("DP-2", 3840, 1920)
        screens = [left, center, right]

        # Total width = 5760
        # Looking far right in camera (1.0) = left screen
        result = detect_monitor_algorithm(1.0, screens)
        assert result == "DP-1_1920x1080"

        # Looking far left in camera (0.0) = right screen
        result = detect_monitor_algorithm(0.0, screens)
        assert result == "DP-2_1920x1080"

        # Center should hit middle screen
        # mirrored 0.5 * 5760 = 2880, which is within center screen (1920-3840)
        result = detect_monitor_algorithm(0.5, screens)
        assert result == "HDMI-1_1920x1080"

    def test_different_resolution_monitors(self):
        """Monitors with different resolutions."""
        # 4K monitor on left, 1080p on right
        left = create_mock_screen("HDMI-1", 0, 3840, 2160)
        right = create_mock_screen("DP-2", 3840, 1920, 1080)
        screens = [left, right]

        # Total width = 5760
        # Looking at center (0.5 mirrored) = 0.5 * 5760 = 2880
        # This is within the 4K monitor (0-3840)
        result = detect_monitor_algorithm(0.5, screens)
        assert result == "HDMI-1_3840x2160"

    def test_unsorted_screens_handled(self):
        """Screens provided in wrong order are sorted correctly."""
        # Screens provided right-to-left
        right = create_mock_screen("DP-2", 1920, 1920)
        left = create_mock_screen("HDMI-1", 0, 1920)
        screens = [right, left]  # Wrong order

        # Should still detect correctly
        result = detect_monitor_algorithm(1.0, screens)  # Looking right = left screen
        assert result == "HDMI-1_1920x1080"


class TestHysteresis:
    """Test hysteresis behavior for monitor switching."""

    def test_initial_detection(self, mock_monitor_detector_state):
        """First detection sets pending, not current."""
        state = mock_monitor_detector_state

        result = apply_hysteresis(state, "HDMI-1_1920x1080")

        assert result is None  # No current yet
        assert state._pending_monitor_id == "HDMI-1_1920x1080"
        assert state._pending_frames == 1

    def test_hysteresis_prevents_immediate_switch(self, mock_monitor_detector_state):
        """Monitor doesn't switch until threshold frames reached."""
        state = mock_monitor_detector_state
        state._current_monitor_id = "HDMI-1_1920x1080"

        # Detect new monitor for fewer than threshold frames
        for i in range(4):
            result = apply_hysteresis(state, "DP-2_1920x1080")
            assert result == "HDMI-1_1920x1080"  # Still on original
            assert state._pending_frames == i + 1

    def test_hysteresis_switches_after_threshold(self, mock_monitor_detector_state):
        """Monitor switches after threshold frames reached."""
        state = mock_monitor_detector_state
        state._current_monitor_id = "HDMI-1_1920x1080"

        # Detect new monitor for threshold frames
        for i in range(5):
            result = apply_hysteresis(state, "DP-2_1920x1080")

        assert result == "DP-2_1920x1080"
        assert state._pending_monitor_id is None
        assert state._pending_frames == 0

    def test_hysteresis_resets_on_return(self, mock_monitor_detector_state):
        """Returning to current monitor resets pending state."""
        state = mock_monitor_detector_state
        state._current_monitor_id = "HDMI-1_1920x1080"

        # Start switching to new monitor
        apply_hysteresis(state, "DP-2_1920x1080")
        apply_hysteresis(state, "DP-2_1920x1080")
        assert state._pending_frames == 2

        # Return to original monitor
        result = apply_hysteresis(state, "HDMI-1_1920x1080")
        assert result == "HDMI-1_1920x1080"
        assert state._pending_monitor_id is None
        assert state._pending_frames == 0

    def test_hysteresis_resets_on_third_monitor(self, mock_monitor_detector_state):
        """Switching to third monitor resets pending count."""
        state = mock_monitor_detector_state
        state._current_monitor_id = "HDMI-1_1920x1080"

        # Start switching to second monitor
        apply_hysteresis(state, "DP-2_1920x1080")
        apply_hysteresis(state, "DP-2_1920x1080")
        assert state._pending_frames == 2

        # Switch to third monitor
        apply_hysteresis(state, "DP-3_1920x1080")
        assert state._pending_monitor_id == "DP-3_1920x1080"
        assert state._pending_frames == 1  # Reset to 1


class TestEdgeCases:
    """Test edge cases in monitor detection."""

    def test_empty_screens_returns_none(self, mock_monitor_detector_state):
        """Empty screens list returns None without calling detection algorithm."""
        state = mock_monitor_detector_state

        # Simulate MonitorDetector.update() guard: if not screens, return None
        def update_with_guard(nose_x: float, screens: list) -> str | None:
            if not screens:
                return None
            detected = detect_monitor_algorithm(nose_x, screens)
            return apply_hysteresis(state, detected)

        result = update_with_guard(0.5, [])
        assert result is None
        # State should be unchanged
        assert state._current_monitor_id is None
        assert state._pending_monitor_id is None
        assert state._pending_frames == 0

    def test_nose_x_at_boundaries(self):
        """Nose X at exact boundaries works correctly."""
        screens = [create_mock_screen("HDMI-1", 0, 1920)]

        # Exact boundaries
        assert detect_monitor_algorithm(0.0, screens) == "HDMI-1_1920x1080"
        assert detect_monitor_algorithm(1.0, screens) == "HDMI-1_1920x1080"

    def test_nose_x_out_of_range_clamped(self):
        """Nose X values outside 0-1 still produce valid results."""
        screens = [
            create_mock_screen("HDMI-1", 0, 1920),
            create_mock_screen("DP-2", 1920, 1920),
        ]

        # Values beyond 1.0 still map to valid screens
        # nose_x=-0.1 -> mirrored=1.1 -> beyond right edge -> last screen
        result = detect_monitor_algorithm(-0.1, screens)
        assert result == "DP-2_1920x1080"

        # nose_x=1.1 -> mirrored=-0.1 -> maps to negative x -> first screen
        result = detect_monitor_algorithm(1.1, screens)
        assert result == "HDMI-1_1920x1080"
