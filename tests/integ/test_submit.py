"""Integration tests for /submit endpoint.

Usage:
    uv run pytest tests/integ/test_submit.py -v \
        --base-url=https://xxx.cloudfront.net \
        --admin-auth=user:pass
"""

import httpx
import pytest


@pytest.fixture(autouse=True)
def _game_active(base_url, admin_headers):
    """Ensure game is active for submit tests, clean up after."""
    httpx.post(f"{base_url}/api/game-state", headers=admin_headers, json={"is_active": True})
    yield
    httpx.post(f"{base_url}/api/game-state", headers=admin_headers, json={"is_active": False})


class TestSubmitCorrectness:
    def test_correct_answer(self, base_url):
        r = httpx.post(
            f"{base_url}/api/submit",
            json={"username": "integ-test", "problem_id": "prime-check", "code": "def solver(n):\n    if n < 2:\n        return False\n    for i in range(2, int(n**0.5) + 1):\n        if n % i == 0:\n            return False\n    return True"},
            timeout=60,
        )
        assert r.status_code == 200
        assert r.json()["result"] == "correct"

    def test_incorrect_answer(self, base_url):
        r = httpx.post(
            f"{base_url}/api/submit",
            json={"username": "integ-test-wrong", "problem_id": "prime-check", "code": "def solver(n):\n    return True"},
            timeout=60,
        )
        assert r.status_code == 200
        assert r.json()["result"] == "incorrect"

    def test_duplicate_correct_answer(self, base_url):
        payload = {"username": "integ-test-dup", "problem_id": "prime-check", "code": "def solver(n):\n    if n < 2:\n        return False\n    for i in range(2, int(n**0.5) + 1):\n        if n % i == 0:\n            return False\n    return True"}
        httpx.post(f"{base_url}/api/submit", json=payload, timeout=60)
        r = httpx.post(f"{base_url}/api/submit", json=payload, timeout=60)
        assert r.status_code == 200
        assert "Already solved" in r.json()["message"]


class TestSubmitValidation:
    def test_empty_username(self, base_url):
        r = httpx.post(
            f"{base_url}/api/submit",
            json={"username": "", "problem_id": "prime-check", "code": "def solver(n): return True"},
            timeout=60,
        )
        assert r.status_code == 400

    def test_username_too_long(self, base_url):
        r = httpx.post(
            f"{base_url}/api/submit",
            json={"username": "a" * 51, "problem_id": "prime-check", "code": "def solver(n): return True"},
            timeout=60,
        )
        assert r.status_code == 400

    def test_code_too_large(self, base_url):
        r = httpx.post(
            f"{base_url}/api/submit",
            json={"username": "integ-test", "problem_id": "prime-check", "code": "x" * 10_001},
            timeout=60,
        )
        assert r.status_code == 400

    def test_invalid_problem_id(self, base_url):
        r = httpx.post(
            f"{base_url}/api/submit",
            json={"username": "integ-test", "problem_id": "nonexistent", "code": "def solver(): pass"},
            timeout=60,
        )
        assert r.status_code == 400


class TestSubmitGameInactive:
    @pytest.fixture(autouse=True)
    def _stop_game(self, base_url, admin_headers):
        httpx.post(f"{base_url}/api/game-state", headers=admin_headers, json={"is_active": False})
        yield

    def test_submit_rejected_when_game_inactive(self, base_url):
        r = httpx.post(
            f"{base_url}/api/submit",
            json={"username": "integ-test", "problem_id": "prime-check", "code": "def solver(n): return True"},
            timeout=60,
        )
        assert r.status_code == 403


class TestLeaderboardReflectsSubmission:
    def test_submission_appears_in_leaderboard(self, base_url, admin_headers):
        # Reset first
        httpx.post(f"{base_url}/api/reset", headers=admin_headers)

        httpx.post(
            f"{base_url}/api/submit",
            json={"username": "integ-leaderboard-test", "problem_id": "prime-check", "code": "def solver(n):\n    if n < 2:\n        return False\n    for i in range(2, int(n**0.5) + 1):\n        if n % i == 0:\n            return False\n    return True"},
            timeout=60,
        )

        r = httpx.get(f"{base_url}/api/leaderboard")
        usernames = [e["username"] for e in r.json()["leaderboard"]]
        assert "integ-leaderboard-test" in usernames
