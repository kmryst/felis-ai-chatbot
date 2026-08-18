"""システムプロンプト（NASA AI 条項準拠。ADR-0006）のテスト。

NASA Brand Center の AI 条項は情報の NASA への帰属を禁止している。
システムプロンプトがその禁止を LLM に指示していることを検証する。
"""

from fastapi.testclient import TestClient

import app.main as main_module
from app.llm.prompts import (
    FORBIDDEN_ATTRIBUTION_PHRASES,
    SYSTEM_PROMPT,
    build_messages,
)


def test_system_prompt_forbids_attribution_phrases():
    """帰属表現（「NASA によると」等）が禁止事項として明示されている。"""
    assert "禁止" in SYSTEM_PROMPT
    for phrase in FORBIDDEN_ATTRIBUTION_PHRASES:
        assert phrase in SYSTEM_PROMPT, f"禁止対象 {phrase!r} がプロンプトにない"
    # 代替の言い方（資料参照の形）へ誘導している
    assert "参照資料には" in SYSTEM_PROMPT


def test_system_prompt_forbids_implying_nasa_endorsement():
    """NASA による審査・許可・公認を示唆する表現の禁止が明示されている。"""
    for word in ("審査", "許可", "公認"):
        assert word in SYSTEM_PROMPT


def test_build_messages_puts_system_prompt_first():
    messages = build_messages("ブラックホールについて教えて")
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[-1] == {
        "role": "user",
        "content": "ブラックホールについて教えて",
    }


def test_chat_response_has_references_field():
    """/chat は references（未加工の原文抜粋の器）を返す。

    RAG 本結線は次フェーズのため現状は空リスト。出典の帰属は AI 生成文
    （reply）ではなくこのフィールドの未加工引用にのみ付ける（ADR-0006）。
    """
    with TestClient(main_module.app) as client:
        res = client.post("/chat", json={"message": "こんにちは"})
    assert res.status_code == 200
    body = res.json()
    assert body["references"] == []
