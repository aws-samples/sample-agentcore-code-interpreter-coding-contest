import boto3
import pytest

DEFAULT_STACK_NAME = "ProgrammingContestStack"


def pytest_addoption(parser):
    parser.addoption("--stack-name", default=DEFAULT_STACK_NAME, help="CloudFormation stack name")


def _get_stack_outputs(stack_name):
    cfn = boto3.client("cloudformation")
    resp = cfn.describe_stacks(StackName=stack_name)
    outputs = resp["Stacks"][0]["Outputs"]
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


@pytest.fixture(scope="session")
def stack_outputs(request):
    return _get_stack_outputs(request.config.getoption("--stack-name"))


@pytest.fixture(scope="session")
def base_url(stack_outputs):
    return stack_outputs["WebsiteUrl"].rstrip("/")


@pytest.fixture(scope="session")
def admin_headers(stack_outputs):
    return {"Content-Type": "application/json", "Authorization": stack_outputs["AdminAuthToken"]}


@pytest.fixture(scope="session")
def admin_credentials(stack_outputs):
    """Plain text 'user:pass' for browser prompt input."""
    return stack_outputs["AdminCredentials"]
