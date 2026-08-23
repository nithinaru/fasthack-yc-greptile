#!/usr/bin/env bash
# Repo Radio — one-time AWS setup (Lane 0, step 4).
# REVIEW BEFORE RUNNING. Requires: aws CLI configured with S3+CloudFront+DynamoDB perms.
# Usage:  bash infra/aws_setup.sh          (uses S3_BUCKET/AWS_REGION from env or defaults)
# After it finishes, copy the printed CLOUDFRONT_* values into .env.
set -euo pipefail

REGION="${AWS_REGION:-us-west-2}"
BUCKET="${S3_BUCKET:-repo-radio-live}"

echo "== 1/5 S3 bucket: $BUCKET ($REGION)"
aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
  --create-bucket-configuration LocationConstraint="$REGION" 2>/dev/null || echo "  (bucket exists, continuing)"

echo "== 2/5 S3: public read policy + CORS (wavesurfer fetches audio cross-origin)"
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false
aws s3api put-bucket-policy --bucket "$BUCKET" --policy "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{
    \"Sid\": \"PublicRead\", \"Effect\": \"Allow\", \"Principal\": \"*\",
    \"Action\": \"s3:GetObject\", \"Resource\": \"arn:aws:s3:::$BUCKET/*\"
  }]
}"
aws s3api put-bucket-cors --bucket "$BUCKET" --cors-configuration '{
  "CORSRules": [{
    "AllowedOrigins": ["*"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3600
  }]
}'

echo "== 3/5 CloudFront distribution (origin: $BUCKET S3 REST endpoint, TTL 60s)"
DIST_JSON=$(aws cloudfront create-distribution --distribution-config "{
  \"CallerReference\": \"repo-radio-$BUCKET\",
  \"Comment\": \"Repo Radio\",
  \"Enabled\": true,
  \"DefaultRootObject\": \"index.html\",
  \"Origins\": {\"Quantity\": 1, \"Items\": [{
    \"Id\": \"s3-$BUCKET\",
    \"DomainName\": \"$BUCKET.s3.$REGION.amazonaws.com\",
    \"S3OriginConfig\": {\"OriginAccessIdentity\": \"\"}
  }]},
  \"DefaultCacheBehavior\": {
    \"TargetOriginId\": \"s3-$BUCKET\",
    \"ViewerProtocolPolicy\": \"redirect-to-https\",
    \"AllowedMethods\": {\"Quantity\": 2, \"Items\": [\"GET\", \"HEAD\"],
      \"CachedMethods\": {\"Quantity\": 2, \"Items\": [\"GET\", \"HEAD\"]}},
    \"ForwardedValues\": {\"QueryString\": false, \"Cookies\": {\"Forward\": \"none\"},
      \"Headers\": {\"Quantity\": 3, \"Items\": [\"Origin\", \"Access-Control-Request-Method\", \"Access-Control-Request-Headers\"]}},
    \"MinTTL\": 0, \"DefaultTTL\": 60, \"MaxTTL\": 60,
    \"Compress\": true
  }
}" 2>&1) || { echo "$DIST_JSON" | grep -q DistributionAlreadyExists && echo "  (distribution exists — look it up with: aws cloudfront list-distributions)" && DIST_JSON=""; }
if [ -n "$DIST_JSON" ]; then
  DIST_ID=$(echo "$DIST_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['Distribution']['Id'])")
  DIST_DOMAIN=$(echo "$DIST_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['Distribution']['DomainName'])")
else
  DIST_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?Comment=='Repo Radio'].Id | [0]" --output text)
  DIST_DOMAIN=$(aws cloudfront list-distributions --query "DistributionList.Items[?Comment=='Repo Radio'].DomainName | [0]" --output text)
fi

echo "== 4/5 DynamoDB table: wallets (PK user_id, on-demand)"
aws dynamodb create-table --region "$REGION" --table-name wallets \
  --attribute-definitions AttributeName=user_id,AttributeType=S \
  --key-schema AttributeName=user_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST 2>/dev/null || echo "  (table exists, continuing)"

echo "== 5/5 Upload fixtures so lanes have live URLs immediately"
aws s3 cp fixtures/ep-000.json "s3://$BUCKET/episodes/ep-000.json" --content-type application/json
aws s3 cp fixtures/audio/ep-000.mp3 "s3://$BUCKET/audio/ep-000.mp3" --content-type audio/mpeg

echo
echo "================  ADD TO .env  ================"
echo "CLOUDFRONT_DISTRIBUTION_ID=$DIST_ID"
echo "CLOUDFRONT_URL=https://$DIST_DOMAIN"
echo "==============================================="
echo "Verify (distribution deploys in ~3-5 min):"
echo "  curl -s https://$DIST_DOMAIN/episodes/ep-000.json | head -5"
