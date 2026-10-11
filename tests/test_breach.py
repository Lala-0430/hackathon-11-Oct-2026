import hashlib
import io
import urllib.request

from app import breach

PASSWORD = "hunter2"
DIGEST = hashlib.sha1(PASSWORD.encode()).hexdigest().upper()


def fake_urlopen(body, calls):
    def urlopen(request, timeout):
        calls.append(request)
        return io.BytesIO(body.encode())
    return urlopen


def test_parse_range():
    body = "0018A45C4D1DEF81644B54AB7F969B88D65:1\r\nABCDEF:0\r\n00D4F6E8FA6EECAD2A3AA415EEC418D38EC:2\n"
    assert breach.parse_range(body, "00D4F6E8FA6EECAD2A3AA415EEC418D38EC") == 2
    assert breach.parse_range(body, "ABCDEF") == 0  # padding entry
    assert breach.parse_range(body, "FFFF") == 0


def test_only_hash_prefix_is_sent(monkeypatch):
    monkeypatch.delenv("BREACH_CHECK", raising=False)
    calls = []
    body = f"{DIGEST[5:]}:42\r\nAAAA:0\r\n"
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen(body, calls))

    assert breach.breach_count(PASSWORD) == 42
    (request,) = calls
    assert request.full_url == breach.API_URL + DIGEST[:5]
    assert PASSWORD not in request.full_url
    assert DIGEST[5:] not in request.full_url


def test_network_error_returns_none(monkeypatch):
    monkeypatch.delenv("BREACH_CHECK", raising=False)

    def fail(request, timeout):
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    assert breach.breach_count(PASSWORD) is None


def test_can_be_disabled(monkeypatch):
    monkeypatch.setenv("BREACH_CHECK", "false")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen("", calls := []))
    assert breach.breach_count(PASSWORD) is None
    assert calls == []
