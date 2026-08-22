"""/readyz の観測鮮度フィールド（Issue #104）のテスト。実 DB には接続しない。"""

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
