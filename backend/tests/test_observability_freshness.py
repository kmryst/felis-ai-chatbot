"""/readyz の観測鮮度フィールド（Issue #104）のテスト。実 DB には接続しない。"""

import asyncio

import pytest
from fastapi.testclient import TestClient

import app.main as main_module


@pytest.fixture()
def client():
    with TestClient(main_module.app) as c:
        yield c


def _patch_db_ready(monkeypatch, ready=True):
    async def fake(database_url, timeout):
        return ready

    monkeypatch.setattr(main_module, "check_database_ready", fake)


def test_readyz_includes_per_series_freshness(client, monkeypatch):
    _patch_db_ready(monkeypatch)

    async def fake_freshness(database_url, timeout):
        return {
            "marker_age_seconds": 42,
            "stats_age_seconds": 130,
            "pgstattuple_age_seconds": 2400,
        }

    monkeypatch.setattr(
        main_module, "fetch_observation_freshness", fake_freshness
    )
    res = client.get("/readyz")
    assert res.status_code == 200
    body = res.json()
    assert body["obs"] == {
        "marker_age_seconds": 42,
        "stats_age_seconds": 130,
        "pgstattuple_age_seconds": 2400,
    }


def test_readyz_obs_null_when_freshness_unavailable(client, monkeypatch):
    """obs スキーマ未作成等でも /readyz 自体は 200 のまま（役割分離）。"""
    _patch_db_ready(monkeypatch)

    async def fake_freshness(database_url, timeout):
        return None

    monkeypatch.setattr(
        main_module, "fetch_observation_freshness", fake_freshness
    )
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json()["obs"] is None


def test_readyz_503_does_not_query_freshness(client, monkeypatch):
    _patch_db_ready(monkeypatch, ready=False)
    called = {"n": 0}

    async def fake_freshness(database_url, timeout):
        called["n"] += 1
        return None

    monkeypatch.setattr(
        main_module, "fetch_observation_freshness", fake_freshness
    )
    res = client.get("/readyz")
    assert res.status_code == 503
    assert called["n"] == 0


# --- statement_timeout（Issue #114 の 3） ---
# 「取得不能でも readiness に影響させない」はエラーには真だが遅延には偽。
# 鮮度クエリが応答しないと /readyz 全体が遅延し、外形監視（30 秒 timeout）側で
# 可用性 SLI の欠測に化ける。接続だけでなく文の実行にも上限を明示する


class _FakeCursor:
    async def fetchone(self):
        return (1, 2, 3)


class _FakeConn:
    async def execute(self, sql):
        return _FakeCursor()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def test_freshness_connect_sets_statement_timeout(monkeypatch):
    """鮮度クエリの接続が statement_timeout を明示していること。"""
    from app import db as db_module

    captured = {}

    async def fake_connect(dsn, **kwargs):
        captured.update(kwargs)
        return _FakeConn()

    monkeypatch.setattr(
        db_module.psycopg.AsyncConnection, "connect", fake_connect
    )
    result = asyncio.run(db_module.fetch_observation_freshness("dsn", 2))
    assert result == {
        "marker_age_seconds": 1,
        "stats_age_seconds": 2,
        "pgstattuple_age_seconds": 3,
    }
    assert "options" in captured, "statement_timeout が接続オプションに無い"
    assert "statement_timeout=2000" in captured["options"]
