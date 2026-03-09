import json
import os

import boto3

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
game_state_table = dynamodb.Table(os.environ["GAME_STATE_TABLE"])
problems_bucket = os.environ["PROBLEMS_BUCKET"]


def handler(event, context):
    try:
        game_state = game_state_table.get_item(Key={"state_key": "game_active"})
        is_active = game_state.get("Item", {}).get("value", False)

        if not is_active:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"problems": [], "game_active": False}),
            }

        paginator = s3.get_paginator("list_objects_v2")
        problems = {}
        for page in paginator.paginate(Bucket=problems_bucket, Delimiter="/"):
            for prefix in page.get("CommonPrefixes", []):
                problem_id = prefix["Prefix"].rstrip("/")
                try:
                    obj = s3.get_object(Bucket=problems_bucket, Key=f"{problem_id}/metadata.json")
                    metadata = json.loads(obj["Body"].read())
                except Exception:
                    continue
                if metadata.get("enabled", False):
                    problems[problem_id] = metadata

        sorted_problems = sorted(problems.items(), key=lambda x: x[1].get("order", 999))
        result = [{"problem_id": pid, **meta} for pid, meta in sorted_problems]

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"problems": result, "game_active": True}, ensure_ascii=False),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": str(e)}),
        }
