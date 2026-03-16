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


def _list_active_ctf_subdirs():
    """List CTF subdirectory names that belong to the active problem set.

    Reads metadata.json from contents/ctf-<name>/ in S3 to check problem_set.
    Convention: ctf-<name> in contents/ corresponds to <name> in ctf-env/.
    """
    active_ps = game_state_table.get_item(Key={"state_key": "active_problem_set"}).get("Item", {}).get("value", "")

    subdirs = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=problems_bucket, Prefix=CTF_ENV_PREFIX, Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            name = prefix["Prefix"][len(CTF_ENV_PREFIX):].rstrip("/")
            if name:
                subdirs.add(name)

    if not active_ps:
        return subdirs

    active = set()
    for name in subdirs:
        try:
            obj = s3.get_object(Bucket=problems_bucket, Key=f"ctf-{name}/metadata.json")
            metadata = json.loads(obj["Body"].read())
            if active_ps in metadata.get("problem_set", []):
                active.add(name)
        except Exception:
            pass
    return active


def _get_ctf_files_for_subdir(subdir):
    """Get files for a CTF subdir, returning (sandbox_files, env_config, setup_code).

    sandbox_files: list of (basename, body_bytes) — only files under assets/
    env_config: dict from env.json (or {})
    setup_code: str content of setup.py (or None)
    """
    prefix = f"{CTF_ENV_PREFIX}{subdir}/"
    assets_prefix = f"{prefix}assets/"
    sandbox_files = []
    env_config = {}
    setup_code = None

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=problems_bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            basename = key[len(prefix):]
            if not basename:
                continue
            if key.startswith(assets_prefix):
                # Files under assets/ go into sandbox
                asset_name = key[len(assets_prefix):]
                if asset_name:
                    body = s3.get_object(Bucket=problems_bucket, Key=key)["Body"].read()
                    sandbox_files.append((asset_name, body))
            elif basename == "env.json":
                body = s3.get_object(Bucket=problems_bucket, Key=key)["Body"].read()
                try:
                    env_config = json.loads(body)
                except Exception:
                    pass
            elif basename == "setup.py":
                body = s3.get_object(Bucket=problems_bucket, Key=key)["Body"].read()
                setup_code = body.decode("utf-8")

    return sandbox_files, env_config, setup_code


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

            # Set up CTF environment using writeFiles/executeCommand/removeFiles
            # to avoid leaking secrets into IPython history and globals
            import base64

            _invoke = lambda name, args: bedrock_agentcore.invoke_code_interpreter(
                codeInterpreterIdentifier=code_interpreter_id,
                sessionId=session_id,
                name=name,
                arguments=args,
            )

            for subdir in sorted(_list_active_ctf_subdirs()):
                ctf_files, env_config, setup_code = _get_ctf_files_for_subdir(subdir)

                # Write sandbox files (from assets/)
                if ctf_files:
                    text_files = []
                    binary_files = []
                    for basename, file_bytes in ctf_files:
                        try:
                            text_files.append({"path": basename, "text": file_bytes.decode("utf-8")})
                        except UnicodeDecodeError:
                            binary_files.append((basename, base64.b64encode(file_bytes).decode()))

                    if text_files:
                        _invoke("writeFiles", {"content": text_files})

                    # Write binary files via shell command (not executeCode)
                    for basename, b64data in binary_files:
                        _invoke("executeCommand", {
                            "command": f"python3 -c \"import base64; open('{basename}','wb').write(base64.b64decode('{b64data}'))\""
                        })

                # Set environment variables via executeCode (needed for IPython process)
                if env_config:
                    env_lines = "; ".join(f'os.environ["{k}"] = "{v}"' for k, v in env_config.items())
                    _invoke("executeCode", {"language": "python", "code": f"import os; {env_lines}"})

                # Run setup script via executeCode (must use IPython process for persistent threads)
                # Wrap in exec() to avoid polluting globals, then clear history
                if setup_code:
                    wrapped = f"exec({setup_code!r}, {{}})"
                    _invoke("executeCode", {"language": "python", "code": wrapped})

            # Clear IPython history and residual variables from setup
            _invoke("executeCode", {"language": "python", "code": (
                "try:\n"
                "    _ip = get_ipython()\n"
                "    _ip.history_manager.reset()\n"
                "    _ip.displayhook.prompt_count = 0\n"
                "    In[:] = ['']\n"
                "    Out.clear()\n"
                "    for _k in list(globals()):\n"
                "        if _k.startswith('_i') and _k not in ('_ih',):\n"
                "            try: del globals()[_k]\n"
                "            except: pass\n"
                "    del _ip, _k\n"
                "except: pass\n"
            )})

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
