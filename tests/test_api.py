import sqlite3

import pytest
from fastapi.testclient import TestClient

SECRET = "Correct-Horse-Battery-42"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.main import app  # import first: it loads .env

    from app import main

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BREACH_CHECK", "false")  # no network calls in tests
    for var in ("GEMINI_API_KEY", "DATABASE_URL", "ADMIN_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    for limiter in (main.assess_limiter, main.feedback_limiter, main.advice_limiter):
        limiter.hits.clear()

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
    assert isinstance(body["id"], str) and len(body["id"]) == 32
    assert 0 <= body["score"] <= 100
    assert body["ai_advice_available"] is False

    conn = sqlite3.connect(tmp_path / "test.db")
    rows = conn.execute("SELECT * FROM assessments").fetchall()
    conn.close()
    assert len(rows) == 1
    assert SECRET not in repr(rows)
    assert SECRET.lower() not in repr(rows).lower()


def test_assess_reports_breach(client, monkeypatch, tmp_path):
    from app import breach

    monkeypatch.setattr(breach, "breach_count", lambda pw: 7)
    body = client.post("/api/assess", json={"password": SECRET, "answers": {}}).json()
    assert body["features"]["breach_count"] == 7
    assert "found_in_breach" in body["features"]["patterns"]
    assert body["score"] == 0

    conn = sqlite3.connect(tmp_path / "test.db")
    (patterns,) = conn.execute("SELECT patterns FROM assessments").fetchone()
    conn.close()
    assert "found_in_breach" in patterns


def test_assess_returns_improvements(client):
    body = client.post("/api/assess", json={"password": "sunflower", "answers": {}}).json()
    assert body["replace_recommended"] is False
    steps = body["improvements"]
    assert steps and all({"fix", "score"} <= step.keys() for step in steps)
    assert steps[0]["score"] > body["score"]


def test_passphrase_wordlist_served(client):
    res = client.get("/static/wordlists/eff-large.txt")
    assert res.status_code == 200
    assert len(res.text.split()) == 7776


@pytest.mark.parametrize("name", ["background", "click", "clapping"])
def test_sound_served(client, name):
    res = client.get(f"/static/audio/{name}.mp3")
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/mpeg"


def test_unknown_question_rejected(client):
    res = client.post("/api/assess", json={"password": "x", "answers": {"bogus": True}})
    assert res.status_code == 400


def test_feedback_only_once(client):
    aid = client.post("/api/assess", json={"password": "abc123", "answers": {}}).json()["id"]
    assert client.post(f"/api/assessments/{aid}/feedback", json={"feedback": "nope"}).status_code == 400
    assert client.post(f"/api/assessments/{aid}/feedback", json={"feedback": "too_high"}).status_code == 200
    assert client.post(f"/api/assessments/{aid}/feedback", json={"feedback": "accurate"}).status_code == 404
    assert client.post("/api/assessments/1/feedback", json={"feedback": "accurate"}).status_code == 404


def test_stats_requires_admin_token(client, monkeypatch):
    aid = client.post("/api/assess", json={"password": "abc123", "answers": {}}).json()["id"]
    client.post(f"/api/assessments/{aid}/feedback", json={"feedback": "too_high"})

    assert client.get("/api/stats").status_code == 403  # ADMIN_TOKEN not set
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/stats", headers={"Authorization": "Bearer wrong"}).status_code == 401

    stats = client.get("/api/stats", headers={"Authorization": "Bearer s3cret"}).json()
    assert stats["total_assessments"] == 1
    assert stats["by_feedback"] == {"too_high": 1}


def test_assess_rate_limited(client):
    codes = [client.post("/api/assess", json={"password": "abc123"}).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30
    assert codes[30] == 429


def test_sqlite_migration_adds_public_id(tmp_path, monkeypatch):
    from app import db

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        db.SCHEMA.format(**db.SQLITE_TYPES).replace(
            "public_id       TEXT    NOT NULL UNIQUE,  -- random id exposed by the API", "")
    )
    conn.execute(
        "INSERT INTO assessments (created_at, scoring_version, length, has_lower, has_upper,"
        " has_digit, has_symbol, has_other, pool_size, entropy_bits, patterns, answers,"
        " score, label) VALUES ('t', '1.0.0', 6, 1, 0, 1, 0, 0, 36, 31.0, '[]', '{}', 30, 'Weak')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db.init_db()
    conn = sqlite3.connect(path)
    (public_id,) = conn.execute("SELECT public_id FROM assessments").fetchone()
    conn.close()
    assert public_id and len(public_id) == 32


def test_advice_disabled_without_key(client):
    aid = client.post("/api/assess", json={"password": "abc123", "answers": {}}).json()["id"]
    assert client.post(f"/api/assessments/{aid}/advice").status_code == 503


def test_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Password Strength Checker" in res.text


def test_client_ip_prefers_cloudflare_header(monkeypatch):
    from starlette.requests import Request

    from app.ratelimit import client_ip

    def req(headers):
        raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        return Request({"type": "http", "headers": raw, "client": ("127.0.0.1", 1234)})

    assert client_ip(req({"CF-Connecting-IP": "1.2.3.4", "X-Forwarded-For": "5.6.7.8"})) == "1.2.3.4"
    assert client_ip(req({"X-Forwarded-For": "5.6.7.8, 10.0.0.1"})) == "5.6.7.8"
    assert client_ip(req({})) == "127.0.0.1"

    monkeypatch.setenv("VERCEL", "1")  # forged CF header is ignored on Vercel
    assert client_ip(req({"CF-Connecting-IP": "1.2.3.4", "X-Forwarded-For": "5.6.7.8"})) == "5.6.7.8"
