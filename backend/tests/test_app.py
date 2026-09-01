"""health / readyz / request ID / /chat / 設定 fail-fast のテスト。

/chat の応答は SSE（ADR-0028）。本ファイルの /chat テストは wire event を
parse して従来の検証項目（stub 応答・ガード・コンテキスト受け渡し）を見る。
SSE 契約自体の網羅は test_chat_sse_endpoint.py / test_sse_contract.py。
"""

import dataclasses

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import InvalidEnvError, MissingEnvError, Settings
from app.llm.prompts import NO_CONTEXT_NOTICE
from app.rag import ScoredChunk
from sse_test_helpers import parse_wire_sse


def _reply_text(res) -> str:
    """SSE 応答から content event（message / notice）の text を連結して返す。"""
    events = parse_wire_sse(res.text)
    assert events[-1] == {"event": "done", "data": {}}
    return "".join(
        e["data"]["text"] for e in events if e["event"] in ("message", "notice")
    )


def _fake_search(chunks):
    async def fake(database_url, query_embedding, top_k, timeout):
        return chunks

    return fake


async def _fake_properties(database_url, timeout):
    return ["気温 / record_highest_temperature: 41.8 celsius（根拠原文: …伊勢崎…）"]


@pytest.fixture()
def client():
    # /chat は API キー必須（#107）。既存テストの主題は保護ではないため、
    # 正しいキーを既定ヘッダで送る（保護自体のテストは test_chat_protection.py）
    import os

    with TestClient(
        main_module.app, headers={"X-API-Key": os.environ["CHAT_API_KEY"]}
    ) as c:
        yield c


def test_livez_returns_200(client):
    res = client.get("/livez")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_readyz_returns_503_when_db_unreachable(client, monkeypatch):
    """DB に到達できない場合は 503。/livez は 200 のまま（liveness と分離）。"""
    unreachable = dataclasses.replace(
        main_module.settings,
        database_url="postgresql://x:x@127.0.0.1:1/nowhere",
        db_connect_timeout_seconds=1,
    )
    monkeypatch.setattr(main_module, "settings", unreachable)
    res = client.get("/readyz")
    assert res.status_code == 503
    assert res.json() == {"status": "unavailable", "db": "unreachable"}
    assert client.get("/livez").status_code == 200


def test_request_id_is_honored_and_generated(client):
    res = client.get("/livez", headers={"X-Request-ID": "req-abc-123"})
    assert res.headers["x-request-id"] == "req-abc-123"
    res2 = client.get("/livez")
    assert res2.headers["x-request-id"]  # 無ければ採番される
    assert res2.headers["x-request-id"] != "req-abc-123"


def test_chat_returns_stub_reply_when_search_hits(client, monkeypatch):
    """検索ヒット時はスタブ LLM の決定的応答を返す（実 LLM は呼ばない）。"""
    monkeypatch.setattr(
        main_module,
        "search_similar_documents",
        _fake_search([ScoredChunk(content="台風とは…", similarity=0.9)]),
    )
    monkeypatch.setattr(main_module, "fetch_property_records", _fake_properties)
    res = client.post("/chat", json={"message": "台風について教えて"})
    assert res.status_code == 200
    assert res.headers["content-type"] == "text/event-stream; charset=utf-8"
    reply = _reply_text(res)
    assert reply.startswith("[stub]")
    assert "台風について教えて" in reply


def test_chat_passes_context_to_llm_when_search_hits(client, monkeypatch):
    """検索ヒット時、チャンクと数値記録がコンテキストとして LLM に渡る。"""
    monkeypatch.setattr(
        main_module,
        "search_similar_documents",
        _fake_search([ScoredChunk(content="台風とは…", similarity=0.9)]),
    )
    monkeypatch.setattr(main_module, "fetch_property_records", _fake_properties)
    captured: list[list[dict[str, str]]] = []
    original_chat_stream = main_module.app.state.llm.chat_stream

    def spy_chat_stream(messages):
        captured.append(messages)
        return original_chat_stream(messages)

    monkeypatch.setattr(
        main_module.app.state.llm, "chat_stream", spy_chat_stream
    )
    res = client.post("/chat", json={"message": "台風について教えて"})
    assert res.status_code == 200
    assert len(captured) == 1
    context_text = "\n".join(m["content"] for m in captured[0])
    assert "台風とは…" in context_text
    assert "41.8" in context_text


def test_chat_guard_zero_hits_does_not_call_llm(client, monkeypatch):
    """検索 0 件なら LLM を呼ばずに固定文言を返す（ADR-0010 の本丸）。

    LLM の chat が呼ばれたら即 fail する差し替えで「呼ばれないこと」を担保する。
    """
    monkeypatch.setattr(
        main_module, "search_similar_documents", _fake_search([])
    )

    def must_not_be_called(messages):
        raise AssertionError("ガードが素通りして LLM chat_stream が呼ばれた")

    monkeypatch.setattr(
        main_module.app.state.llm, "chat_stream", must_not_be_called
    )
    res = client.post("/chat", json={"message": "おすすめのラーメン屋は？"})
    assert res.status_code == 200
    assert _reply_text(res) == NO_CONTEXT_NOTICE


def test_chat_guard_below_threshold_does_not_call_llm(client, monkeypatch):
    """最上位の類似度が閾値未満でも LLM を呼ばずに固定文言を返す。"""
    below = main_module.settings.rag_similarity_threshold - 0.01
    monkeypatch.setattr(
        main_module,
        "search_similar_documents",
        _fake_search([ScoredChunk(content="無関係なチャンク", similarity=below)]),
    )

    def must_not_be_called(messages):
        raise AssertionError("ガードが素通りして LLM chat_stream が呼ばれた")

    monkeypatch.setattr(
        main_module.app.state.llm, "chat_stream", must_not_be_called
    )
    res = client.post("/chat", json={"message": "おすすめのラーメン屋は？"})
    assert res.status_code == 200
    assert _reply_text(res) == NO_CONTEXT_NOTICE


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


def test_settings_stub_provider_does_not_require_azure_vars(monkeypatch):
    """LLM_PROVIDER=stub（既定）では Azure 用変数なしで起動できる（ADR-0004）。"""
    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.llm_provider == "stub"


def test_settings_azure_provider_requires_azure_vars(monkeypatch):
    """LLM_PROVIDER=azure-openai では endpoint / api key 欠落で即 fail する。"""
    monkeypatch.setenv("LLM_PROVIDER", "azure-openai")
    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(MissingEnvError) as exc_info:
        Settings.from_env()
    assert "AZURE_OPENAI_ENDPOINT" in str(exc_info.value)
    assert "AZURE_OPENAI_API_KEY" in str(exc_info.value)


def test_settings_repr_does_not_leak_azure_api_key(monkeypatch):
    """API キーは repr に出さない（ログ・エラー画面への漏出防止）。"""
    monkeypatch.setenv("LLM_PROVIDER", "azure-openai")
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/"
    )
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret-value-do-not-print")
    settings = Settings.from_env()
    assert "secret-value-do-not-print" not in repr(settings)
