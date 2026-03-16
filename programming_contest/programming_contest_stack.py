import base64
import os

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
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
            partition_key=aws_dynamodb.Attribute(name="problem_id", type=aws_dynamodb.AttributeType.STRING),
            sort_key=aws_dynamodb.Attribute(name="username", type=aws_dynamodb.AttributeType.STRING),
            billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        game_state_table = aws_dynamodb.Table(
            self,
            "GameStateTable",
            partition_key=aws_dynamodb.Attribute(name="state_key", type=aws_dynamodb.AttributeType.STRING),
            billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
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
        website_bucket = aws_s3.Bucket(
            self, "WebsiteBucket",
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        problems_bucket = aws_s3.Bucket(
            self, "ProblemsBucket",
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

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
                "RATE_LIMIT_COOLDOWN": "10",
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

        explore_lambda = aws_lambda.Function(
            self,
            "ExploreFunction",
            runtime=aws_lambda.Runtime.PYTHON_3_11,
            handler="explore.handler",
            code=aws_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(30),
            environment={
                "GAME_STATE_TABLE": game_state_table.table_name,
                "PROBLEMS_BUCKET": problems_bucket.bucket_name,
                "RATE_LIMIT_COOLDOWN": "10",
            },
        )

        explore_lambda.add_to_role_policy(
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
        game_state_table.grant_read_write_data(submit_lambda)
        problems_bucket.grant_read(submit_lambda)

        leaderboard_table.grant_read_write_data(api_lambda)
        game_state_table.grant_read_write_data(api_lambda)
        problems_bucket.grant_read(api_lambda)

        game_state_table.grant_read_write_data(explore_lambda)
        problems_bucket.grant_read(explore_lambda)

        # API Gateway
        api = aws_apigateway.RestApi(self, "ProgrammingContestApi")

        api_integration = aws_apigateway.LambdaIntegration(api_lambda)

        api_resource = api.root.add_resource("api")
        api_resource.add_resource("submit").add_method("POST", aws_apigateway.LambdaIntegration(submit_lambda))
        api_resource.add_resource("explore").add_method("POST", aws_apigateway.LambdaIntegration(explore_lambda))
        api_resource.add_resource("leaderboard").add_method("GET", api_integration)
        api_resource.add_resource("problems").add_method("GET", api_integration)
        api_resource.add_resource("reset").add_method("POST", api_integration)

        game_state_resource = api_resource.add_resource("game-state")
        game_state_resource.add_method("GET", api_integration)
        game_state_resource.add_method("POST", api_integration)

        # CloudFront
        api_origin = aws_cloudfront_origins.HttpOrigin(
            f"{api.rest_api_id}.execute-api.{self.region}.amazonaws.com",
            origin_path=f"/{api.deployment_stage.stage_name}",
        )

        distribution = aws_cloudfront.Distribution(
            self,
            "WebsiteDistribution",
            default_behavior=aws_cloudfront.BehaviorOptions(
                origin=aws_cloudfront_origins.S3Origin(website_bucket),
                viewer_protocol_policy=aws_cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            additional_behaviors={
                "/api/*": aws_cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=aws_cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=aws_cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=aws_cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=aws_cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                ),
            },
            default_root_object="index.html",
        )

        # Deploy website + assets to Web Bucket
        aws_s3_deployment.BucketDeployment(
            self,
            "DeployWebsite",
            sources=[
                aws_s3_deployment.Source.asset("website"),
                aws_s3_deployment.Source.asset("build/assets"),
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

        # Deploy CTF environment files to Problems Bucket under ctf-env/ prefix
        ctf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ctf")
        if os.path.isdir(ctf_dir):
            aws_s3_deployment.BucketDeployment(
                self,
                "DeployCtfEnv",
                sources=[aws_s3_deployment.Source.asset(ctf_dir, exclude=["generate.py"])],
                destination_bucket=problems_bucket,
                destination_key_prefix="ctf-env",
            )

        # Outputs
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "WebsiteUrl", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "AdminAuthToken", value=f"Basic {auth_string}")
        CfnOutput(self, "AdminCredentials", value=f"{admin_username}:{admin_password}")
