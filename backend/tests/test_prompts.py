"""システムプロンプト（気象業務法対応。ADR-0008）のテスト。

気象業務法は予報業務を許可制とし（第17条第1項）、警報の発表を気象庁以外に
禁止している（第23条）。システムプロンプトが予報・警報に当たる出力の生成を
禁止し、固定の案内文で断るよう LLM に指示していることを検証する。
"""

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.llm.prompts import (
    CONTEXT_HEADER,
    FORBIDDEN_OUTPUT_KINDS,
    NO_CITATION_INSTRUCTION,
    NO_CONTEXT_NOTICE,
    REFUSAL_NOTICE,
    SYSTEM_PROMPT,
    build_context,
    build_messages,
)
from app.rag import ScoredChunk


def test_system_prompt_forbids_forecast_and_warning_outputs():
    """予報・警報・独自の危険度判定が禁止事項として明示されている。"""
    # FORBIDDEN_OUTPUT_KINDS が空になると下のループが空回りして素通りし、
    # 気象業務法対応の形骸化を検出できないため、まず非空を保証する
    # （予報・警報・独自の危険度判定の 3 種類が最低ライン）
    assert len(FORBIDDEN_OUTPUT_KINDS) >= 3, "禁止事項の定数が減っている"
    assert all(kind for kind in FORBIDDEN_OUTPUT_KINDS), "空文字の禁止事項がある"
    assert "禁止" in SYSTEM_PROMPT
    for kind in FORBIDDEN_OUTPUT_KINDS:
        assert kind in SYSTEM_PROMPT, f"禁止対象 {kind!r} がプロンプトにない"
    # 禁止の根拠となる法令が明示されている
    assert "気象業務法" in SYSTEM_PROMPT
    assert "第17条" in SYSTEM_PROMPT
    assert "第23条" in SYSTEM_PROMPT


def test_system_prompt_contains_refusal_notice():
    """予報を求められたときの固定の案内文（拒否文言）が指示されている。"""
    assert REFUSAL_NOTICE in SYSTEM_PROMPT
    # 案内文は気象庁ホームページへ誘導し、断る内容であること
    assert "予報・警報を提供しません" in REFUSAL_NOTICE
    assert "気象庁ホームページ" in REFUSAL_NOTICE


def test_system_prompt_allows_past_records_and_explanations():
    """過去の記録・一般的な解説は回答してよいことが明示されている。"""
    assert "過去の記録" in SYSTEM_PROMPT
    assert "解説" in SYSTEM_PROMPT


def test_system_prompt_forbids_citation_in_reply_body():
    """回答本文への出典表記の禁止が指示されている（ADR-0008）。

    実 LLM が回答末尾に「（参考：気象庁｜…）」という出典表記を自記した
    実測があり、出典はフッターと docs/data-sources.md に集約する方針
    （ADR-0008）に反するため、プロンプトで明示的に禁止する。
    """
    # NO_CITATION_INSTRUCTION が空になると次の in 検証が素通りするため、
    # まず禁止の中身（出典・書かない）が残っていることを保証する
    assert "出典" in NO_CITATION_INSTRUCTION
    assert "書かない" in NO_CITATION_INSTRUCTION
    assert NO_CITATION_INSTRUCTION in SYSTEM_PROMPT


def test_no_context_notice_states_missing_reference():
    """ガード発動時の固定文言が「参照資料に記載がない」ことを伝える。"""
    assert "参照資料に記載がない" in NO_CONTEXT_NOTICE
    assert "気象庁ホームページ" in NO_CONTEXT_NOTICE


def test_build_context_includes_chunks_and_property_records():
    context = build_context(
        ["台風とは…", "猛烈な雨は…"], ["気温 / record_highest_temperature: 41.8 celsius"]
    )
    assert context.startswith(CONTEXT_HEADER)
    assert "台風とは…" in context
    assert "猛烈な雨は…" in context
    assert "41.8" in context


def test_build_messages_puts_system_prompt_first_and_context_second():
    context = build_context(["台風とは…"], [])
    messages = build_messages("台風について教えて", context)
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1] == {"role": "system", "content": context}
    assert messages[-1] == {
        "role": "user",
        "content": "台風について教えて",
    }


def test_build_messages_rejects_empty_context():
    """空コンテキストで LLM を呼ぶ経路を作らない（ADR-0010 のガードの二重化）。"""
    with pytest.raises(ValueError):
        build_messages("台風について教えて", "")


def test_chat_response_has_no_references_field(monkeypatch):
    """/chat は references を返さない（回答ごとの出典表示は行わない。ADR-0008）。

    出典表示はツール全体としてフロントエンドのフッターで常設表示し、
    個別ページ URL へは docs/data-sources.md で辿れるようにする。
    RAG 検索は DB を使わないフェイクに差し替える（実 DB・実 LLM は使わない）。
    """

    async def fake_search(database_url, query_embedding, top_k, timeout):
        return [ScoredChunk(content="台風とは…", similarity=0.9)]

    async def fake_properties(database_url, timeout):
        return ["気温 / record_highest_temperature: 41.8 celsius"]

    monkeypatch.setattr(main_module, "search_similar_documents", fake_search)
    monkeypatch.setattr(main_module, "fetch_property_records", fake_properties)
    import os

    with TestClient(
        main_module.app, headers={"X-API-Key": os.environ["CHAT_API_KEY"]}
    ) as client:
        res = client.post("/chat", json={"message": "台風について教えて"})
    assert res.status_code == 200
    # SSE 応答（ADR-0028）: どの event の data にも references を含めない。
    # message の data は text のみ（出典表示は wire に載らない）
    from sse_test_helpers import parse_wire_sse

    events = parse_wire_sse(res.text)
    message_events = [e for e in events if e["event"] == "message"]
    assert message_events
    for event in events:
        assert "references" not in event["data"]
    for event in message_events:
        assert set(event["data"].keys()) == {"text"}
