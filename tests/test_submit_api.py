"""Integration tests for /submit API using schemathesis.

Usage:
    uv run pytest tests/test_submit_api.py --base-url=https://xxx.execute-api.ap-northeast-1.amazonaws.com/prod/
"""

import schemathesis
from pathlib import Path

schema = schemathesis.openapi.from_path(
    Path(__file__).resolve().parent.parent / "website" / "openapi.yaml",
)


@schema.parametrize()
def test_submit_api(case):
    case.call_and_validate()
