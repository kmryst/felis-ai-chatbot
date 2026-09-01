"""共有 contract fixture（ADR-0028 決定 9）に対する producer 変換の検証。

`docs/contracts/chat-sse/fixtures/` の raw stream 系列を決定 5 の表の実装
（app.llm.streaming.raw_stream_to_deltas）に通し、wire 出力が fixture の期待値と
一致することを検証する。実 LLM は呼ばない（ADR-0004。fixture がスタブ側の入力）。

fixture 5〜7 相当の系列（content filter 系・post-stop error）と途中切断系列が
「`done` なし・`error` 終端」になることは決定 9 がテストの必須条件と定めており、
本ファイルが必須条件の実装である。
"""

from collections.abc import AsyncIterator

import pytest

from app.llm.client import LLMError
from app.llm.prompts import NO_CONTEXT_NOTICE
from app.llm.streaming import raw_stream_to_deltas
from app.sse import error_class_for, format_sse_event
from sse_test_helpers import (
    load_fixture,
    load_raw_series_fixtures,
    parse_wire_sse,
    payloads_from_raw_sse,
)

RAW_FIXTURES = load_raw_series_fixtures()

# 決定 9 の必須条件の対象（`done` なし・`error` 終端でなければならない系列）
MUST_ERROR_TERMINATE = [
    "series-5-content-filter-finish",
    "series-6a-plural-error",
    "series-6b-singular-error-all-chunks",
    "series-7-post-stop-error",
    "series-8-truncated",
]


async def _aiter(payloads: list[str]) -> AsyncIterator[str]:
    for payload in payloads:
        yield payload


async def convert_to_wire_events(payloads: list[str]) -> list[dict]:
    """producer と同じ規則で raw payload 列を wire event 列へ変換する。"""
    events: list[dict] = []
    try:
        async for delta in raw_stream_to_deltas(_aiter(payloads)):
            events.append({"event": "message", "data": {"text": delta}})
    except LLMError as exc:
        events.append(
            {"event": "error", "data": {"class": error_class_for(exc)}}
        )
        return events
    events.append({"event": "done", "data": {}})
    return events


@pytest.mark.parametrize(
    "fixture", RAW_FIXTURES, ids=[f["name"] for f in RAW_FIXTURES]
)
async def test_raw_series_converts_to_expected_wire_events(fixture: dict):
    """raw 系列 → 決定 5 の表の変換 → fixture の期待 wire event 列に一致する。"""
    payloads = payloads_from_raw_sse(fixture["raw_sse"])
    events = await convert_to_wire_events(payloads)
    assert events == fixture["expected_wire_events"]


@pytest.mark.parametrize(
    "fixture", RAW_FIXTURES, ids=[f["name"] for f in RAW_FIXTURES]
)
async def test_terminal_event_matches_fixture_expectation(fixture: dict):
    """終端 event（done / error）と expect_done / expected_error_class の整合。"""
    payloads = payloads_from_raw_sse(fixture["raw_sse"])
    events = await convert_to_wire_events(payloads)
    last = events[-1]
    if fixture["expect_done"]:
        assert last == {"event": "done", "data": {}}
        assert fixture["expected_error_class"] is None
    else:
        assert last["event"] == "error"
        assert last["data"] == {"class": fixture["expected_error_class"]}
        # `done` は現れない（決定 6: error 終端で done を送らない）
        assert all(e["event"] != "done" for e in events)


def test_mandatory_error_termination_series_are_present_and_flagged():
    """決定 9 の必須条件: 系列 5〜7 と途中切断系列が fixture に存在し、
    すべて `done` なし・`error` 終端として定義されていること。"""
    names = {f["name"] for f in RAW_FIXTURES}
    for name in MUST_ERROR_TERMINATE:
        assert name in names, f"必須系列 {name} が fixture にない"
        fixture = load_fixture(name)
        assert fixture["expect_done"] is False
        assert fixture["expected_wire_events"][-1]["event"] == "error"


def test_series_6_has_both_plural_and_singular_error_variants():
    """決定 9 系列 6（2026-09-01 追記改訂）: 複数形 error の系列に加え、実測
    （run3-long）の単数形 error が全 chunk に同乗したまま stop に至る系列の
    両方があり、どちらも class content_filter で error 終端すること。"""
    for name in (
        "series-6a-plural-error",
        "series-6b-singular-error-all-chunks",
    ):
        fixture = load_fixture(name)
        assert fixture["expected_error_class"] == "content_filter"
        assert fixture["expect_done"] is False


async def test_singular_error_terminates_before_any_message():
    """run3-long 実測形状（先頭 chunk から error 同乗）では message を 1 件も
    送出せずに error 終端する（失敗系列は message 0 回以上 → error。決定 2）。"""
    fixture = load_fixture("series-6b-singular-error-all-chunks")
    events = await convert_to_wire_events(
        payloads_from_raw_sse(fixture["raw_sse"])
    )
    assert events == [
        {"event": "error", "data": {"class": "content_filter"}}
    ]


@pytest.mark.parametrize(
    "fixture", RAW_FIXTURES, ids=[f["name"] for f in RAW_FIXTURES]
)
async def test_wire_sse_is_canonical_serialization_of_expected_events(
    fixture: dict,
):
    """fixture の wire_sse は producer の直列化（format_sse_event）と byte 単位で
    一致する canonical wire example であること。"""
    rendered = "".join(
        format_sse_event(e["event"], e["data"])
        for e in fixture["expected_wire_events"]
    )
    assert rendered == fixture["wire_sse"]
    # 逆方向: wire_sse の parse が expected_wire_events に戻ること
    assert parse_wire_sse(fixture["wire_sse"]) == fixture["expected_wire_events"]


def test_guard_notice_fixture_matches_no_context_notice():
    """系列 2 の notice の text は NO_CONTEXT_NOTICE 全文（正本: prompts.py）。"""
    fixture = load_fixture("series-2-guard-notice")
    assert fixture["raw_sse"] is None
    assert fixture["expected_wire_events"] == [
        {"event": "notice", "data": {"text": NO_CONTEXT_NOTICE}},
        {"event": "done", "data": {}},
    ]
    rendered = format_sse_event(
        "notice", {"text": NO_CONTEXT_NOTICE}
    ) + format_sse_event("done", {})
    assert rendered == fixture["wire_sse"]


async def test_message_events_never_have_empty_text():
    """決定 4: すべての系列で空文字列の text を持つ message が現れないこと。"""
    for fixture in RAW_FIXTURES:
        events = await convert_to_wire_events(
            payloads_from_raw_sse(fixture["raw_sse"])
        )
        for event in events:
            if event["event"] == "message":
                assert event["data"]["text"] != ""
