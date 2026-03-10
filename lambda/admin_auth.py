import hmac
import json
import os

HEADERS = {"Content-Type": "application/json"}


def require_admin_auth(event):
    """Return error response if auth fails, None if auth succeeds."""
    expected = os.environ.get("ADMIN_AUTH_TOKEN", "")
    auth = event.get("headers", {}).get("Authorization") or event.get("headers", {}).get("authorization", "")
    if not hmac.compare_digest(auth, expected):
        return {"statusCode": 401, "headers": HEADERS, "body": json.dumps({"error": "Unauthorized"})}
    return None
