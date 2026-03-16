"""Unit tests for rate_limit module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from rate_limit import check_rate_limit


@pytest.fixture
def mock_table():
    return MagicMock()


class TestCheckRateLimit:
    @patch.dict("os.environ", {"RATE_LIMIT_COOLDOWN": "10"})
    def test_first_request_allowed(self, mock_table):
        mock_table.get_item.return_value = {}
        result = check_rate_limit(mock_table, "user1")
        assert result is None
        mock_table.put_item.assert_called_once()

    @patch.dict("os.environ", {"RATE_LIMIT_COOLDOWN": "10"})
    def test_within_cooldown_rejected(self, mock_table):
        now = datetime.now(timezone.utc)
        mock_table.get_item.return_value = {"Item": {"state_key": "rate:user1", "value": now.isoformat()}}
        result = check_rate_limit(mock_table, "user1")
        assert result is not None
        assert result["statusCode"] == 429
        assert "retry_after" in result["body"]

    @patch.dict("os.environ", {"RATE_LIMIT_COOLDOWN": "10"})
    def test_after_cooldown_allowed(self, mock_table):
        old_time = datetime.now(timezone.utc) - timedelta(seconds=11)
        mock_table.get_item.return_value = {"Item": {"state_key": "rate:user1", "value": old_time.isoformat()}}
        result = check_rate_limit(mock_table, "user1")
        assert result is None
        mock_table.put_item.assert_called_once()

    @patch.dict("os.environ", {"RATE_LIMIT_COOLDOWN": "5"})
    def test_custom_cooldown(self, mock_table):
        old_time = datetime.now(timezone.utc) - timedelta(seconds=6)
        mock_table.get_item.return_value = {"Item": {"state_key": "rate:user1", "value": old_time.isoformat()}}
        result = check_rate_limit(mock_table, "user1")
        assert result is None

    @patch.dict("os.environ", {"RATE_LIMIT_COOLDOWN": "10"})
    def test_no_item_key(self, mock_table):
        """When get_item returns no Item key at all."""
        mock_table.get_item.return_value = {}
        result = check_rate_limit(mock_table, "newuser")
        assert result is None
