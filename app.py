#!/usr/bin/env python3
import aws_cdk as cdk
from aws_pdk.pdk_nag import AwsPrototypingChecks
from cdk_nag import NagSuppressions

from programming_contest.programming_contest_stack import ProgrammingContestStack

app = cdk.App()

admin_username = app.node.try_get_context("adminUsername") or "admin"
admin_password = app.node.try_get_context("adminPassword") or "password"

stack = ProgrammingContestStack(
    app,
    "ProgrammingContestStack",
    admin_username=admin_username,
    admin_password=admin_password,
)

# PDK Nagチェックを追加
cdk.Aspects.of(app).add(AwsPrototypingChecks())

NagSuppressions.add_stack_suppressions(
    stack, [{"id": "AwsPrototyping-CloudFrontDistributionGeoRestrictions", "reason": "使用可能地域を制限しない"}]
)

app.synth()
