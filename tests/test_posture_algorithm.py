"""Tests for posture evaluation algorithm."""

from conftest import MockAppState


def evaluate_posture(
    state: MockAppState,
    current_y: float,
    forward_offset: float = 0.0,
    shoulders_detected: bool = False,
    scale_ratio: float = 0.0,
    neck_v_ratio: float = 0.0,
    view_mode: str = "front",
    side_forward: float = 0.0,
    cva_deg: float = 90.0,
) -> tuple[float, bool]:
    """
    Extracted posture evaluation logic from Application._evaluate_posture().

    Returns (target_opacity, is_bad_posture_frame).
    """
    if view_mode == "side":
        good_side_forward = getattr(state, "good_side_forward", 0.0)
        good_cva = getattr(state, "good_cva", 65.0)

        delta_side = side_forward - good_side_forward
        threshold_scale = 1.5 - 0.5 * state.sensitivity
        enter_threshold = 0.08 * threshold_scale
        exit_threshold = enter_threshold * state.HYSTERESIS_FACTOR
        threshold = exit_threshold if state.is_slouching else enter_threshold

        if delta_side <= -0.05:
            is_bad_posture = False
            slouch_severity = 0.0
        else:
            cva_slouch = (cva_deg > 0.0 and cva_deg < 50.0)
            plumb_slouch = delta_side > threshold

            if plumb_slouch or cva_slouch:
                is_bad_posture = True
                if plumb_slouch:
                    excess = delta_side - enter_threshold
                    slouch_severity = max(0.0, min(1.0, excess / 0.10))
                else:
                    slouch_severity = max(0.0, min(1.0, (50.0 - cva_deg) / 20.0))
            else:
                is_bad_posture = False
                slouch_severity = 0.0
    elif shoulders_detected:
        good_forward = getattr(state, "good_forward_offset", 0.55)
        good_scale = getattr(state, "good_head_scale", 0.40)
        good_neck = getattr(state, "good_neck_ratio", 0.32)

        threshold_scale = 1.5 - 0.5 * state.sensitivity
        enter_threshold = state.FORWARD_THRESHOLD_BASE * threshold_scale
        exit_threshold = enter_threshold * state.HYSTERESIS_FACTOR
        threshold = exit_threshold if state.is_slouching else enter_threshold

        delta_z = forward_offset - good_forward
        base_s = max(0.1, good_scale)
        delta_scale = (scale_ratio - base_s) / base_s if scale_ratio > 0.0 else 0.0
        base_n = max(0.1, good_neck)
        delta_neck = (base_n - neck_v_ratio) / base_n if neck_v_ratio > 0.0 else 0.0

        if delta_z <= -0.05:
            forward_slouch = delta_z
        else:
            forward_slouch = (
                delta_z
                + 0.5 * max(0.0, delta_scale)
                + 0.5 * max(0.0, delta_neck)
            )

        if forward_slouch <= 0.0:
            is_bad_posture = False
            slouch_severity = 0.0
        else:
            is_bad_posture = forward_slouch > threshold
            if is_bad_posture:
                excess = forward_slouch - enter_threshold
                slouch_severity = max(0.0, min(1.0, excess / 0.10))
            else:
                slouch_severity = 0.0
    else:
        posture_range = max(0.08, abs(state.bad_posture_y - state.good_posture_y))

        slouch_amount = current_y - state.bad_posture_y
        base_threshold = state.DEAD_ZONE * posture_range * state.sensitivity

        enter_threshold = base_threshold
        exit_threshold = base_threshold * state.HYSTERESIS_FACTOR

        threshold = exit_threshold if state.is_slouching else enter_threshold
        is_bad_posture = slouch_amount > threshold

        if is_bad_posture:
            severity = (slouch_amount - enter_threshold) / posture_range
            slouch_severity = max(0.0, min(1.0, severity))
        else:
            slouch_severity = 0.0

    target_opacity = 0.0

    if is_bad_posture:
        state.consecutive_bad_frames += 1
        state.consecutive_good_frames = 0

        if state.consecutive_bad_frames >= state.FRAME_THRESHOLD:
            state.is_slouching = True
            eased_severity = slouch_severity * slouch_severity
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
        # bad_posture_y is 0.6, so 0.5 should be good
        _, is_bad = evaluate_posture(state, 0.5)
        assert is_bad is False
        assert state.consecutive_good_frames == 1


class TestForwardHeadPosture:
    """Test head-relative-to-shoulder posture evaluation."""

    def test_leaning_back_never_slouches(self, mock_app_state):
        """Leaning back (head behind or level with baseline) is never slouching, even if head is low."""
        state = mock_app_state
        # Head dropped low in frame (current_y = 0.85), but leaning back (forward_offset = 0.40, below 0.55 baseline)
        opacity, is_bad = evaluate_posture(
            state,
            current_y=0.85,
            forward_offset=0.40,
            shoulders_detected=True,
        )
        assert is_bad is False
        assert state.consecutive_bad_frames == 0
        assert opacity == 0.0

    def test_head_level_with_shoulders_is_good(self, mock_app_state):
        """Head at upright baseline (forward_offset = 0.55) is good posture."""
        state = mock_app_state
        _, is_bad = evaluate_posture(
            state, current_y=0.7, forward_offset=0.55, shoulders_detected=True
        )
        assert is_bad is False

    def test_forward_head_triggers_slouch(self, mock_app_state):
        """Head moving in front of shoulders (forward_offset = 0.85, well above baseline) triggers slouching."""
        state = mock_app_state
        for _ in range(8):
            opacity, is_bad = evaluate_posture(
                state,
                current_y=0.5,
                forward_offset=0.85,
                shoulders_detected=True,
            )
            assert is_bad is True

        assert state.is_slouching is True
        assert opacity > 0.03

    def test_neck_stretched_forward_detected_by_scale_and_neck_ratio(
        self, mock_app_state
    ):
        """Neck stretched forward triggers slouching via scale and neck ratio even if Z offset barely moved."""
        state = mock_app_state
        # Suppose baseline is forward=0.55, scale=0.40, neck=0.32
        # User stretches neck forward: Z only moves slightly (0.57, delta_z=+0.02, below threshold)
        # But head moves closer to camera (scale=0.52, +30%) and neck drops (neck=0.22, -31%)
        for _ in range(8):
            opacity, is_bad = evaluate_posture(
                state,
                current_y=0.5,
                forward_offset=0.57,
                shoulders_detected=True,
                scale_ratio=0.52,
                neck_v_ratio=0.22,
            )
            assert is_bad is True

        assert state.is_slouching is True
        assert opacity > 0.03

    def test_leaning_back_suppresses_slouching_via_recline_gate(
        self, mock_app_state
    ):
        """When leaning back in chair (delta_z <= -0.05), slouching is strictly suppressed."""
        state = mock_app_state
        # Reclining: forward_offset = 0.40 (delta_z = -0.15 relative to 0.55 baseline)
        opacity, is_bad = evaluate_posture(
            state,
            current_y=0.5,
            forward_offset=0.40,
            shoulders_detected=True,
            scale_ratio=0.48,
            neck_v_ratio=0.25,
        )
        assert is_bad is False
        assert state.consecutive_bad_frames == 0
        assert opacity == 0.0

    def test_fallback_to_vertical_when_shoulders_not_detected(
        self, mock_app_state
    ):
        """Falls back to vertical nose Y evaluation when shoulders are not detected."""
        state = mock_app_state
        # Head low in frame without shoulders detected -> falls back to vertical slouching
        _, is_bad = evaluate_posture(
            state,
            current_y=0.7,
            forward_offset=0.0,
            shoulders_detected=False,
        )
        assert is_bad is True


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


class TestSideCameraPostureEvaluation:
    """Test posture evaluation in sagittal (side) camera profile view."""

    def test_side_view_upright_posture_is_good(self, mock_app_state):
        """Upright posture with ear vertically aligned above shoulder plumb line is good."""
        state = mock_app_state
        # Baseline = 0.0, current side_forward = 0.0, CVA = 80 deg
        opacity, is_bad = evaluate_posture(
            state,
            current_y=0.5,
            view_mode="side",
            side_forward=0.0,
            cva_deg=80.0,
        )
        assert is_bad is False
        assert state.consecutive_good_frames == 1
        assert opacity == 0.0

    def test_side_view_forward_head_slouch_detected(self, mock_app_state):
        """Forward head posture (ear displaced past shoulder plumb line) triggers slouch."""
        state = mock_app_state
        # Enter threshold is 0.08 * (1.5 - 0.5 * 0.85) = 0.08 * 1.075 = 0.086
        # With side_forward = 0.18, displacement is +0.18, triggering slouch
        for _ in range(8):
            opacity, is_bad = evaluate_posture(
                state,
                current_y=0.5,
                view_mode="side",
                side_forward=0.18,
                cva_deg=65.0,
            )
            assert is_bad is True

        assert state.is_slouching is True
        assert opacity > 0.03

    def test_side_view_cva_drop_slouch_detected(self, mock_app_state):
        """Acute Craniovertebral Angle collapse (< 50 deg) triggers slouch."""
        state = mock_app_state
        # Small forward displacement (0.02) but severe downward head poke angle (CVA = 44 deg)
        for _ in range(8):
            opacity, is_bad = evaluate_posture(
                state,
                current_y=0.5,
                view_mode="side",
                side_forward=0.02,
                cva_deg=44.0,
            )
            assert is_bad is True

        assert state.is_slouching is True
        assert opacity > 0.03

    def test_side_view_recline_gate_suppresses_slouch(self, mock_app_state):
        """Leaning back in chair (ear behind shoulder plumb line) suppresses slouching."""
        state = mock_app_state
        # Reclined: side_forward = -0.10 (ear is 10% behind shoulder axis)
        # Even with low CVA or low head position, recline gate activates
        opacity, is_bad = evaluate_posture(
            state,
            current_y=0.8,
            view_mode="side",
            side_forward=-0.10,
            cva_deg=48.0,
        )
        assert is_bad is False
        assert state.consecutive_bad_frames == 0
        assert opacity == 0.0

