"""Repo Radio serving API (Lane D) — contracts/wallet_api.md, verbatim.

Run locally:  make serve-local          (cd server && uvicorn app:app --port 8080)
Container:    server/Dockerfile, port 8080 (App Runner in D5).
"""
import logging
import pathlib
import sys

# Flat imports work when launched from server/; make them work from repo root too,
# and put the repo root on the path for the sanctioned pipeline.greptile import (D4).
_HERE = pathlib.Path(__file__).resolve().parent
for p in (str(_HERE), str(_HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import ask
import settings
import stripe_pay
import wallet

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server.app")

app = FastAPI(title="Repo Radio API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TopupRequest(BaseModel):
    user_id: str
    tier: int


class AskRequest(BaseModel):
    user_id: str
    episode_id: str
    question: str = Field(min_length=1, max_length=500)


@app.get("/healthz")
def healthz():
    return {"ok": True, "mocks": settings.USE_MOCKS}


@app.post("/api/topup")
def topup(req: TopupRequest):
    try:
        url = stripe_pay.create_checkout(req.user_id.lower(), req.tier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"checkout_url": url}


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    try:
        stripe_pay.handle_webhook(payload, request.headers.get("stripe-signature"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {}


@app.get("/api/wallet/{user_id}")
def get_wallet(user_id: str):
    return {"credits": wallet.get_store().get_credits(user_id.lower())}


@app.post("/api/ask")
def post_ask(req: AskRequest, background: BackgroundTasks):
    user_id = req.user_id.lower()
    job_id = ask.create_job(user_id, req.episode_id, req.question)
    try:
        wallet.get_store().debit(user_id, settings.CREDITS_PER_QUESTION, job_id)
    except wallet.InsufficientCredits:
        return JSONResponse(status_code=402, content={"error": "no_credits"})
    background.add_task(ask.run_job, job_id)
    return {"job_id": job_id}


@app.get("/api/ask/{job_id}")
def get_ask(job_id: str):
    job = ask.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    if job["status"] == "done":
        return {"status": "done", "qa_segment": job["qa_segment"]}
    if job["status"] == "error":
        # Contract only defines pending|done; surface errors as pending never —
        # be explicit so Lane C can show a retry state.
        return JSONResponse(status_code=500, content={"status": "error", "error": job["error"]})
    return {"status": "pending"}
