"""POST /chat の SSE 応答（ADR-0028 producer）の endpoint レベル検証。

共有 fixture の raw 系列を fake transport から流し、/chat の応答 body が
fixture の canonical wire example（wire_sse）と byte 単位で一致することを
検証する。実 LLM・実 DB は呼ばない（ADR-0004）。

ストリーム開始前の失敗（ゲート 404 / 401・validation 422・embedding 502・
検索 503）が SSE を開始せず現行 HTTP status のままであることも本ファイルで
検証する（ゲート自体の網羅は test_chat_protection.py）。
"""

import os

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.llm.client import LLMClient, LLMError, RetryConfig
from app.rag import ScoredChunk
from sse_test_helpers import (
    FakeRawStreamTransport,
    load_fixture,
    parse_wire_sse,
    payloads_from_raw_sse,
)

FAST = RetryConfig(
    max_attempts=2,
    timeout_seconds=1,
    base_delay_seconds=0.01,
    max_delay_seconds=0.05,
)


@pytest.fixture()
def client():
    with TestClient(
        main_module.app, headers={"X-API-Key": os.environ["CHAT_API_KEY"]}
    ) as c:
        yield c


def _patch_rag_hit(monkeypatch):
    async def fake_search(database_url, query_embedding, top_k, timeout):
        return [ScoredChunk(content="台風とは…", similarity=0.9)]

    async def fake_properties(database_url, timeout):
        return ["気温 / record_highest_temperature: 41.8 celsius"]

    monkeypatch.setattr(main_module, "search_similar_documents", fake_search)
    monkeypatch.setattr(
        main_module, "fetch_property_records", fake_properties
    )


def _install_fixture_llm(monkeypatch, fixture_name: str) -> FakeRawStreamTransport:
    fixture = load_fixture(fixture_name)
    transport = FakeRawStreamTransport(
        payloads_from_raw_sse(fixture["raw_sse"])
    )
    monkeypatch.setattr(
        main_module.app.state, "llm", LLMClient(transport, FAST)
    )
    return transport


def _post_chat(client):
    return client.post("/chat", json={"message": "台風について教えて"})


# --- 正常系: fixture の canonical wire example と byte 一致 ---------------------


def test_chat_streams_series_1_wire_bytes_exactly(client, monkeypatch):
    """系列 1（正常）: 応答 body が fixture の wire_sse と完全一致する。"""
    _patch_rag_hit(monkeypatch)
    _install_fixture_llm(monkeypatch, "series-1-normal")
    res = _post_chat(client)
    fixture = load_fixture("series-1-normal")
    assert res.status_code == 200
    assert res.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert res.headers["cache-control"] == "no-cache"
    assert res.text == fixture["wire_sse"]


def test_chat_event_grammar_message_then_done(client, monkeypatch):
    """event 文法（決定 2）: message 1 回以上 → done ちょうど 1 回・最後。"""
    _patch_rag_hit(monkeypatch)
    _install_fixture_llm(monkeypatch, "series-1-normal")
    events = parse_wire_sse(_post_chat(client).text)
    kinds = [e["event"] for e in events]
    assert kinds.count("done") == 1
    assert kinds[-1] == "done"
    assert kinds[:-1] == ["message"] * (len(kinds) - 1)
    assert len(kinds) >= 2  # message 1 回以上


# --- guard 経路: notice → done（決定 3。LLM を呼ばない） ------------------------


def test_guard_path_streams_series_2_wire_bytes_exactly(client, monkeypatch):
    """系列 2（guard notice）: 検索 0 件で notice → done を SSE で返し、
    LLM chat_stream は呼ばれない。"""

    async def fake_search(database_url, query_embedding, top_k, timeout):
        return []

    monkeypatch.setattr(main_module, "search_similar_documents", fake_search)

    def must_not_be_called(messages):
        raise AssertionError("guard 発火時に LLM chat_stream が呼ばれた")

    monkeypatch.setattr(
        main_module.app.state.llm, "chat_stream", must_not_be_called
    )
    res = _post_chat(client)
    fixture = load_fixture("series-2-guard-notice")
    assert res.status_code == 200
    assert res.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert res.text == fixture["wire_sse"]


# --- 失敗系列: error 終端（done なし） ------------------------------------------


@pytest.mark.parametrize(
    "fixture_name",
    [
        "series-5-content-filter-finish",
        "series-6a-plural-error",
        "series-6b-singular-error-all-chunks",
        "series-7-post-stop-error",
        "series-8-truncated",
    ],
)
def test_error_series_stream_error_and_no_done(
    client, monkeypatch, fixture_name
):
    """系列 5〜7・途中切断: HTTP 200 の SSE として開始し、`done` を出さず
    `error` で終端する（撤回契約の producer 義務・fail-closed）。"""
    _patch_rag_hit(monkeypatch)
    _install_fixture_llm(monkeypatch, fixture_name)
    res = _post_chat(client)
    fixture = load_fixture(fixture_name)
    assert res.status_code == 200
    assert res.text == fixture["wire_sse"]
    events = parse_wire_sse(res.text)
    assert events[-1]["event"] == "error"
    assert events[-1]["data"] == {"class": fixture["expected_error_class"]}
    assert all(e["event"] != "done" for e in events)


def test_error_data_contains_only_class(client, monkeypatch):
    """error の data は class のみ（詳細メッセージ・upstream 応答本文を
    含めない。決定 2）。"""
    _patch_rag_hit(monkeypatch)
    _install_fixture_llm(monkeypatch, "series-6a-plural-error")
    events = parse_wire_sse(_post_chat(client).text)
    error_event = events[-1]
    assert set(error_event["data"].keys()) == {"class"}


def test_retries_exhausted_before_first_delta_becomes_error_event(
    client, monkeypatch
):
    """chat stream の接続確立局面の失敗（retry 尽き）は SSE の error event で
    終端する（class は分類どおり）。"""
    _patch_rag_hit(monkeypatch)

    class FailingTransport:
        async def chat_stream(self, messages):
            from app.llm.client import LLMRateLimitError

            raise LLMRateLimitError("rate limited")
            yield  # generator にするための到達しない yield

        async def embed(self, text):
            return [0.1] * 1536

    monkeypatch.setattr(
        main_module.app.state, "llm", LLMClient(FailingTransport(), FAST)
    )
    res = _post_chat(client)
    assert res.status_code == 200
    events = parse_wire_sse(res.text)
    assert events == [{"event": "error", "data": {"class": "rate_limit"}}]


# --- ストリーム開始前の失敗: SSE を開始せず現行 HTTP status ----------------------


def test_embed_failure_returns_502_without_sse(client, monkeypatch):
    """embedding の失敗は SSE を開始せず 502 を返す（現行分類の維持）。"""

    class EmbedFailLLM:
        async def embed(self, text):
            raise LLMError("embed failed")

        async def chat_stream(self, messages):
            raise AssertionError("embed 失敗時に chat_stream が呼ばれた")

    monkeypatch.setattr(main_module.app.state, "llm", EmbedFailLLM())
    res = _post_chat(client)
    assert res.status_code == 502
    assert "text/event-stream" not in res.headers["content-type"]


def test_search_failure_returns_503_without_sse(client, monkeypatch):
    """検索の失敗は SSE を開始せず 503 を返す（現行分類の維持）。"""

    async def broken_search(database_url, query_embedding, top_k, timeout):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        main_module, "search_similar_documents", broken_search
    )
    res = _post_chat(client)
    assert res.status_code == 503
    assert "text/event-stream" not in res.headers["content-type"]


def test_validation_failure_returns_422_without_sse(client):
    """validation の失敗（空 message）は SSE を開始せず 422 を返す。"""
    res = client.post("/chat", json={"message": ""})
    assert res.status_code == 422
    assert "text/event-stream" not in res.headers["content-type"]


# --- 応答終了後に provider stream が閉じられていること（決定 2） -----------------


def test_transport_stream_is_closed_after_response(client, monkeypatch):
    """応答完了時点で transport の raw stream が close されている
    （client 切断時の打ち切りと同じ close 連鎖が endpoint 経由でも機能する）。"""
    _patch_rag_hit(monkeypatch)
    transport = _install_fixture_llm(monkeypatch, "series-1-normal")
    _post_chat(client)
    assert transport.closed
