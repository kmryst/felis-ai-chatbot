"""LLMClient.chat_stream の retry 境界（ADR-0028 決定 10）と打ち切りの検証。

- retry は「最初の content delta を受信する前」に限る。受信後の upstream 失敗は
  retry せず即座に送出する（部分出力の重複送出を作らない）
- timeout（1 試行あたり）は最初の content delta の受信までに適用する
- 呼び出し側が generator を close したら（client 切断）、transport の stream まで
  連鎖して閉じる（決定 2: provider stream の打ち切り）

実 LLM は呼ばない（ADR-0004）。故障はスクリプト化した fake transport で注入する。
"""

import asyncio
import json
from collections.abc import AsyncIterator

import pytest

from app.llm.client import (
    LLMBadRequestError,
    LLMClient,
    LLMContentFilterError,
    LLMServerError,
    LLMTimeoutError,
    RetryConfig,
    StubTransport,
)
from sse_test_helpers import (
    FakeRawStreamTransport,
    load_fixture,
    payloads_from_raw_sse,
)

FAST = RetryConfig(
    max_attempts=3,
    timeout_seconds=1,
    base_delay_seconds=0.01,
    max_delay_seconds=0.05,
)

MESSAGES = [{"role": "user", "content": "台風とは"}]


def _payload(content: str | None = None, finish: str | None = None) -> str:
    choice: dict = {
        "content_filter_results": {},
        "delta": {} if content is None else {"content": content},
        "finish_reason": finish,
        "index": 0,
        "logprobs": None,
    }
    return json.dumps({"choices": [choice]}, ensure_ascii=False)


NORMAL_PAYLOADS = [
    _payload(content=""),
    _payload(content="台風は"),
    _payload(content="熱帯低気圧です。"),
    _payload(finish="stop"),
    "[DONE]",
]


class ScriptedStreamTransport:
    """試行ごとの挙動をスクリプトで注入する fake transport。

    script の各要素は 1 試行分の挙動:
    - ("fail", exc): payload を返す前に失敗する（接続確立局面の失敗）
    - ("payloads", [...]): payload 列を返して正常終了する
    - ("payloads_then_fail", [...], exc): payload を返した後に失敗する
      （stream 途中の upstream 失敗）
    - ("hang",): 最初の payload を返さず待ち続ける（timeout 検証用）
    """

    def __init__(self, script: list[tuple]) -> None:
        self._script = script
        self.stream_calls = 0
        self.closed_streams = 0

    async def chat_stream(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        step = self._script[self.stream_calls]
        self.stream_calls += 1
        try:
            match step[0]:
                case "fail":
                    raise step[1]
                case "payloads":
                    for payload in step[1]:
                        yield payload
                case "payloads_then_fail":
                    for payload in step[1]:
                        yield payload
                    raise step[2]
                case "hang":
                    await asyncio.sleep(3600)
        finally:
            self.closed_streams += 1


async def _collect(agen: AsyncIterator[str]) -> list[str]:
    return [delta async for delta in agen]


# --- retry 境界: 最初の content delta 受信前 -----------------------------------


async def test_retryable_failure_before_first_delta_is_retried():
    """接続確立局面の retryable 失敗（server error）は retry され、成功する。"""
    transport = ScriptedStreamTransport(
        [
            ("fail", LLMServerError("一時障害")),
            ("fail", LLMServerError("一時障害")),
            ("payloads", NORMAL_PAYLOADS),
        ]
    )
    client = LLMClient(transport, FAST)
    deltas = await _collect(client.chat_stream(MESSAGES))
    assert deltas == ["台風は", "熱帯低気圧です。"]
    assert transport.stream_calls == 3


async def test_retries_exhausted_before_first_delta_raises_last_error():
    """全試行が最初の content delta 前に失敗したら最後のエラーを送出する。"""
    transport = ScriptedStreamTransport(
        [("fail", LLMServerError("down"))] * 3
    )
    client = LLMClient(transport, FAST)
    with pytest.raises(LLMServerError):
        await _collect(client.chat_stream(MESSAGES))
    assert transport.stream_calls == 3


async def test_non_retryable_failure_before_first_delta_fails_immediately():
    """bad request 系は retry しても直らないため 1 試行で即失敗する。"""
    transport = ScriptedStreamTransport([("fail", LLMBadRequestError("bad"))])
    client = LLMClient(transport, FAST)
    with pytest.raises(LLMBadRequestError):
        await _collect(client.chat_stream(MESSAGES))
    assert transport.stream_calls == 1


async def test_content_filter_error_is_not_retried():
    """error field を先頭 chunk から検出した系列（run3-long 実測形状）は
    content filter 起因であり、retry せず即失敗する（fail-closed。決定 6）。"""
    fixture = load_fixture("series-6b-singular-error-all-chunks")
    transport = FakeRawStreamTransport(
        payloads_from_raw_sse(fixture["raw_sse"])
    )
    client = LLMClient(transport, FAST)
    with pytest.raises(LLMContentFilterError):
        await _collect(client.chat_stream(MESSAGES))
    assert transport.stream_calls == 1
    assert transport.closed


async def test_empty_content_stream_is_fail_closed_and_retried():
    """content 0 件で done に至る stream は文法（message 1 回以上 → done）を
    満たせないため server error 系として扱う（retry 対象）。"""
    empty = [_payload(content=""), _payload(finish="stop"), "[DONE]"]
    transport = ScriptedStreamTransport(
        [("payloads", empty), ("payloads", empty), ("payloads", empty)]
    )
    client = LLMClient(transport, FAST)
    with pytest.raises(LLMServerError):
        await _collect(client.chat_stream(MESSAGES))
    assert transport.stream_calls == 3


async def test_timeout_before_first_delta_is_enforced_and_stream_closed():
    """最初の content delta までの timeout（1 試行あたり）が効き、timeout した
    試行の transport stream は閉じられる（垂れ流しを作らない）。"""
    transport = ScriptedStreamTransport([("hang",), ("hang",)])
    client = LLMClient(
        transport,
        RetryConfig(
            max_attempts=2,
            timeout_seconds=0.05,
            base_delay_seconds=0.01,
            max_delay_seconds=0.02,
        ),
    )
    with pytest.raises(LLMTimeoutError):
        await _collect(client.chat_stream(MESSAGES))
    assert transport.stream_calls == 2
    assert transport.closed_streams == 2


# --- retry 境界: 最初の content delta 受信後 -----------------------------------


async def test_failure_after_first_delta_is_not_retried():
    """最初の content delta 受信後の upstream 失敗は retry せず送出する
    （同じ内容の重複送出を作らない。決定 10 の本丸）。"""
    transport = ScriptedStreamTransport(
        [
            (
                "payloads_then_fail",
                [_payload(content=""), _payload(content="部分応答")],
                LLMServerError("stream 途中の接続断"),
            ),
            # retry されないこと（2 試行目が定義されていても使われない）
            ("payloads", NORMAL_PAYLOADS),
        ]
    )
    client = LLMClient(transport, FAST)
    received: list[str] = []
    with pytest.raises(LLMServerError):
        async for delta in client.chat_stream(MESSAGES):
            received.append(delta)
    assert received == ["部分応答"]
    assert transport.stream_calls == 1


async def test_truncated_stream_after_first_delta_is_not_retried():
    """[DONE] なしの stream 終了（途中切断系列）も受信後は retry しない。"""
    fixture = load_fixture("series-8-truncated")
    transport = FakeRawStreamTransport(
        payloads_from_raw_sse(fixture["raw_sse"])
    )
    client = LLMClient(transport, FAST)
    received: list[str] = []
    with pytest.raises(LLMServerError):
        async for delta in client.chat_stream(MESSAGES):
            received.append(delta)
    assert received == ["秋は", "台風の季節です。"]
    assert transport.stream_calls == 1


async def test_no_timeout_between_deltas_after_first():
    """最初の content delta 受信後の delta 間隔には timeout を適用しない
    （token 間隔の閾値は SLO 側の決定手順で決める。数値を先取りしない）。"""

    class SlowMiddleTransport:
        async def chat_stream(self, messages):
            yield _payload(content="はじめ")
            await asyncio.sleep(0.2)  # timeout_seconds=0.05 より長い間隔
            yield _payload(content="おわり")
            yield _payload(finish="stop")
            yield "[DONE]"

    client = LLMClient(
        SlowMiddleTransport(),
        RetryConfig(
            max_attempts=1,
            timeout_seconds=0.05,
            base_delay_seconds=0.01,
            max_delay_seconds=0.02,
        ),
    )
    deltas = await _collect(client.chat_stream(MESSAGES))
    assert deltas == ["はじめ", "おわり"]


# --- client 切断: provider stream の打ち切り（決定 2） --------------------------


async def test_closing_client_generator_closes_transport_stream():
    """途中で consumer が generator を close したら transport まで連鎖して
    閉じる（client 切断時に provider stream を打ち切る）。"""
    fixture = load_fixture("series-1-normal")
    transport = FakeRawStreamTransport(
        payloads_from_raw_sse(fixture["raw_sse"])
    )
    client = LLMClient(transport, FAST)
    stream = client.chat_stream(MESSAGES)
    first = await anext(stream)
    assert first == "注意報は"
    assert not transport.closed
    await stream.aclose()
    assert transport.closed


# --- stub transport も同一契約の stream を生成する（ADR-0004） ------------------


async def test_stub_transport_streams_same_reply_as_chat():
    """StubTransport.chat_stream の delta 連結は chat() の応答と一致する。"""
    client = LLMClient(StubTransport(), FAST)
    deltas = await _collect(client.chat_stream(MESSAGES))
    assert deltas  # message 1 回以上
    assert all(delta != "" for delta in deltas)
    reply = await LLMClient(StubTransport(), FAST).chat(MESSAGES)
    assert "".join(deltas) == reply


async def test_stub_transport_stream_fault_injection_is_retried():
    """スタブの故障注入（先頭 N 回失敗）は接続確立局面の失敗として retry される。"""
    transport = StubTransport(fail_first_n=2)
    client = LLMClient(transport, FAST)
    deltas = await _collect(client.chat_stream(MESSAGES))
    assert "".join(deltas).startswith("[stub]")
    assert transport.calls == 3
