"""Tests for calibration logic."""

from conftest import MockCalibrationState


def capture_position(state: MockCalibrationState):
    """Extracted capture logic from CalibrationWindow._capture_position()."""
    state.captured_values.append(state.current_nose_y)
    state.current_step += 1


def calculate_calibration_result(
    captured_values: list[float],
) -> tuple[float, float, float]:
    """Extracted calculation from CalibrationWindow._complete()."""
    min_y = min(captured_values)
    max_y = max(captured_values)
    avg_y = sum(captured_values) / len(captured_values)
    return min_y, max_y, avg_y


class TestCalibrationCalculation:
    """Test min/max/avg calculation from captured values."""

    def test_min_max_avg_calculation(self):
        """Correctly calculates min, max, avg from captured values."""
        values = [0.3, 0.7]

        min_y, max_y, avg_y = calculate_calibration_result(values)

        assert min_y == 0.3
        assert max_y == 0.7
        assert avg_y == 0.5  # (0.3 + 0.7) / 2

    def test_calculation_with_typical_values(self):
        """Test with typical calibration values."""
        # Looking at top = looking up = lower Y (good posture)
        # Looking at bottom = looking down = higher Y (bad posture)
        values = [0.35, 0.62]

        min_y, max_y, avg_y = calculate_calibration_result(values)

        assert min_y == 0.35  # Good posture (looking up)
        assert max_y == 0.62  # Bad posture (looking down)
        assert abs(avg_y - 0.485) < 0.0001


class TestStepProgression:
    """Test calibration step progression."""

    def test_step_starts_at_zero(self, mock_calibration_state):
        """Calibration starts at step 0."""
        state = mock_calibration_state
        assert state.current_step == 0

    def test_step_increments_on_capture(self, mock_calibration_state):
        """Step increments after each capture."""
        state = mock_calibration_state

        capture_position(state)
        assert state.current_step == 1

        capture_position(state)
        assert state.current_step == 2

    def test_full_progression_0_to_2(self, mock_calibration_state):
        """Steps progress from 0 to 2 (complete) over 2 captures."""
        state = mock_calibration_state

        for i in range(2):
            assert state.current_step == i
            capture_position(state)

        assert state.current_step == 2


class TestValueCapture:
    """Test value capture during calibration."""

    def test_two_values_captured(self, mock_calibration_state):
        """Two values are captured, one per position."""
        state = mock_calibration_state
        state.current_nose_y = 0.35

        capture_position(state)
        state.current_nose_y = 0.62
        capture_position(state)

        assert len(state.captured_values) == 2
        assert state.captured_values == [0.35, 0.62]

    def test_positions_list_has_two_entries(self, mock_calibration_state):
        """POSITIONS list contains 2 positions."""
        state = mock_calibration_state
        assert len(state.POSITIONS) == 2
        assert state.POSITIONS == ["TOP", "BOTTOM"]


class TestEdgeCases:
    """Test edge cases in calibration."""

    def test_all_same_values(self):
        """Handles case where all captured values are the same."""
        values = [0.5, 0.5]

        min_y, max_y, avg_y = calculate_calibration_result(values)

        assert min_y == 0.5
        assert max_y == 0.5
        assert avg_y == 0.5

    def test_extreme_values(self):
        """Handles extreme value differences."""
        values = [0.1, 0.9]

        min_y, max_y, avg_y = calculate_calibration_result(values)

        assert min_y == 0.1
        assert max_y == 0.9
        assert avg_y == 0.5
