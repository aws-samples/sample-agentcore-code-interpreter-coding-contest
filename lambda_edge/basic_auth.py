import base64

import boto3

ssm = boto3.client("ssm", region_name="us-east-1")

_cached_credentials = None


def _get_credentials():
    global _cached_credentials
    if _cached_credentials is None:
        username = ssm.get_parameter(Name="/coding-contest/admin-username")["Parameter"]["Value"]
        password = ssm.get_parameter(Name="/coding-contest/admin-password")["Parameter"]["Value"]
        auth_string = f"{username}:{password}"
        _cached_credentials = f"Basic {base64.b64encode(auth_string.encode()).decode()}"
    return _cached_credentials


def handler(event, context):
    request = event["Records"][0]["cf"]["request"]
    uri = request["uri"]

    if uri != "/admin.html" and not uri.endswith("/admin.html"):
        return request

    required_auth = _get_credentials()
    headers = request["headers"]

    if "authorization" in headers and headers["authorization"][0]["value"] == required_auth:
        return request

    return {
        "status": "401",
        "statusDescription": "Unauthorized",
        "headers": {"www-authenticate": [{"key": "WWW-Authenticate", "value": 'Basic realm="Admin Area"'}]},
    }
