"""Tests for D-Bus status building."""


from conftest import MockAppState


def get_state_string(app: MockAppState) -> str:
    """Extracted state string logic from PosturedDBusAdaptor._get_state_string()."""
    if not app.is_enabled:
        return "paused"
    if app.is_calibrating:
        return "calibrating"
    if app.consecutive_no_detection >= app.AWAY_THRESHOLD:
        return "away"
    if app.is_slouching:
        return "slouching"
    return "good"


def build_status_dict(app: MockAppState) -> dict:
    """Extracted status dict logic from PosturedDBusAdaptor._build_status_dict()."""
    return {
        "state": get_state_string(app),
        "enabled": app.is_enabled,
        "is_slouching": app.is_slouching,
    }


class TestGetStateString:
    """Test _get_state_string() state determination."""

    def test_state_paused_when_not_enabled(self, mock_app_state):
        """Returns 'paused' when not enabled."""
        state = mock_app_state
        state.is_enabled = False

        result = get_state_string(state)

        assert result == "paused"

    def test_state_calibrating_during_calibration(self, mock_app_state):
        """Returns 'calibrating' during calibration."""
        state = mock_app_state
        state.is_calibrating = True

        result = get_state_string(state)

        assert result == "calibrating"

    def test_state_away_when_no_detection(self, mock_app_state):
        """Returns 'away' when no detection >= 15 frames."""
        state = mock_app_state
        state.consecutive_no_detection = 15

        result = get_state_string(state)

        assert result == "away"

    def test_state_away_threshold_is_15(self, mock_app_state):
        """Away threshold is exactly 15 frames."""
        state = mock_app_state

        state.consecutive_no_detection = 14
        assert get_state_string(state) != "away"

        state.consecutive_no_detection = 15
        assert get_state_string(state) == "away"

    def test_state_slouching_when_slouching(self, mock_app_state):
        """Returns 'slouching' when is_slouching is True."""
        state = mock_app_state
        state.is_slouching = True

        result = get_state_string(state)

        assert result == "slouching"

    def test_state_good_otherwise(self, mock_app_state):
        """Returns 'good' when none of the other conditions apply."""
        state = mock_app_state
        # All defaults: enabled, not calibrating, no away, not slouching

        result = get_state_string(state)

        assert result == "good"


class TestStatePriority:
    """Test priority order of states."""

    def test_paused_takes_precedence_over_calibrating(self, mock_app_state):
        """'paused' takes precedence over 'calibrating'."""
        state = mock_app_state
        state.is_enabled = False
        state.is_calibrating = True

        result = get_state_string(state)

        assert result == "paused"

    def test_calibrating_takes_precedence_over_away(self, mock_app_state):
        """'calibrating' takes precedence over 'away'."""
        state = mock_app_state
        state.is_calibrating = True
        state.consecutive_no_detection = 20

        result = get_state_string(state)

        assert result == "calibrating"

    def test_away_takes_precedence_over_slouching(self, mock_app_state):
        """'away' takes precedence over 'slouching'."""
        state = mock_app_state
        state.consecutive_no_detection = 20
        state.is_slouching = True

        result = get_state_string(state)

        assert result == "away"


class TestBuildStatusDict:
    """Test _build_status_dict() output."""

    def test_dict_contains_all_expected_keys(self, mock_app_state):
        """Status dict contains all expected keys."""
        state = mock_app_state

        result = build_status_dict(state)

        assert "state" in result
        assert "enabled" in result
        assert "is_slouching" in result

    def test_dict_values_match_state(self, mock_app_state):
        """Dict values correctly reflect application state."""
        state = mock_app_state
        state.is_slouching = True

        result = build_status_dict(state)

        assert result["state"] == "slouching"
        assert result["enabled"] is True
        assert result["is_slouching"] is True

    def test_dict_reflects_disabled_state(self, mock_app_state):
        """Dict correctly shows disabled state."""
        state = mock_app_state
        state.is_enabled = False

        result = build_status_dict(state)

        assert result["state"] == "paused"
        assert result["enabled"] is False
