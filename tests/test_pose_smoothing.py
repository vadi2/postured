"""Tests for pose smoothing (rolling average calculation)."""


from conftest import MockPoseWorkerState


def smooth(state: MockPoseWorkerState, raw_y: float) -> float:
    """Extracted smoothing logic from PoseWorker._smooth()."""
    state.nose_y_history.append(raw_y)
    return sum(state.nose_y_history) / len(state.nose_y_history)


class TestRollingAverage:
    """Test rolling average calculation."""

    def test_first_value_returns_itself(self, mock_pose_worker_state):
        """First value returns itself (average of single value)."""
        state = mock_pose_worker_state

        result = smooth(state, 0.5)

        assert result == 0.5

    def test_average_of_two_values(self, mock_pose_worker_state):
        """Average calculated correctly for two values."""
        state = mock_pose_worker_state

        smooth(state, 0.4)
        result = smooth(state, 0.6)

        assert result == 0.5  # (0.4 + 0.6) / 2

    def test_window_fills_correctly(self, mock_pose_worker_state):
        """Window fills up to SMOOTHING_WINDOW size."""
        state = mock_pose_worker_state

        values = [0.1, 0.2, 0.3, 0.4, 0.5]
        for v in values:
            smooth(state, v)

        assert len(state.nose_y_history) == 5
        # Last smooth call returns the average
        smooth(state, 0.5)  # This adds 6th value, drops first
        # Now window is [0.2, 0.3, 0.4, 0.5, 0.5]
        assert len(state.nose_y_history) == 5


class TestWindowBehavior:
    """Test sliding window behavior."""

    def test_old_values_drop_off_after_5_entries(self, mock_pose_worker_state):
        """Old values are removed after window is full."""
        state = mock_pose_worker_state

        # Fill window with 0.5
        for _ in range(5):
            smooth(state, 0.5)

        assert list(state.nose_y_history) == [0.5, 0.5, 0.5, 0.5, 0.5]

        # Add new value, oldest should drop
        smooth(state, 1.0)

        assert list(state.nose_y_history) == [0.5, 0.5, 0.5, 0.5, 1.0]
        assert len(state.nose_y_history) == 5

    def test_smoothing_reduces_noise(self, mock_pose_worker_state):
        """Smoothing reduces the effect of noisy values."""
        state = mock_pose_worker_state

        # Stable values
        for _ in range(5):
            smooth(state, 0.5)

        # Add one noisy outlier
        result = smooth(state, 1.0)

        # Result should be dampened: (0.5 + 0.5 + 0.5 + 0.5 + 1.0) / 5 = 0.6
        assert result == 0.6

    def test_window_size_is_5(self, mock_pose_worker_state):
        """Window size is exactly 5."""
        state = mock_pose_worker_state

        assert state.SMOOTHING_WINDOW == 5
        assert state.nose_y_history.maxlen == 5
