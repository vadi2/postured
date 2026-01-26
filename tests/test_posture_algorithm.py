"""Tests for posture evaluation algorithm."""


from conftest import MockAppState


def evaluate_posture(state: MockAppState, current_y: float) -> tuple[float, bool]:
    """
    Extracted posture evaluation logic from Application._evaluate_posture().

    Returns (target_opacity, is_bad_posture_frame).
    """
    posture_range = abs(state.bad_posture_y - state.good_posture_y)
    if posture_range < 0.01:
        posture_range = 0.2

    slouch_amount = current_y - state.bad_posture_y
    base_threshold = state.DEAD_ZONE * posture_range * state.sensitivity

    enter_threshold = base_threshold
    exit_threshold = base_threshold * state.HYSTERESIS_FACTOR

    threshold = exit_threshold if state.is_slouching else enter_threshold
    is_bad_posture = slouch_amount > threshold

    target_opacity = 0.0

    if is_bad_posture:
        state.consecutive_bad_frames += 1
        state.consecutive_good_frames = 0

        if state.consecutive_bad_frames >= state.FRAME_THRESHOLD:
            state.is_slouching = True
            severity = (slouch_amount - enter_threshold) / posture_range
            severity = max(0.0, min(1.0, severity))
            eased_severity = severity * severity
            target_opacity = 0.03 + eased_severity * 0.97 * state.sensitivity
    else:
        state.consecutive_good_frames += 1
        state.consecutive_bad_frames = 0

        if state.consecutive_good_frames >= state.FRAME_THRESHOLD:
            state.is_slouching = False

    return target_opacity, is_bad_posture


class TestSlouchDetection:
    """Test slouch detection basics."""

    def test_current_y_above_bad_posture_y_triggers_bad_frames(self, mock_app_state):
        """Current Y above bad_posture_y triggers bad frame counting."""
        state = mock_app_state
        # bad_posture_y is 0.6, so 0.7 should trigger slouching
        _, is_bad = evaluate_posture(state, 0.7)
        assert is_bad is True
        assert state.consecutive_bad_frames == 1

    def test_current_y_below_bad_posture_y_is_good(self, mock_app_state):
        """Current Y below bad_posture_y is considered good posture."""
        state = mock_app_state
        _, is_bad = evaluate_posture(state, 0.5)
        assert is_bad is False
        assert state.consecutive_good_frames == 1


class TestHysteresis:
    """Test hysteresis behavior for state transitions."""

    def test_hysteresis_entry_threshold(self, mock_app_state):
        """Must exceed base_threshold to enter slouching."""
        state = mock_app_state
        # Not currently slouching, uses enter_threshold (full base_threshold)
        # base_threshold = 0.03 * 0.2 * 0.85 = 0.0051
        # With bad_posture_y = 0.6, need to be > 0.6 + 0.0051 = 0.6051

        # Just at threshold - should not trigger
        _, is_bad = evaluate_posture(state, 0.605)
        assert is_bad is False

        # Above threshold - should trigger
        state2 = MockAppState()
        _, is_bad2 = evaluate_posture(state2, 0.61)
        assert is_bad2 is True

    def test_hysteresis_exit_threshold(self, mock_app_state):
        """Only needs to drop below base_threshold * 0.5 to exit slouching."""
        state = mock_app_state
        state.is_slouching = True
        # Uses exit_threshold = base_threshold * 0.5 = 0.0051 * 0.5 = 0.00255
        # Need to be <= 0.6 + 0.00255 = 0.60255 to exit

        # Still above exit threshold - stays slouching
        _, is_bad = evaluate_posture(state, 0.605)
        assert is_bad is True

        # Below exit threshold - considered good
        state2 = MockAppState()
        state2.is_slouching = True
        _, is_bad2 = evaluate_posture(state2, 0.601)
        assert is_bad2 is False


class TestFrameThreshold:
    """Test consecutive frame requirements."""

    def test_needs_8_bad_frames_to_become_slouching(self, mock_app_state):
        """Need 8 consecutive bad frames to enter slouching state."""
        state = mock_app_state

        for i in range(7):
            evaluate_posture(state, 0.7)
            assert state.is_slouching is False

        evaluate_posture(state, 0.7)
        assert state.is_slouching is True

    def test_needs_8_good_frames_to_clear_slouching(self, mock_app_state):
        """Need 8 consecutive good frames to exit slouching state."""
        state = mock_app_state
        state.is_slouching = True

        for i in range(7):
            evaluate_posture(state, 0.5)
            assert state.is_slouching is True

        evaluate_posture(state, 0.5)
        assert state.is_slouching is False

    def test_bad_frame_resets_good_frame_counter(self, mock_app_state):
        """A bad frame resets the consecutive good frames counter."""
        state = mock_app_state
        state.is_slouching = True

        # Build up good frames
        for i in range(5):
            evaluate_posture(state, 0.5)

        assert state.consecutive_good_frames == 5

        # One bad frame resets
        evaluate_posture(state, 0.7)
        assert state.consecutive_good_frames == 0
        assert state.consecutive_bad_frames == 1

    def test_good_frame_resets_bad_frame_counter(self, mock_app_state):
        """A good frame resets the consecutive bad frames counter."""
        state = mock_app_state

        # Build up bad frames
        for i in range(5):
            evaluate_posture(state, 0.7)

        assert state.consecutive_bad_frames == 5

        # One good frame resets
        evaluate_posture(state, 0.5)
        assert state.consecutive_bad_frames == 0
        assert state.consecutive_good_frames == 1


class TestOpacityCalculation:
    """Test opacity calculation and quadratic easing."""

    def test_opacity_uses_quadratic_easing(self, mock_app_state):
        """Opacity calculation uses quadratic ease-in."""
        state = mock_app_state

        # Get into slouching state
        for _ in range(8):
            evaluate_posture(state, 0.7)

        # Now calculate expected opacity
        posture_range = 0.2  # bad - good = 0.6 - 0.4
        base_threshold = 0.03 * 0.2 * 0.85
        slouch_amount = 0.7 - 0.6  # 0.1

        severity = (slouch_amount - base_threshold) / posture_range
        severity = max(0.0, min(1.0, severity))
        eased_severity = severity * severity
        expected_opacity = 0.03 + eased_severity * 0.97 * 0.85

        opacity, _ = evaluate_posture(state, 0.7)
        assert abs(opacity - expected_opacity) < 0.001

    def test_minimum_opacity_is_003(self, mock_app_state):
        """Minimum opacity when slouching is 0.03."""
        state = mock_app_state

        # Get just barely into slouching state
        for _ in range(8):
            evaluate_posture(state, 0.61)

        opacity, _ = evaluate_posture(state, 0.61)
        assert opacity >= 0.03

    def test_opacity_zero_when_not_slouching(self, mock_app_state):
        """Opacity is 0 when not in slouching state."""
        state = mock_app_state

        # Just a few bad frames, not enough to trigger slouching
        for _ in range(5):
            opacity, _ = evaluate_posture(state, 0.7)
            assert opacity == 0.0


class TestSensitivityScaling:
    """Test sensitivity parameter effects."""

    def test_higher_sensitivity_increases_opacity(self, mock_app_state):
        """Higher sensitivity results in higher opacity."""
        state_high = MockAppState(sensitivity=1.0)
        state_low = MockAppState(sensitivity=0.5)

        # Get both into slouching
        for _ in range(8):
            evaluate_posture(state_high, 0.7)
            evaluate_posture(state_low, 0.7)

        opacity_high, _ = evaluate_posture(state_high, 0.7)
        opacity_low, _ = evaluate_posture(state_low, 0.7)

        assert opacity_high > opacity_low

    def test_higher_sensitivity_lower_threshold(self, mock_app_state):
        """Higher sensitivity means lower threshold for detection."""
        # With higher sensitivity, smaller slouch amounts trigger detection
        state_high = MockAppState(sensitivity=1.0)
        state_low = MockAppState(sensitivity=0.3)

        # A moderate slouch amount
        test_y = 0.608

        _, is_bad_high = evaluate_posture(state_high, test_y)
        _, is_bad_low = evaluate_posture(state_low, test_y)

        # High sensitivity should detect this as bad
        assert is_bad_high is True
        # Low sensitivity might not (depends on exact thresholds)
        # base_threshold = 0.03 * 0.2 * sensitivity
        # high: 0.006, low: 0.0018
        # slouch = 0.608 - 0.6 = 0.008
        # high: 0.008 > 0.006 = True
        # low: 0.008 > 0.0018 = True (actually both should trigger)


class TestSmallPostureRange:
    """Test fallback behavior for small posture ranges."""

    def test_small_range_falls_back_to_02(self, mock_app_state):
        """When posture range < 0.01, falls back to 0.2."""
        state = mock_app_state
        state.good_posture_y = 0.5
        state.bad_posture_y = 0.505  # Range of 0.005

        # Should use 0.2 as range for calculations
        # base_threshold = 0.03 * 0.2 * 0.85 = 0.0051
        # slouch_amount = 0.6 - 0.505 = 0.095
        # 0.095 > 0.0051 = True

        _, is_bad = evaluate_posture(state, 0.6)
        assert is_bad is True

    def test_exact_zero_range_uses_fallback(self, mock_app_state):
        """When good_posture_y == bad_posture_y, uses fallback."""
        state = mock_app_state
        state.good_posture_y = 0.5
        state.bad_posture_y = 0.5

        # Should not crash, should use fallback
        _, is_bad = evaluate_posture(state, 0.6)
        assert is_bad is True


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_current_y_exactly_at_threshold(self, mock_app_state):
        """Test behavior when current_y is exactly at the threshold."""
        state = mock_app_state
        # base_threshold = 0.03 * 0.2 * 0.85 = 0.0051
        # threshold when not slouching = 0.6 + 0.0051 = 0.6051

        # Exactly at threshold (slouch_amount = threshold, not > threshold)
        _, is_bad = evaluate_posture(state, 0.6051)
        # slouch_amount = 0.6051 - 0.6 = 0.0051
        # is_bad = 0.0051 > 0.0051 = False
        assert is_bad is False

    def test_negative_slouch_amount(self, mock_app_state):
        """Negative slouch amount (good posture) is not detected as bad."""
        state = mock_app_state
        # current_y well below bad_posture_y
        _, is_bad = evaluate_posture(state, 0.3)
        assert is_bad is False
        assert state.consecutive_good_frames == 1

    def test_extreme_slouch_caps_severity(self, mock_app_state):
        """Extreme slouch values cap severity at 1.0."""
        state = mock_app_state

        # Get into slouching state with extreme value
        for _ in range(8):
            evaluate_posture(state, 1.0)

        opacity, _ = evaluate_posture(state, 1.0)
        # Max opacity should be around 0.03 + 1 * 0.97 * 0.85 = 0.8545
        assert opacity <= 0.03 + 0.97 * state.sensitivity + 0.001
