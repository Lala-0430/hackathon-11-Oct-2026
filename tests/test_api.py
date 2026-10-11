import sqlite3

import pytest
from fastapi.testclient import TestClient

SECRET = "Correct-Horse-Battery-42"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.main import app  # import first: it loads .env

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with TestClient(app) as c:
        yield c


def test_questions(client):
    res = client.get("/api/questions")
    assert res.status_code == 200
    assert all({"id", "text"} <= q.keys() for q in res.json())


def test_assess_stores_features_but_not_password(client, tmp_path):
    res = client.post("/api/assess", json={
        "password": SECRET,
        "answers": {"contains_name": False, "reused": True},
    })
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == 1
    assert 0 <= body["score"] <= 100
    assert body["ai_advice_available"] is False

    conn = sqlite3.connect(tmp_path / "test.db")
    rows = conn.execute("SELECT * FROM assessments").fetchall()
    conn.close()
    assert len(rows) == 1
    assert SECRET not in repr(rows)
    assert SECRET.lower() not in repr(rows).lower()


def test_unknown_question_rejected(client):
    res = client.post("/api/assess", json={"password": "x", "answers": {"bogus": True}})
    assert res.status_code == 400


def test_feedback_and_stats(client):
    aid = client.post("/api/assess", json={"password": "abc123", "answers": {}}).json()["id"]
    assert client.post(f"/api/assessments/{aid}/feedback", json={"feedback": "too_high"}).status_code == 200
    assert client.post(f"/api/assessments/{aid}/feedback", json={"feedback": "nope"}).status_code == 400
    assert client.post("/api/assessments/999/feedback", json={"feedback": "accurate"}).status_code == 404

    stats = client.get("/api/stats").json()
    assert stats["total_assessments"] == 1
    assert stats["by_feedback"] == {"too_high": 1}


def test_advice_disabled_without_key(client):
    aid = client.post("/api/assess", json={"password": "abc123", "answers": {}}).json()["id"]
    assert client.post(f"/api/assessments/{aid}/advice").status_code == 503


def test_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Password Strength Checker" in res.text
