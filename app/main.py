"""FastAPI application: JSON API + static frontend."""

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from app import advisor, breach, db  # noqa: E402  (load .env before reading config)
from app.analyzer import analyze  # noqa: E402
from app.questions import QUESTIONS, QUESTIONS_BY_ID  # noqa: E402
from app.ratelimit import RateLimiter, client_ip  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

logger = logging.getLogger(__name__)

# Per-client limits, plus a global cap on AI advice to protect the Gemini API quota.
assess_limiter = RateLimiter(limit=30, window_seconds=60)
feedback_limiter = RateLimiter(limit=30, window_seconds=60)
advice_limiter = RateLimiter(limit=10, window_seconds=60)
advice_global_limiter = RateLimiter(limit=200, window_seconds=3600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Password Strength Checker", lifespan=lifespan)


class AssessRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    answers: dict[str, bool] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    feedback: str


@app.get("/api/questions")
def list_questions():
    return [{"id": q.id, "text": q.text} for q in QUESTIONS]


@app.post("/api/assess")
def assess(req: AssessRequest, request: Request):
    assess_limiter.check(client_ip(request))
    unknown = set(req.answers) - set(QUESTIONS_BY_ID)
    if unknown:
        raise HTTPException(400, f"Unknown question ids: {sorted(unknown)}")

    # The password is used here in memory only and is never stored or logged.
    result = analyze(req.password, req.answers, breach.breach_count(req.password))
    assessment_id = db.save_assessment(result, req.answers)

    body = result.to_dict()
    body["id"] = assessment_id
    body["ai_advice_available"] = advisor.is_enabled()
    return body


@app.post("/api/assessments/{assessment_id}/advice")
async def advice(assessment_id: str, request: Request):
    if not advisor.is_enabled():
        raise HTTPException(503, "AI advice is not configured (GEMINI_API_KEY missing).")
    advice_limiter.check(client_ip(request))
    record = db.get_assessment(assessment_id)
    if record is None:
        raise HTTPException(404, "Assessment not found.")
    advice_global_limiter.check("global")
    try:
        text = await advisor.get_advice(record)
    except Exception:  # network / quota / model errors
        logger.exception("AI advice failed")
        raise HTTPException(502, "AI advice is temporarily unavailable. Please try again later.")
    return {"advice": text}


@app.post("/api/assessments/{assessment_id}/feedback")
def feedback(assessment_id: str, req: FeedbackRequest, request: Request):
    feedback_limiter.check(client_ip(request))
    if req.feedback not in db.FEEDBACK_VALUES:
        raise HTTPException(400, f"feedback must be one of {sorted(db.FEEDBACK_VALUES)}")
    if not db.set_feedback(assessment_id, req.feedback):
        raise HTTPException(404, "Assessment not found, or feedback was already given.")
    return {"ok": True}


@app.get("/api/stats")
def stats(authorization: str | None = Header(default=None)):
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        raise HTTPException(403, "Stats are disabled. Set ADMIN_TOKEN to enable them.")
    expected = f"Bearer {token}".encode()
    if not authorization or not secrets.compare_digest(authorization.encode(), expected):
        raise HTTPException(401, "Missing or invalid admin token.")
    return db.get_stats()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
