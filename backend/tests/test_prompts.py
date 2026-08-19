"""システムプロンプト（気象業務法対応。ADR-0008）のテスト。

気象業務法は予報業務を許可制とし（第17条第1項）、警報の発表を気象庁以外に
禁止している（第23条）。システムプロンプトが予報・警報に当たる出力の生成を
禁止し、固定の案内文で断るよう LLM に指示していることを検証する。
"""

from fastapi.testclient import TestClient

import app.main as main_module
from app.llm.prompts import (
    FORBIDDEN_OUTPUT_KINDS,
    REFUSAL_NOTICE,
    SYSTEM_PROMPT,
    build_messages,
)


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


def test_build_messages_puts_system_prompt_first():
    messages = build_messages("台風について教えて")
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[-1] == {
        "role": "user",
        "content": "台風について教えて",
    }


def test_chat_response_has_no_references_field():
    """/chat は references を返さない（回答ごとの出典表示は行わない。ADR-0008）。

    出典表示はツール全体としてフロントエンドのフッターで常設表示し、
    個別ページ URL へは docs/data-sources.md で辿れるようにする。
    """
    with TestClient(main_module.app) as client:
        res = client.post("/chat", json={"message": "こんにちは"})
    assert res.status_code == 200
    body = res.json()
    assert "references" not in body
    assert set(body.keys()) == {"reply"}
