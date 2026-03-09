import json
import os

import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["GAME_STATE_TABLE"])

HEADERS = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}


def handler(event, context):
    try:
        http_method = event["httpMethod"]

        if http_method == "GET":
            response = table.get_item(Key={"state_key": "game_active"})
            is_active = response.get("Item", {}).get("value", False)
            return {"statusCode": 200, "headers": HEADERS, "body": json.dumps({"is_active": is_active})}

        elif http_method == "POST":
            body = json.loads(event["body"])
            is_active = body.get("is_active", True)
            table.put_item(Item={"state_key": "game_active", "value": is_active})
            return {
                "statusCode": 200,
                "headers": HEADERS,
                "body": json.dumps({"message": "Game state updated", "is_active": is_active}),
            }

        return {"statusCode": 405, "headers": HEADERS, "body": json.dumps({"error": "Method not allowed"})}
    except Exception as e:
        return {"statusCode": 500, "headers": HEADERS, "body": json.dumps({"error": str(e)})}
