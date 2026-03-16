import json
import os

import boto3
from rate_limit import check_rate_limit

dynamodb = boto3.resource("dynamodb")
bedrock_agentcore = boto3.client("bedrock-agentcore")
s3 = boto3.client("s3")
game_state_table = dynamodb.Table(os.environ["GAME_STATE_TABLE"])
code_interpreter_id = "aws.codeinterpreter.v1"
problems_bucket = os.environ["PROBLEMS_BUCKET"]

HEADERS = {"Content-Type": "application/json"}
MAX_CODE_SIZE = 10_000
MAX_USERNAME_LENGTH = 50
CTF_ENV_PREFIX = "ctf-env/"


def _get_ctf_files():
    """Get all files under ctf-env/ prefix from S3, returning list of (key_basename, body_bytes)."""
    files = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=problems_bucket, Prefix=CTF_ENV_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            basename = key[len(CTF_ENV_PREFIX):]
            if not basename or basename == "env.json":
                continue
            body = s3.get_object(Bucket=problems_bucket, Key=key)["Body"].read()
            files.append((basename, body))
    return files


def _get_env_config():
    """Get env.json from S3 for environment variable setup."""
    try:
        obj = s3.get_object(Bucket=problems_bucket, Key=f"{CTF_ENV_PREFIX}env.json")
        return json.loads(obj["Body"].read())
    except Exception:
        return {}


def handler(event, context):
    try:
        game_state = game_state_table.get_item(Key={"state_key": "game_active"})
        if not game_state.get("Item", {}).get("value", False):
            return {"statusCode": 403, "headers": HEADERS, "body": json.dumps({"error": "Game is not active."})}

        body = json.loads(event["body"])
        username = body.get("username", "").strip()
        code = body.get("code", "")

        if not username or len(username) > MAX_USERNAME_LENGTH:
            return {"statusCode": 400, "headers": HEADERS, "body": json.dumps({"error": "Invalid username."})}
        if not code or len(code) > MAX_CODE_SIZE:
            return {"statusCode": 400, "headers": HEADERS, "body": json.dumps({"error": "Invalid code."})}

        rate_error = check_rate_limit(game_state_table, username)
        if rate_error:
            return rate_error

        session_id = None
        try:
            session = bedrock_agentcore.start_code_interpreter_session(
                codeInterpreterIdentifier=code_interpreter_id,
                name="explore-session",
                sessionTimeoutSeconds=60,
            )
            session_id = session["sessionId"]

            # Write CTF files (excluding env.json)
            ctf_files = _get_ctf_files()
            if ctf_files:
                import base64

                text_files = []
                binary_files = []
                for basename, file_bytes in ctf_files:
                    try:
                        text_files.append({"path": basename, "text": file_bytes.decode("utf-8")})
                    except UnicodeDecodeError:
                        binary_files.append((basename, base64.b64encode(file_bytes).decode()))

                if text_files:
                    bedrock_agentcore.invoke_code_interpreter(
                        codeInterpreterIdentifier=code_interpreter_id,
                        sessionId=session_id,
                        name="writeFiles",
                        arguments={"content": text_files},
                    )

                # Write binary files via executeCode (writeFiles blob doesn't preserve binary)
                for basename, b64data in binary_files:
                    decode_code = (
                        f"import base64\n"
                        f"with open({basename!r}, 'wb') as f:\n"
                        f"    f.write(base64.b64decode({b64data!r}))"
                    )
                    bedrock_agentcore.invoke_code_interpreter(
                        codeInterpreterIdentifier=code_interpreter_id,
                        sessionId=session_id,
                        name="executeCode",
                        arguments={"language": "python", "code": decode_code},
                    )

            # Set environment variables from env.json
            env_config = _get_env_config()
            if env_config:
                env_lines = "; ".join(f'os.environ["{k}"] = "{v}"' for k, v in env_config.items())
                setup_code = f"import os; {env_lines}"
                bedrock_agentcore.invoke_code_interpreter(
                    codeInterpreterIdentifier=code_interpreter_id,
                    sessionId=session_id,
                    name="executeCode",
                    arguments={"language": "python", "code": setup_code},
                )

            # Execute user code
            response = bedrock_agentcore.invoke_code_interpreter(
                codeInterpreterIdentifier=code_interpreter_id,
                sessionId=session_id,
                name="executeCode",
                arguments={"language": "python", "code": code},
            )

            stdout = ""
            stderr = ""
            exit_code = 0

            for event_data in response["stream"]:
                if "result" in event_data:
                    result = event_data["result"]
                    sc = result.get("structuredContent")
                    if sc:
                        stdout = sc.get("stdout", "")
                        stderr = sc.get("stderr", "")
                        exit_code = sc.get("exitCode", 0)
                    elif not stdout:
                        for content in result.get("content", []):
                            if content["type"] == "text":
                                stdout += content["text"]

            return {
                "statusCode": 200,
                "headers": HEADERS,
                "body": json.dumps({"stdout": stdout, "stderr": stderr, "exit_code": exit_code}),
            }
        finally:
            if session_id:
                try:
                    bedrock_agentcore.stop_code_interpreter_session(
                        codeInterpreterIdentifier=code_interpreter_id,
                        sessionId=session_id,
                    )
                except Exception:
                    pass
    except Exception as e:
        return {"statusCode": 500, "headers": HEADERS, "body": json.dumps({"error": str(e)})}
