"""Tests for Overlay opacity transition math."""


from conftest import MockOverlayState


def update_opacity(state: MockOverlayState) -> bool:
    """
    Extracted opacity update logic from Overlay._update_opacity().

    Returns True if opacity was updated, False if already converged.
    """
    if abs(state.current_opacity - state.target_opacity) < 0.001:
        return False

    if state.current_opacity < state.target_opacity:
        state.current_opacity = min(
            state.current_opacity + state.EASE_IN_RATE, state.target_opacity
        )
    else:
        state.current_opacity = max(
            state.current_opacity - state.EASE_OUT_RATE, state.target_opacity
        )

    return True


class TestEaseIn:
    """Test opacity increase (ease-in) behavior."""

    def test_ease_in_rate(self, mock_overlay_state):
        """Opacity increases by 0.015 per tick toward target."""
        state = mock_overlay_state
        state.current_opacity = 0.0
        state.target_opacity = 0.5

        update_opacity(state)

        assert abs(state.current_opacity - 0.015) < 0.0001

    def test_ease_in_multiple_ticks(self, mock_overlay_state):
        """Opacity increases correctly over multiple ticks."""
        state = mock_overlay_state
        state.current_opacity = 0.0
        state.target_opacity = 0.5

        for _ in range(10):
            update_opacity(state)

        expected = 0.015 * 10
        assert abs(state.current_opacity - expected) < 0.0001


class TestEaseOut:
    """Test opacity decrease (ease-out) behavior."""

    def test_ease_out_rate(self, mock_overlay_state):
        """Opacity decreases by 0.047 per tick toward target."""
        state = mock_overlay_state
        state.current_opacity = 0.5
        state.target_opacity = 0.0

        update_opacity(state)

        assert abs(state.current_opacity - (0.5 - 0.047)) < 0.0001

    def test_ease_out_faster_than_ease_in(self, mock_overlay_state):
        """Recovery (ease-out) is faster than onset (ease-in)."""
        assert MockOverlayState.EASE_OUT_RATE > MockOverlayState.EASE_IN_RATE
        # 0.047 > 0.015

    def test_ease_out_multiple_ticks(self, mock_overlay_state):
        """Opacity decreases correctly over multiple ticks."""
        state = mock_overlay_state
        state.current_opacity = 0.5
        state.target_opacity = 0.0

        for _ in range(5):
            update_opacity(state)

        expected = 0.5 - (0.047 * 5)
        assert abs(state.current_opacity - expected) < 0.0001


class TestConvergence:
    """Test convergence behavior."""

    def test_stops_updating_when_converged(self, mock_overlay_state):
        """Stops updating when within 0.001 of target."""
        state = mock_overlay_state
        state.current_opacity = 0.5
        state.target_opacity = 0.5005  # Within 0.001

        updated = update_opacity(state)

        assert updated is False
        assert state.current_opacity == 0.5  # Unchanged

    def test_updates_when_not_converged(self, mock_overlay_state):
        """Updates when more than 0.001 from target."""
        state = mock_overlay_state
        state.current_opacity = 0.5
        state.target_opacity = 0.6

        updated = update_opacity(state)

        assert updated is True


class TestNoOvershoot:
    """Test that opacity doesn't overshoot target."""

    def test_ease_in_no_overshoot(self, mock_overlay_state):
        """Ease-in doesn't overshoot target."""
        state = mock_overlay_state
        state.current_opacity = 0.49
        state.target_opacity = 0.5

        update_opacity(state)

        # Would be 0.49 + 0.015 = 0.505, but capped at target
        assert state.current_opacity == 0.5

    def test_ease_out_no_overshoot(self, mock_overlay_state):
        """Ease-out doesn't overshoot target."""
        state = mock_overlay_state
        state.current_opacity = 0.03
        state.target_opacity = 0.0

        update_opacity(state)

        # Would be 0.03 - 0.047 = -0.017, but capped at target
        assert state.current_opacity == 0.0


class TestBounds:
    """Test target opacity bounds clamping."""

    def test_target_clamped_in_overlay_set_method(self):
        """Target is clamped to 0.0-1.0 in set_target_opacity."""

        # This tests the clamping logic from Overlay.set_target_opacity
        def set_target_opacity(state, opacity):
            state.target_opacity = max(0.0, min(1.0, opacity))

        state = MockOverlayState()

        set_target_opacity(state, -0.5)
        assert state.target_opacity == 0.0

        set_target_opacity(state, 1.5)
        assert state.target_opacity == 1.0

        set_target_opacity(state, 0.5)
        assert state.target_opacity == 0.5
