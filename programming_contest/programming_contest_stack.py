import base64

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_apigateway,
    aws_cloudfront,
    aws_cloudfront_origins,
    aws_dynamodb,
    aws_iam,
    aws_lambda,
    aws_s3,
    aws_s3_deployment,
    custom_resources,
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

        auth_string = base64.b64encode(f"{admin_username}:{admin_password}".encode()).decode()

        # DynamoDB tables
        leaderboard_table = aws_dynamodb.Table(
            self,
            "LeaderboardTable",
            partition_key=aws_dynamodb.Attribute(name="submission_id", type=aws_dynamodb.AttributeType.STRING),
            billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        game_state_table = aws_dynamodb.Table(
            self,
            "GameStateTable",
            partition_key=aws_dynamodb.Attribute(name="state_key", type=aws_dynamodb.AttributeType.STRING),
            billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        # Initialize game state to false
        custom_resources.AwsCustomResource(
            self,
            "InitGameState",
            on_create=custom_resources.AwsSdkCall(
                service="DynamoDB",
                action="putItem",
                parameters={
                    "TableName": game_state_table.table_name,
                    "Item": {"state_key": {"S": "game_active"}, "value": {"BOOL": False}},
                },
                physical_resource_id=custom_resources.PhysicalResourceId.of("game-state-init"),
            ),
            policy=custom_resources.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[game_state_table.table_arn],
            ),
        )

        # S3 Buckets
        website_bucket = aws_s3.Bucket(self, "WebsiteBucket", block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL)

        problems_bucket = aws_s3.Bucket(self, "ProblemsBucket", block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL)

        # Lambda functions
        submit_lambda = aws_lambda.Function(
            self,
            "SubmitFunction",
            runtime=aws_lambda.Runtime.PYTHON_3_11,
            handler="submit.handler",
            code=aws_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(30),
            environment={
                "LEADERBOARD_TABLE": leaderboard_table.table_name,
                "GAME_STATE_TABLE": game_state_table.table_name,
                "PROBLEMS_BUCKET": problems_bucket.bucket_name,
            },
        )

        submit_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:StartCodeInterpreterSession",
                    "bedrock-agentcore:InvokeCodeInterpreter",
                    "bedrock-agentcore:StopCodeInterpreterSession",
                ],
                resources=[
                    f"arn:aws:bedrock-agentcore:{self.region}:aws:code-interpreter/aws.codeinterpreter.v1"
                ],
            )
        )

        api_lambda = aws_lambda.Function(
            self,
            "ApiFunction",
            runtime=aws_lambda.Runtime.PYTHON_3_11,
            handler="api.handler",
            code=aws_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(10),
            environment={
                "LEADERBOARD_TABLE": leaderboard_table.table_name,
                "GAME_STATE_TABLE": game_state_table.table_name,
                "PROBLEMS_BUCKET": problems_bucket.bucket_name,
                "ADMIN_AUTH_TOKEN": f"Basic {auth_string}",
            },
        )

        # Permissions
        leaderboard_table.grant_read_write_data(submit_lambda)
        game_state_table.grant_read_data(submit_lambda)
        problems_bucket.grant_read(submit_lambda)

        leaderboard_table.grant_read_write_data(api_lambda)
        game_state_table.grant_read_write_data(api_lambda)
        problems_bucket.grant_read(api_lambda)

        # API Gateway
        api = aws_apigateway.RestApi(
            self,
            "ProgrammingContestApi",
            default_cors_preflight_options=aws_apigateway.CorsOptions(
                allow_origins=aws_apigateway.Cors.ALL_ORIGINS,
                allow_methods=aws_apigateway.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        api_integration = aws_apigateway.LambdaIntegration(api_lambda)

        api.root.add_resource("submit").add_method("POST", aws_apigateway.LambdaIntegration(submit_lambda))
        api.root.add_resource("leaderboard").add_method("GET", api_integration)
        api.root.add_resource("problems").add_method("GET", api_integration)
        api.root.add_resource("reset").add_method("POST", api_integration)

        game_state_resource = api.root.add_resource("game-state")
        game_state_resource.add_method("GET", api_integration)
        game_state_resource.add_method("POST", api_integration)

        # CloudFront Functions for Basic Auth
        basic_auth_function = aws_cloudfront.Function(
            self,
            "BasicAuthFunction",
            code=aws_cloudfront.FunctionCode.from_inline(f"""\
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
        distribution = aws_cloudfront.Distribution(
            self,
            "WebsiteDistribution",
            default_behavior=aws_cloudfront.BehaviorOptions(
                origin=aws_cloudfront_origins.S3Origin(website_bucket),
                viewer_protocol_policy=aws_cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                function_associations=[
                    aws_cloudfront.FunctionAssociation(
                        function=basic_auth_function,
                        event_type=aws_cloudfront.FunctionEventType.VIEWER_REQUEST,
                    )
                ],
            ),
            default_root_object="index.html",
        )

        # Deploy website + assets to Web Bucket
        config_js = f"window.API_CONFIG = {{ url: '{api.url}' }};"

        aws_s3_deployment.BucketDeployment(
            self,
            "DeployWebsite",
            sources=[
                aws_s3_deployment.Source.asset("website"),
                aws_s3_deployment.Source.asset("build/assets"),
                aws_s3_deployment.Source.data("config.js", config_js),
            ],
            destination_bucket=website_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        # Deploy test_solver.py + metadata.json to Problems Bucket
        aws_s3_deployment.BucketDeployment(
            self,
            "DeployProblems",
            sources=[aws_s3_deployment.Source.asset("build/problems")],
            destination_bucket=problems_bucket,
        )

        # Outputs
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "WebsiteUrl", value=f"https://{distribution.distribution_domain_name}")
