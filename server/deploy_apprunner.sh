#!/usr/bin/env bash
# D5 — build + push the API image to ECR and create/update the App Runner service.
# One command once AWS access exists:  bash server/deploy_apprunner.sh
# Requires: Docker running, aws CLI configured, .env populated at repo root.
set -euo pipefail
cd "$(dirname "$0")/.."

set -a; source .env; set +a
: "${AWS_REGION:?}"; : "${S3_BUCKET:?}"

SERVICE=repo-radio-api
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR="$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com"
IMAGE="$ECR/$SERVICE:latest"

aws ecr describe-repositories --repository-names "$SERVICE" --region "$AWS_REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$SERVICE" --region "$AWS_REGION" >/dev/null

aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR"
docker build --platform linux/amd64 -f server/Dockerfile -t "$IMAGE" .
docker push "$IMAGE"

RUNTIME_ENV=$(cat <<EOF
[
  {"Name":"USE_MOCKS","Value":"${USE_MOCKS:-0}"},
  {"Name":"AWS_REGION","Value":"$AWS_REGION"},
  {"Name":"S3_BUCKET","Value":"$S3_BUCKET"},
  {"Name":"STRIPE_SECRET_KEY","Value":"${STRIPE_SECRET_KEY:-}"},
  {"Name":"STRIPE_WEBHOOK_SECRET","Value":"${STRIPE_WEBHOOK_SECRET:-}"},
  {"Name":"GREPTILE_API_KEY","Value":"${GREPTILE_API_KEY:-}"},
  {"Name":"GITHUB_TOKEN","Value":"${GITHUB_TOKEN:-}"},
  {"Name":"MODAL_SCRIPT_URL","Value":"${MODAL_SCRIPT_URL:-}"},
  {"Name":"MODAL_TTS_URL","Value":"${MODAL_TTS_URL:-}"},
  {"Name":"CORS_ORIGINS","Value":"${CORS_ORIGINS:-*}"},
  {"Name":"SITE_URL","Value":"${SITE_URL:-}"}
]
EOF
)

# App Runner needs an instance role with DynamoDB (wallets) + S3 (bucket) access
# and an ECR access role. infra/aws_setup.sh owns creating those; pass ARNs here.
: "${APPRUNNER_ECR_ROLE_ARN:?set in .env after infra/aws_setup.sh runs}"
: "${APPRUNNER_INSTANCE_ROLE_ARN:?set in .env after infra/aws_setup.sh runs}"

SOURCE_CFG=$(cat <<EOF
{
  "ImageRepository": {
    "ImageIdentifier": "$IMAGE",
    "ImageRepositoryType": "ECR",
    "ImageConfiguration": {"Port": "8080", "RuntimeEnvironmentVariables": $(echo "$RUNTIME_ENV" | python3 -c 'import json,sys; print(json.dumps({e["Name"]: e["Value"] for e in json.load(sys.stdin)}))')}
  },
  "AuthenticationConfiguration": {"AccessRoleArn": "$APPRUNNER_ECR_ROLE_ARN"},
  "AutoDeploymentsEnabled": false
}
EOF
)

ARN=$(aws apprunner list-services --region "$AWS_REGION" \
      --query "ServiceSummaryList[?ServiceName=='$SERVICE'].ServiceArn|[0]" --output text)

if [ "$ARN" = "None" ] || [ -z "$ARN" ]; then
  aws apprunner create-service --region "$AWS_REGION" --service-name "$SERVICE" \
    --source-configuration "$SOURCE_CFG" \
    --instance-configuration "{\"Cpu\":\"1 vCPU\",\"Memory\":\"2 GB\",\"InstanceRoleArn\":\"$APPRUNNER_INSTANCE_ROLE_ARN\"}" \
    --health-check-configuration '{"Protocol":"HTTP","Path":"/healthz"}'
else
  aws apprunner update-service --region "$AWS_REGION" --service-arn "$ARN" \
    --source-configuration "$SOURCE_CFG"
fi

echo "Waiting for service URL…"
sleep 5
URL=$(aws apprunner list-services --region "$AWS_REGION" \
      --query "ServiceSummaryList[?ServiceName=='$SERVICE'].ServiceUrl|[0]" --output text)
echo "API base: https://$URL"
echo "Next: verify  curl https://$URL/healthz  then SYNC the URL into web/config.js"
