#!/usr/bin/env python3
import aws_cdk as cdk
from aws_pdk.pdk_nag import AwsPrototypingChecks
from cdk_nag import NagSuppressions

from programming_contest.programming_contest_stack import ProgrammingContestStack

app = cdk.App()
stack = ProgrammingContestStack(app, "ProgrammingContestStack")

# PDK Nagチェックを追加
cdk.Aspects.of(app).add(AwsPrototypingChecks())

NagSuppressions.add_stack_suppressions(
    stack, [{"id": "AwsPrototyping-CloudFrontDistributionGeoRestrictions", "reason": "使用可能地域を制限しない"}]
)

app.synth()
