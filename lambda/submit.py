import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3

dynamodb = boto3.resource("dynamodb")
bedrock_agentcore = boto3.client("bedrock-agentcore")
s3 = boto3.client("s3")
table = dynamodb.Table(os.environ["LEADERBOARD_TABLE"])
game_state_table = dynamodb.Table(os.environ["GAME_STATE_TABLE"])
code_interpreter_id = os.environ["CODE_INTERPRETER_ID"]
problems_bucket = os.environ["PROBLEMS_BUCKET"]

HEADERS = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}

RUNNER_CODE = """
import unittest
import sys
import io

loader = unittest.TestLoader()
suite = loader.loadTestsFromModule(__import__('test_solver'))
stream = io.StringIO()
runner = unittest.TextTestRunner(stream=stream, verbosity=0)
result = runner.run(suite)
print(f"{result.testsRun - len(result.failures) - len(result.errors)}/{result.testsRun}")
"""


def _get_metadata(problem_id):
    try:
        obj = s3.get_object(Bucket=problems_bucket, Key=f"{problem_id}/metadata.json")
        return json.loads(obj["Body"].read())
    except Exception:
        return None


def _get_test_code(problem_id):
    obj = s3.get_object(Bucket=problems_bucket, Key=f"{problem_id}/test_solver.py")
    return obj["Body"].read().decode()


def _run_tests(user_code, test_code):
    session_id = None
    try:
        session = bedrock_agentcore.start_code_interpreter_session(
            codeInterpreterIdentifier=code_interpreter_id,
            name="solver-session",
            sessionTimeoutSeconds=60,
        )
        session_id = session["sessionId"]

        bedrock_agentcore.invoke_code_interpreter(
            codeInterpreterIdentifier=code_interpreter_id,
            sessionId=session_id,
            name="writeFiles",
            arguments={
                "content": [
                    {"path": "solver.py", "text": user_code},
                    {"path": "test_solver.py", "text": test_code},
                ]
            },
        )

        response = bedrock_agentcore.invoke_code_interpreter(
            codeInterpreterIdentifier=code_interpreter_id,
            sessionId=session_id,
            name="executeCode",
            arguments={"language": "python", "code": RUNNER_CODE},
        )

        output = ""
        for event in response["stream"]:
            if "result" in event and "content" in event["result"]:
                for content in event["result"]["content"]:
                    if content["type"] == "text":
                        output += content["text"]

        return output.strip(), None
    except Exception as e:
        return None, str(e)
    finally:
        if session_id:
            try:
                bedrock_agentcore.stop_code_interpreter_session(
                    codeInterpreterIdentifier=code_interpreter_id,
                    sessionId=session_id,
                )
            except Exception:
                pass


def handler(event, context):
    try:
        game_state = game_state_table.get_item(Key={"state_key": "game_active"})
        if not game_state.get("Item", {}).get("value", False):
            return {"statusCode": 403, "headers": HEADERS, "body": json.dumps({"error": "Game is not active."})}

        body = json.loads(event["body"])
        username = body["username"]
        problem_id = body["problem_id"]
        code = body["code"]

        metadata = _get_metadata(problem_id)
        if not metadata or not metadata.get("enabled", False):
            return {
                "statusCode": 400,
                "headers": HEADERS,
                "body": json.dumps({"error": f"Problem '{problem_id}' does not exist or is disabled."}),
            }

        code = code.replace("\\n", "\n").replace("\\t", "\t")
        test_code = _get_test_code(problem_id)
        result_str, error = _run_tests(code, test_code)

        if error:
            return {
                "statusCode": 200,
                "headers": HEADERS,
                "body": json.dumps({"result": "error", "message": f"Execution error: {error}"}),
            }

        # Parse "passed/total" format
        parts = result_str.split("/")
        if len(parts) != 2:
            return {
                "statusCode": 200,
                "headers": HEADERS,
                "body": json.dumps({"result": "error", "message": "Unexpected output format."}),
            }

        passed, total = int(parts[0]), int(parts[1])
        is_correct = passed == total

        if is_correct:
            existing = table.scan(
                FilterExpression="username = :u AND problem_id = :p",
                ExpressionAttributeValues={":u": username, ":p": problem_id},
            )
            if existing["Items"]:
                return {
                    "statusCode": 200,
                    "headers": HEADERS,
                    "body": json.dumps({"result": "correct", "message": f"Already solved. {passed}/{total} passed."}),
                }

            jst = timezone(timedelta(hours=9))
            timestamp = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S JST")
            submission_id = str(uuid.uuid4())

            table.put_item(
                Item={
                    "submission_id": submission_id,
                    "username": username,
                    "problem_id": problem_id,
                    "timestamp": timestamp,
                }
            )

            return {
                "statusCode": 200,
                "headers": HEADERS,
                "body": json.dumps(
                    {
                        "result": "correct",
                        "message": f"Congratulations! {passed}/{total} passed.",
                        "submission_id": submission_id,
                    }
                ),
            }
        else:
            return {
                "statusCode": 200,
                "headers": HEADERS,
                "body": json.dumps({"result": "incorrect", "message": f"{passed}/{total} passed."}),
            }
    except Exception as e:
        return {"statusCode": 500, "headers": HEADERS, "body": json.dumps({"error": str(e)})}
