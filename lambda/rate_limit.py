"""Rate limiting module shared by /api/explore and /api/submit."""

import json
import os
from datetime import datetime, timezone

HEADERS = {"Content-Type": "application/json"}


def check_rate_limit(game_state_table, username):
    """Check rate limit for username. Returns error response dict if limited, None if allowed."""
    cooldown = int(os.environ.get("RATE_LIMIT_COOLDOWN", "10"))
    state_key = f"rate:{username}"

    item = game_state_table.get_item(Key={"state_key": state_key}).get("Item")
    now = datetime.now(timezone.utc)

    if item:
        last_time = datetime.fromisoformat(item["value"])
        elapsed = (now - last_time).total_seconds()
        if elapsed < cooldown:
            retry_after = int(cooldown - elapsed) + 1
            body = json.dumps({
                "error": f"Rate limited. Please wait {retry_after} seconds.",
                "retry_after": retry_after,
            })
            return {"statusCode": 429, "headers": HEADERS, "body": body}

    game_state_table.put_item(Item={"state_key": state_key, "value": now.isoformat()})
    return None
