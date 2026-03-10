import json
import os
import traceback
from collections import defaultdict
from decimal import Decimal

import boto3

from admin_auth import require_admin_auth

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

leaderboard_table = dynamodb.Table(os.environ["LEADERBOARD_TABLE"])
game_state_table = dynamodb.Table(os.environ["GAME_STATE_TABLE"])
problems_bucket = os.environ["PROBLEMS_BUCKET"]

HEADERS = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}


def handler(event, context):
    resource = event.get("resource", "")
    method = event.get("httpMethod", "")

    try:
        if resource == "/leaderboard" and method == "GET":
            return _get_leaderboard()
        elif resource == "/problems" and method == "GET":
            return _get_problems()
        elif resource == "/game-state" and method == "GET":
            return _get_game_state()
        elif resource == "/game-state" and method == "POST":
            return _require_auth_then(event, lambda: _set_game_state(event))
        elif resource == "/reset" and method == "POST":
            return _require_auth_then(event, _reset_leaderboard)
        else:
            return _response(404, {"error": "Not found"})
    except Exception as e:
        print(f"Error: {e}")
        print(traceback.format_exc())
        return _response(500, {"error": str(e)})


def _require_auth_then(event, fn):
    auth_error = require_admin_auth(event)
    if auth_error:
        return auth_error
    return fn()


def _response(status, body):
    return {"statusCode": status, "headers": HEADERS, "body": json.dumps(body, default=_decimal_default, ensure_ascii=False)}


def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj)
    raise TypeError


# --- Leaderboard ---

def _get_leaderboard():
    problem_ids = _get_enabled_problem_ids()
    items = leaderboard_table.scan().get("Items", [])

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
    return _response(200, {"leaderboard": result, "problem_ids": problem_ids})


def _reset_leaderboard():
    response = leaderboard_table.scan()
    with leaderboard_table.batch_writer() as batch:
        for item in response["Items"]:
            batch.delete_item(Key={"submission_id": item["submission_id"]})
    return _response(200, {"message": "Leaderboard reset successfully"})


# --- Game State ---

def _get_game_state():
    response = game_state_table.get_item(Key={"state_key": "game_active"})
    is_active = response.get("Item", {}).get("value", False)
    ps_response = game_state_table.get_item(Key={"state_key": "active_problem_set"})
    problem_set = ps_response.get("Item", {}).get("value", "")
    problem_sets = _get_all_problem_sets()
    return _response(200, {"is_active": is_active, "problem_set": problem_set, "problem_sets": problem_sets})


def _set_game_state(event):
    body = json.loads(event["body"])
    is_active = body.get("is_active", True)
    problem_set = body.get("problem_set")
    game_state_table.put_item(Item={"state_key": "game_active", "value": is_active})
    if problem_set is not None:
        game_state_table.put_item(Item={"state_key": "active_problem_set", "value": problem_set})
    ps_response = game_state_table.get_item(Key={"state_key": "active_problem_set"})
    current_ps = ps_response.get("Item", {}).get("value", "")
    return _response(200, {"message": "Game state updated", "is_active": is_active, "problem_set": current_ps})


# --- Problems ---

def _get_problems():
    game_state = game_state_table.get_item(Key={"state_key": "game_active"})
    is_active = game_state.get("Item", {}).get("value", False)

    if not is_active:
        return _response(200, {"problems": [], "game_active": False})

    problem_ids_with_meta = _get_enabled_problems()
    result = [{"problem_id": pid, **meta} for pid, meta in problem_ids_with_meta]
    return _response(200, {"problems": result, "game_active": True})


# --- Shared ---

def _get_enabled_problem_ids():
    return [pid for pid, _ in _get_enabled_problems()]


def _get_active_problem_set():
    response = game_state_table.get_item(Key={"state_key": "active_problem_set"})
    return response.get("Item", {}).get("value", "")


def _get_all_problem_sets():
    """Return sorted unique problem_set values from all enabled problems."""
    paginator = s3.get_paginator("list_objects_v2")
    sets = set()
    for page in paginator.paginate(Bucket=problems_bucket, Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            pid = prefix["Prefix"].rstrip("/")
            try:
                obj = s3.get_object(Bucket=problems_bucket, Key=f"{pid}/metadata.json")
                metadata = json.loads(obj["Body"].read())
                if metadata.get("enabled", False):
                    for ps in metadata.get("problem_set", []):
                        sets.add(ps)
            except Exception:
                continue
    return sorted(sets)


def _get_enabled_problems():
    active_ps = _get_active_problem_set()
    paginator = s3.get_paginator("list_objects_v2")
    problems = []
    for page in paginator.paginate(Bucket=problems_bucket, Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            pid = prefix["Prefix"].rstrip("/")
            try:
                obj = s3.get_object(Bucket=problems_bucket, Key=f"{pid}/metadata.json")
                metadata = json.loads(obj["Body"].read())
                if not metadata.get("enabled", False):
                    continue
                if active_ps not in metadata.get("problem_set", []):
                    continue
                problems.append((pid, metadata))
            except Exception:
                continue
    problems.sort(key=lambda x: x[1].get("order", 999))
    return problems
