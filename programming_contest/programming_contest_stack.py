import base64
import subprocess
import sys

from aws_cdk import (
    CfnOutput,
    CustomResource,
    Duration,
    Stack,
)
from aws_cdk import (
    aws_apigateway as apigw,
)
from aws_cdk import (
    aws_bedrockagentcore as agentcore,
)
from aws_cdk import (
    aws_cloudfront as cloudfront,
)
from aws_cdk import (
    aws_cloudfront_origins as origins,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as _lambda,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_s3_deployment as s3deploy,
)
from aws_cdk import (
    custom_resources as cr,
)
from constructs import Construct


class ProgrammingContestStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        admin_username: str = "admin",
        admin_password: str = "password",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Run build script to prepare deployment sources
        subprocess.run([sys.executable, "scripts/build_contents.py"], check=True)

        # DynamoDB tables
        leaderboard_table = dynamodb.Table(
            self,
            "LeaderboardTable",
            partition_key=dynamodb.Attribute(name="submission_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        game_state_table = dynamodb.Table(
            self,
            "GameStateTable",
            partition_key=dynamodb.Attribute(name="state_key", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        # Initialize game state to false
        init_lambda = _lambda.SingletonFunction(
            self,
            "InitGameState",
            uuid="init-game-state",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=_lambda.Code.from_inline(
                """
import boto3
import json

def handler(event, context):
    if event['RequestType'] == 'Create':
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(event['ResourceProperties']['TableName'])
        table.put_item(Item={'state_key': 'game_active', 'value': False})
    return {'PhysicalResourceId': 'game-state-init'}
"""
            ),
            timeout=Duration.seconds(10),
        )
        game_state_table.grant_write_data(init_lambda)

        CustomResource(
            self,
            "InitGameStateResource",
            service_token=cr.Provider(self, "InitProvider", on_event_handler=init_lambda).service_token,
            properties={"TableName": game_state_table.table_name},
        )

        # Code Interpreter
        code_interpreter = agentcore.CfnCodeInterpreterCustom(
            self,
            "CodeInterpreter",
            name="contest_interpreter",
            network_configuration=agentcore.CfnCodeInterpreterCustom.CodeInterpreterNetworkConfigurationProperty(
                network_mode="SANDBOX"
            ),
        )

        # S3 Buckets
        website_bucket = s3.Bucket(self, "WebsiteBucket", block_public_access=s3.BlockPublicAccess.BLOCK_ALL)

        problems_bucket = s3.Bucket(self, "ProblemsBucket", block_public_access=s3.BlockPublicAccess.BLOCK_ALL)

        # Lambda functions
        submit_lambda = _lambda.Function(
            self,
            "SubmitFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="submit.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(30),
            environment={
                "LEADERBOARD_TABLE": leaderboard_table.table_name,
                "GAME_STATE_TABLE": game_state_table.table_name,
                "CODE_INTERPRETER_ID": code_interpreter.attr_code_interpreter_id,
                "PROBLEMS_BUCKET": problems_bucket.bucket_name,
            },
        )

        submit_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:StartCodeInterpreterSession",
                    "bedrock-agentcore:InvokeCodeInterpreter",
                    "bedrock-agentcore:StopCodeInterpreterSession",
                ],
                resources=[code_interpreter.attr_code_interpreter_arn],
            )
        )

        leaderboard_lambda = _lambda.Function(
            self,
            "LeaderboardFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="leaderboard.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(10),
            environment={
                "LEADERBOARD_TABLE": leaderboard_table.table_name,
                "PROBLEMS_BUCKET": problems_bucket.bucket_name,
            },
        )

        reset_lambda = _lambda.Function(
            self,
            "ResetFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="reset.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(30),
            environment={"LEADERBOARD_TABLE": leaderboard_table.table_name},
        )

        game_state_lambda = _lambda.Function(
            self,
            "GameStateFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="game_state.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(10),
            environment={"GAME_STATE_TABLE": game_state_table.table_name},
        )

        problems_lambda = _lambda.Function(
            self,
            "ProblemsFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="problems.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(10),
            environment={
                "GAME_STATE_TABLE": game_state_table.table_name,
                "PROBLEMS_BUCKET": problems_bucket.bucket_name,
            },
        )

        # Permissions
        leaderboard_table.grant_read_write_data(submit_lambda)
        leaderboard_table.grant_read_data(leaderboard_lambda)
        leaderboard_table.grant_read_write_data(reset_lambda)
        game_state_table.grant_read_data(submit_lambda)
        game_state_table.grant_read_write_data(game_state_lambda)
        game_state_table.grant_read_data(problems_lambda)
        problems_bucket.grant_read(submit_lambda)
        problems_bucket.grant_read(leaderboard_lambda)
        problems_bucket.grant_read(problems_lambda)

        # API Gateway
        api = apigw.RestApi(
            self,
            "ProgrammingContestApi",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        admin_auth_token = base64.b64encode(f"{admin_username}:{admin_password}".encode()).decode()

        api.root.add_resource("submit").add_method("POST", apigw.LambdaIntegration(submit_lambda))
        api.root.add_resource("leaderboard").add_method("GET", apigw.LambdaIntegration(leaderboard_lambda))
        api.root.add_resource("problems").add_method("GET", apigw.LambdaIntegration(problems_lambda))

        game_state_resource = api.root.add_resource("game-state")
        game_state_resource.add_method("GET", apigw.LambdaIntegration(game_state_lambda))

        # Admin endpoints - Lambda checks Authorization header
        for fn in [reset_lambda, game_state_lambda]:
            fn.add_environment("ADMIN_AUTH_TOKEN", f"Basic {admin_auth_token}")

        api.root.add_resource("reset").add_method("POST", apigw.LambdaIntegration(reset_lambda))
        game_state_resource.add_method("POST", apigw.LambdaIntegration(game_state_lambda))

        # CloudFront Functions for Basic Auth
        auth_string = base64.b64encode(f"{admin_username}:{admin_password}".encode()).decode()
        basic_auth_function = cloudfront.Function(
            self,
            "BasicAuthFunction",
            code=cloudfront.FunctionCode.from_inline(f"""\
function handler(event) {{
  var request = event.request;
  var uri = request.uri;
  if (uri !== '/admin.html' && !uri.endsWith('/admin.html')) return request;
  var expected = 'Basic {auth_string}';
  var auth = request.headers.authorization;
  if (auth && auth.value === expected) return request;
  return {{
    statusCode: 401,
    statusDescription: 'Unauthorized',
    headers: {{ 'www-authenticate': {{ value: 'Basic realm="Admin Area"' }} }}
  }};
}}"""),
        )

        # CloudFront
        distribution = cloudfront.Distribution(
            self,
            "WebsiteDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(website_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                function_associations=[
                    cloudfront.FunctionAssociation(
                        function=basic_auth_function,
                        event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                    )
                ],
            ),
            default_root_object="index.html",
        )

        # Deploy website + assets to Web Bucket
        config_js = f"window.API_CONFIG = {{ url: '{api.url}' }};"

        s3deploy.BucketDeployment(
            self,
            "DeployWebsite",
            sources=[
                s3deploy.Source.asset("website"),
                s3deploy.Source.asset("build/assets"),
                s3deploy.Source.data("config.js", config_js),
            ],
            destination_bucket=website_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        # Deploy test_solver.py + metadata.json to Problems Bucket
        s3deploy.BucketDeployment(
            self,
            "DeployProblems",
            sources=[s3deploy.Source.asset("build/problems")],
            destination_bucket=problems_bucket,
        )

        # Outputs
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "WebsiteUrl", value=f"https://{distribution.distribution_domain_name}")
