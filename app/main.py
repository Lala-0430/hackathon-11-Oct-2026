"""FastAPI application: JSON API + static frontend."""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from app import advisor, db  # noqa: E402  (load .env before reading config)
from app.analyzer import analyze  # noqa: E402
from app.questions import QUESTIONS, QUESTIONS_BY_ID  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


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
def assess(req: AssessRequest):
    unknown = set(req.answers) - set(QUESTIONS_BY_ID)
    if unknown:
        raise HTTPException(400, f"Unknown question ids: {sorted(unknown)}")

    # The password is used here in memory only and is never stored or logged.
    result = analyze(req.password, req.answers)
    assessment_id = db.save_assessment(result, req.answers)

    body = result.to_dict()
    body["id"] = assessment_id
    body["ai_advice_available"] = advisor.is_enabled()
    return body


@app.post("/api/assessments/{assessment_id}/advice")
async def advice(assessment_id: int):
    if not advisor.is_enabled():
        raise HTTPException(503, "AI advice is not configured (GEMINI_API_KEY missing).")
    record = db.get_assessment(assessment_id)
    if record is None:
        raise HTTPException(404, "Assessment not found.")
    try:
        text = await advisor.get_advice(record)
    except Exception as exc:  # network / quota / model errors
        raise HTTPException(502, f"AI advice failed: {exc}") from exc
    return {"advice": text}


@app.post("/api/assessments/{assessment_id}/feedback")
def feedback(assessment_id: int, req: FeedbackRequest):
    if req.feedback not in db.FEEDBACK_VALUES:
        raise HTTPException(400, f"feedback must be one of {sorted(db.FEEDBACK_VALUES)}")
    if not db.set_feedback(assessment_id, req.feedback):
        raise HTTPException(404, "Assessment not found.")
    return {"ok": True}


@app.get("/api/stats")
def stats():
    return db.get_stats()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
