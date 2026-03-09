import json
import os

import boto3

from admin_auth import require_admin_auth

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["LEADERBOARD_TABLE"])

HEADERS = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}


def handler(event, context):
    auth_error = require_admin_auth(event)
    if auth_error:
        return auth_error

    try:
        response = table.scan()
        with table.batch_writer() as batch:
            for item in response["Items"]:
                batch.delete_item(Key={"submission_id": item["submission_id"]})

        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({"message": "Leaderboard reset successfully"}),
        }
    except Exception as e:
        return {"statusCode": 500, "headers": HEADERS, "body": json.dumps({"error": str(e)})}
