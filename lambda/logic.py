"""Pure functions extracted for testability. No AWS SDK dependencies."""

from collections import defaultdict
from decimal import Decimal


def build_leaderboard(items, problem_ids):
    """Build sorted leaderboard from raw DynamoDB items."""
    user_data = defaultdict(dict)
    for item in items:
        user_data[item["username"]][item["problem_id"]] = item.get("timestamp", "")

    result = []
    for username, solved in user_data.items():
        entry = {"username": username}
        valid_times = []
        for pid in problem_ids:
            ts = solved.get(pid)
            if ts:
                parts = ts.split(" ")
                entry[pid] = parts[1] if len(parts) >= 2 else ts
                valid_times.append(ts)
            else:
                entry[pid] = None
        entry["solved_count"] = len(valid_times)
        entry["latest_time"] = max(valid_times) if valid_times else None
        result.append(entry)

    result.sort(key=lambda x: (-x["solved_count"], x["latest_time"] or "z"))
    return result


def decimal_default(obj):
    """JSON serializer for Decimal types."""
    if isinstance(obj, Decimal):
        return int(obj)
    raise TypeError
