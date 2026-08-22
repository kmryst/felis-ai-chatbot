"""/chat 保護ゲート（API キー + 緊急遮断フラグ。Issue #107）のテスト。

- /chat のみ保護し、/health・/readyz は無認証のまま（外形監視 #106 と両立）
- キー未設定は fail-closed（404）: キーを配らないデプロイで LLM 課金経路が
  無認証公開される事故を「/chat が無い」側に倒す
"""

import dataclasses
import os

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.llm.prompts import NO_CONTEXT_NOTICE

_KEY = os.environ["CHAT_API_KEY"]


@pytest.fixture()
def raw_client():
    """既定ヘッダを持たないクライアント（キー無し・誤キーの検証用）。"""
    with TestClient(main_module.app) as c:
        yield c


def _patch_search_empty(monkeypatch):
    """DB に触れないよう検索を 0 件で返す（ガードにより LLM も呼ばれない）。"""

    async def fake(database_url, query_embedding, top_k, timeout):
        return []

    monkeypatch.setattr(main_module, "search_similar_documents", fake)


def test_chat_without_key_returns_401(raw_client):
    res = raw_client.post("/chat", json={"message": "台風とは"})
    assert res.status_code == 401


def test_chat_with_wrong_key_returns_401(raw_client):
    res = raw_client.post(
        "/chat",
        json={"message": "台風とは"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert res.status_code == 401


def test_chat_with_correct_key_passes(raw_client, monkeypatch):
    _patch_search_empty(monkeypatch)
    res = raw_client.post(
        "/chat",
        json={"message": "台風とは"},
        headers={"X-API-Key": _KEY},
    )
    assert res.status_code == 200
    assert res.json()["reply"] == NO_CONTEXT_NOTICE


def test_chat_disabled_returns_404_even_with_correct_key(
    raw_client, monkeypatch
):
    disabled = dataclasses.replace(main_module.settings, chat_disabled=True)
    monkeypatch.setattr(main_module, "settings", disabled)
    res = raw_client.post(
        "/chat",
        json={"message": "台風とは"},
        headers={"X-API-Key": _KEY},
    )
    assert res.status_code == 404


def test_chat_unset_key_returns_404_fail_closed(raw_client, monkeypatch):
    """CHAT_API_KEY 未設定なら、どんなキーを出しても /chat は存在しない扱い。"""
    no_key = dataclasses.replace(main_module.settings, chat_api_key="")
    monkeypatch.setattr(main_module, "settings", no_key)
    res = raw_client.post(
        "/chat",
        json={"message": "台風とは"},
        headers={"X-API-Key": _KEY},
    )
    assert res.status_code == 404


def test_readyz_and_health_not_gated_when_chat_disabled(
    raw_client, monkeypatch
):
    """遮断フラグ ON でも liveness / readiness は生きている（外形監視と両立）。"""
    disabled = dataclasses.replace(main_module.settings, chat_disabled=True)
    monkeypatch.setattr(main_module, "settings", disabled)

    async def fake_ready(database_url, timeout):
        return True

    monkeypatch.setattr(main_module, "check_database_ready", fake_ready)

    assert raw_client.get("/health").status_code == 200
    res = raw_client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "db": "ok"}
