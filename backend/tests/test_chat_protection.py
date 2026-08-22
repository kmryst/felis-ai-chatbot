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


# --- キー強度の境界（外部レビュー指摘: 空白のみ・短いキーが「鍵」として通る穴） ---


def test_whitespace_only_key_is_fail_closed(raw_client, monkeypatch):
    """空白のみのキーは「未設定」と同じ扱い（404）でなければならない。

    修正前の実測: CHAT_API_KEY='   ' が truthy として通り、X-API-Key: '   ' で
    /chat が LLM 呼び出しまで到達する。
    """
    ws = dataclasses.replace(main_module.settings, chat_api_key="   ")
    monkeypatch.setattr(main_module, "settings", ws)
    res = raw_client.post(
        "/chat", json={"message": "台風とは"}, headers={"X-API-Key": "   "}
    )
    assert res.status_code == 404


def test_short_key_is_fail_closed(raw_client, monkeypatch):
    """最小長（32 文字）未満のキーは鍵として成立させない（404）。"""
    short = dataclasses.replace(main_module.settings, chat_api_key="k" * 31)
    monkeypatch.setattr(main_module, "settings", short)
    res = raw_client.post(
        "/chat", json={"message": "台風とは"}, headers={"X-API-Key": "k" * 31}
    )
    assert res.status_code == 404


def test_min_length_key_is_accepted(raw_client, monkeypatch):
    """最小長ちょうど（32 文字）は有効な鍵として機能する。"""
    ok = dataclasses.replace(main_module.settings, chat_api_key="k" * 32)
    monkeypatch.setattr(main_module, "settings", ok)
    _patch_search_empty(monkeypatch)
    res = raw_client.post(
        "/chat", json={"message": "台風とは"}, headers={"X-API-Key": "k" * 32}
    )
    assert res.status_code == 200


def test_from_env_rejects_short_key(monkeypatch):
    """起動時検証: 32 文字未満の CHAT_API_KEY は InvalidEnvError で即 fail。"""
    from app.config import InvalidEnvError, Settings

    monkeypatch.setenv("CHAT_API_KEY", "short-key")
    with pytest.raises(InvalidEnvError):
        Settings.from_env()


def test_from_env_strips_whitespace_key_to_fail_closed(monkeypatch):
    """起動時検証: 空白のみは strip されて未設定（fail-closed）扱い。起動は失敗しない。"""
    from app.config import Settings

    monkeypatch.setenv("CHAT_API_KEY", "   ")
    settings = Settings.from_env()
    assert settings.chat_api_key == ""
