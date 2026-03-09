import json
import os
import traceback
from collections import defaultdict
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
table = dynamodb.Table(os.environ["LEADERBOARD_TABLE"])
problems_bucket = os.environ["PROBLEMS_BUCKET"]

HEADERS = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}


def _get_enabled_problem_ids():
    paginator = s3.get_paginator("list_objects_v2")
    problem_ids = []
    for page in paginator.paginate(Bucket=problems_bucket, Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            pid = prefix["Prefix"].rstrip("/")
            try:
                obj = s3.get_object(Bucket=problems_bucket, Key=f"{pid}/metadata.json")
                metadata = json.loads(obj["Body"].read())
                if metadata.get("enabled", False):
                    problem_ids.append((pid, metadata.get("order", 999)))
            except Exception:
                continue
    problem_ids.sort(key=lambda x: x[1])
    return [pid for pid, _ in problem_ids]


def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj)
    raise TypeError


def handler(event, context):
    try:
        problem_ids = _get_enabled_problem_ids()

        response = table.scan()
        items = response.get("Items", [])

        user_data = defaultdict(dict)
        for item in items:
            username = item.get("username", "")
            problem_id = item.get("problem_id", "")
            timestamp = item.get("timestamp", "")
            user_data[username][problem_id] = timestamp

        result = []
        for username, solved in user_data.items():
            entry = {"username": username}
            valid_times = []
            for pid in problem_ids:
                ts = solved.get(pid)
                if ts:
                    # "YYYY-MM-DD HH:MM:SS JST" -> "HH:MM:SS"
                    parts = ts.split(" ")
                    entry[pid] = parts[1] if len(parts) >= 2 else ts
                    valid_times.append(ts)
                else:
                    entry[pid] = None

            entry["solved_count"] = len(valid_times)
            entry["latest_time"] = max(valid_times) if valid_times else None
            result.append(entry)

        result.sort(key=lambda x: (-x["solved_count"], x["latest_time"] or "z"))

        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({"leaderboard": result, "problem_ids": problem_ids}, default=_decimal_default),
        }
    except Exception as e:
        print(f"Error: {e}")
        print(traceback.format_exc())
        return {"statusCode": 500, "headers": HEADERS, "body": json.dumps({"error": str(e)})}
