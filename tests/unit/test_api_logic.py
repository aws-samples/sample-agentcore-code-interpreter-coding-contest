from decimal import Decimal

import pytest

from logic import build_leaderboard, decimal_default


class TestBuildLeaderboard:
    def test_sort_by_solved_count_desc(self):
        items = [
            {"username": "alice", "problem_id": "p1", "timestamp": "2026-03-10 10:00:00 JST"},
            {"username": "bob", "problem_id": "p1", "timestamp": "2026-03-10 10:01:00 JST"},
            {"username": "bob", "problem_id": "p2", "timestamp": "2026-03-10 10:02:00 JST"},
        ]
        result = build_leaderboard(items, ["p1", "p2"])
        assert result[0]["username"] == "bob"
        assert result[0]["solved_count"] == 2
        assert result[1]["username"] == "alice"
        assert result[1]["solved_count"] == 1

    def test_sort_by_latest_time_asc_on_tie(self):
        items = [
            {"username": "alice", "problem_id": "p1", "timestamp": "2026-03-10 10:05:00 JST"},
            {"username": "bob", "problem_id": "p1", "timestamp": "2026-03-10 10:01:00 JST"},
        ]
        result = build_leaderboard(items, ["p1"])
        assert result[0]["username"] == "bob"
        assert result[1]["username"] == "alice"

    def test_unsolved_is_none(self):
        items = [
            {"username": "alice", "problem_id": "p1", "timestamp": "2026-03-10 10:00:00 JST"},
        ]
        result = build_leaderboard(items, ["p1", "p2"])
        assert result[0]["p1"] == "10:00:00"
        assert result[0]["p2"] is None

    def test_empty_items(self):
        assert build_leaderboard([], ["p1"]) == []

    def test_time_display_extracts_hms(self):
        items = [
            {"username": "alice", "problem_id": "p1", "timestamp": "2026-03-10 14:30:59 JST"},
        ]
        result = build_leaderboard(items, ["p1"])
        assert result[0]["p1"] == "14:30:59"

    def test_timestamp_without_space_used_as_is(self):
        items = [
            {"username": "alice", "problem_id": "p1", "timestamp": "14:30:59"},
        ]
        result = build_leaderboard(items, ["p1"])
        assert result[0]["p1"] == "14:30:59"


class TestDecimalDefault:
    def test_decimal_to_int(self):
        assert decimal_default(Decimal("42")) == 42

    def test_non_decimal_raises(self):
        with pytest.raises(TypeError):
            decimal_default("not a decimal")
