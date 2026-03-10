"""Integration tests for API endpoints.

Usage:
    uv run pytest tests/integ/test_api.py -v \
        --base-url=https://xxx.cloudfront.net \
        --admin-auth=user:pass
"""

import httpx
import pytest


@pytest.fixture(autouse=True)
def _ensure_game_stopped(base_url, admin_headers):
    """Stop game after each test to leave clean state."""
    yield
    httpx.post(f"{base_url}/api/game-state", headers=admin_headers, json={"is_active": False})


class TestGameState:
    def test_get_game_state(self, base_url):
        r = httpx.get(f"{base_url}/api/game-state")
        assert r.status_code == 200
        data = r.json()
        assert "is_active" in data

    def test_toggle_game_state(self, base_url, admin_headers):
        r = httpx.post(f"{base_url}/api/game-state", headers=admin_headers, json={"is_active": True})
        assert r.status_code == 200
        assert r.json()["is_active"] is True

        r = httpx.post(f"{base_url}/api/game-state", headers=admin_headers, json={"is_active": False})
        assert r.status_code == 200
        assert r.json()["is_active"] is False

    def test_game_state_requires_auth(self, base_url):
        r = httpx.post(f"{base_url}/api/game-state", headers={"Content-Type": "application/json"}, json={"is_active": True})
        assert r.status_code == 401


class TestProblems:
    def test_problems_empty_when_game_inactive(self, base_url, admin_headers):
        httpx.post(f"{base_url}/api/game-state", headers=admin_headers, json={"is_active": False})
        r = httpx.get(f"{base_url}/api/problems")
        assert r.status_code == 200
        data = r.json()
        assert data["game_active"] is False
        assert data["problems"] == []

    def test_problems_listed_when_game_active(self, base_url, admin_headers):
        httpx.post(f"{base_url}/api/game-state", headers=admin_headers, json={"is_active": True})
        r = httpx.get(f"{base_url}/api/problems")
        assert r.status_code == 200
        data = r.json()
        assert data["game_active"] is True


class TestProblemSetSwitching:
    def test_switching_problem_set_filters_problems(self, base_url, admin_headers):
        # Switch to "practice" -> only prime-check
        httpx.post(f"{base_url}/api/game-state", headers=admin_headers, json={"is_active": True, "problem_set": "practice"})
        r = httpx.get(f"{base_url}/api/problems")
        pids = [p["problem_id"] for p in r.json()["problems"]]
        assert "prime-check" in pids
        assert "bracket-depth" not in pids

        # Switch to "contest" -> bracket-depth, country-quiz, range-lookup but not prime-check
        httpx.post(f"{base_url}/api/game-state", headers=admin_headers, json={"is_active": True, "problem_set": "contest"})
        r = httpx.get(f"{base_url}/api/problems")
        pids = [p["problem_id"] for p in r.json()["problems"]]
        assert "bracket-depth" in pids
        assert "prime-check" not in pids


class TestLeaderboard:
    def test_get_leaderboard(self, base_url):
        r = httpx.get(f"{base_url}/api/leaderboard")
        assert r.status_code == 200
        data = r.json()
        assert "leaderboard" in data
        assert "problem_ids" in data


class TestReset:
    def test_reset_requires_auth(self, base_url):
        r = httpx.post(f"{base_url}/api/reset", headers={"Content-Type": "application/json"})
        assert r.status_code == 401

    def test_reset_clears_leaderboard(self, base_url, admin_headers):
        r = httpx.post(f"{base_url}/api/reset", headers=admin_headers)
        assert r.status_code == 200

        r = httpx.get(f"{base_url}/api/leaderboard")
        assert r.json()["leaderboard"] == []
