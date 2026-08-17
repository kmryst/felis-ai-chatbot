"""health / readyz / request ID / /chat / 設定 fail-fast のテスト。"""

import dataclasses

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import InvalidEnvError, MissingEnvError, Settings


@pytest.fixture()
def client():
    with TestClient(main_module.app) as c:
        yield c


def test_health_returns_200(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_readyz_returns_503_when_db_unreachable(client, monkeypatch):
    """DB に到達できない場合は 503。/health は 200 のまま（liveness と分離）。"""
    unreachable = dataclasses.replace(
        main_module.settings,
        database_url="postgresql://x:x@127.0.0.1:1/nowhere",
        db_connect_timeout_seconds=1,
    )
    monkeypatch.setattr(main_module, "settings", unreachable)
    res = client.get("/readyz")
    assert res.status_code == 503
    assert res.json() == {"status": "unavailable", "db": "unreachable"}
    assert client.get("/health").status_code == 200


def test_request_id_is_honored_and_generated(client):
    res = client.get("/health", headers={"X-Request-ID": "req-abc-123"})
    assert res.headers["x-request-id"] == "req-abc-123"
    res2 = client.get("/health")
    assert res2.headers["x-request-id"]  # 無ければ採番される
    assert res2.headers["x-request-id"] != "req-abc-123"


def test_chat_returns_stub_reply(client):
    """/chat はスタブ LLM の決定的応答を返す（実 LLM は呼ばない）。"""
    res = client.post("/chat", json={"message": "こんにちは"})
    assert res.status_code == 200
    body = res.json()
    assert body["reply"].startswith("[stub]")
    assert "こんにちは" in body["reply"]


def test_chat_rejects_empty_message(client):
    assert client.post("/chat", json={"message": ""}).status_code == 422


def test_settings_fail_fast_on_missing_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(MissingEnvError) as exc_info:
        Settings.from_env()
    assert "DATABASE_URL" in str(exc_info.value)


def test_settings_fail_fast_on_invalid_int(monkeypatch):
    monkeypatch.setenv("DB_CONNECT_TIMEOUT_SECONDS", "abc")
    with pytest.raises(InvalidEnvError) as exc_info:
        Settings.from_env()
    assert "DB_CONNECT_TIMEOUT_SECONDS" in str(exc_info.value)
