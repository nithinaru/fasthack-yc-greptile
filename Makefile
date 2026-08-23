# Repo Radio — shared targets (frozen at Gate 0; changes need a SYNC commit)
# Env comes from .env (see .env.example). Load with: set -a; . ./.env; set +a

PYTHON ?= python3
-include .env
export

.PHONY: smoke deploy-web bake-episode serve-local fixtures

smoke:
	$(PYTHON) scripts/smoke.py

# Sync the static site + published episode data to S3, then invalidate CloudFront.
deploy-web:
	aws s3 sync web/ s3://$(S3_BUCKET)/ --exclude ".*" --region $(AWS_REGION)
	@if [ -n "$(CLOUDFRONT_DISTRIBUTION_ID)" ]; then \
		aws cloudfront create-invalidation --distribution-id $(CLOUDFRONT_DISTRIBUTION_ID) --paths "/*"; \
	else echo "CLOUDFRONT_DISTRIBUTION_ID unset — skipping invalidation"; fi

# Full pipeline: repo in → published episode out. Usage: make bake-episode REPO=owner/name
bake-episode:
	$(PYTHON) -m pipeline.bake --repo "$(REPO)"

# Lane D fallback: local FastAPI (pair with `stripe listen --forward-to localhost:8080`)
serve-local:
	cd server && uvicorn app:app --port 8080 --reload

# Regenerate ep-000 fixture from fixtures/src (Lane 0 tooling)
fixtures:
	$(PYTHON) fixtures/generate_ep000.py
