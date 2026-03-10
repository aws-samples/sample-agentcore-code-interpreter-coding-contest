import json
import os
import traceback

import boto3

from admin_auth import require_admin_auth
from logic import build_leaderboard, decimal_default

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

leaderboard_table = dynamodb.Table(os.environ["LEADERBOARD_TABLE"])
game_state_table = dynamodb.Table(os.environ["GAME_STATE_TABLE"])
problems_bucket = os.environ["PROBLEMS_BUCKET"]

HEADERS = {"Content-Type": "application/json"}

# Module-level cache for enabled problems (reused across warm Lambda invocations)
_problems_cache = {"data": None, "problem_set": None}


def handler(event, context):
    resource = event.get("resource", "")
    method = event.get("httpMethod", "")

    try:
        if resource == "/api/leaderboard" and method == "GET":
            return _get_leaderboard()
        elif resource == "/api/problems" and method == "GET":
            return _get_problems()
        elif resource == "/api/game-state" and method == "GET":
            auth_error = require_admin_auth(event)
            if auth_error:
                return _get_game_state()
            return _get_game_state_admin()
        elif resource == "/api/game-state" and method == "POST":
            return _require_auth_then(event, lambda: _set_game_state(event))
        elif resource == "/api/reset" and method == "POST":
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
    return {"statusCode": status, "headers": HEADERS, "body": json.dumps(body, default=decimal_default, ensure_ascii=False)}


# --- Leaderboard ---

def _scan_all(table_resource):
    """Scan all items with pagination."""
    items = []
    scan_kwargs = {}
    while True:
        response = table_resource.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def _get_leaderboard():
    problem_ids = _get_enabled_problem_ids()
    items = _scan_all(leaderboard_table)
    result = build_leaderboard(items, problem_ids)
    return _response(200, {"leaderboard": result, "problem_ids": problem_ids})


def _reset_leaderboard():
    _problems_cache["data"] = None  # Invalidate cache
    scan_kwargs = {}
    while True:
        response = leaderboard_table.scan(**scan_kwargs)
        with leaderboard_table.batch_writer() as batch:
            for item in response["Items"]:
                batch.delete_item(Key={"problem_id": item["problem_id"], "username": item["username"]})
        if "LastEvaluatedKey" not in response:
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return _response(200, {"message": "Leaderboard reset successfully"})


# --- Game State ---

def _get_game_state():
    response = game_state_table.get_item(Key={"state_key": "game_active"})
    is_active = response.get("Item", {}).get("value", False)
    return _response(200, {"is_active": is_active})


def _get_game_state_admin():
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
    _problems_cache["data"] = None  # Invalidate cache on state change
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
    """Return enabled problems for the active problem set, with module-level caching."""
    active_ps = _get_active_problem_set()
    if _problems_cache["data"] is not None and _problems_cache["problem_set"] == active_ps:
        return _problems_cache["data"]

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
    _problems_cache["data"] = problems
    _problems_cache["problem_set"] = active_ps
    return problems
