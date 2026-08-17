"""LLM クライアントの故障注入テスト（ADR-0004）。

「実装した」ではなく「意図的に失敗させて確認した」と言うためのテスト群。
実 LLM・外部 API は一切呼ばない。sleep を短くするため delay は極小値を使う。
"""

import random

import pytest

from app.llm.client import (
    EMBEDDING_DIMENSIONS,
    LLMBadRequestError,
    LLMClient,
    LLMServerError,
    LLMTimeoutError,
    RetryConfig,
    StubTransport,
    create_llm_client,
)

FAST = dict(base_delay_seconds=0.01, max_delay_seconds=0.05)


async def test_retry_succeeds_after_transient_failures():
    """先頭2回失敗を注入 → 3回目で成功する（計3呼び出し）。"""
    transport = StubTransport(fail_first_n=2)
    client = LLMClient(
        transport, RetryConfig(max_attempts=3, timeout_seconds=1, **FAST)
    )
    reply = await client.chat([{"role": "user", "content": "hello"}])
    assert "hello" in reply
    assert transport.calls == 3


async def test_retry_gives_up_after_max_attempts():
    """失敗し続けると上限回数で諦め、最後のエラーを送出する。"""
    transport = StubTransport(fail_first_n=99)
    client = LLMClient(
        transport, RetryConfig(max_attempts=3, timeout_seconds=1, **FAST)
    )
    with pytest.raises(LLMServerError):
        await client.chat([{"role": "user", "content": "x"}])
    assert transport.calls == 3


async def test_non_retryable_error_fails_immediately():
    """bad request 系は retry しても直らないため 1 回で即失敗する。"""
    transport = StubTransport(
        fail_first_n=99, error_factory=lambda: LLMBadRequestError("bad")
    )
    client = LLMClient(
        transport, RetryConfig(max_attempts=3, timeout_seconds=1, **FAST)
    )
    with pytest.raises(LLMBadRequestError):
        await client.chat([{"role": "user", "content": "x"}])
    assert transport.calls == 1


async def test_timeout_is_enforced_and_retried():
    """遅延 0.5s を注入し timeout 0.05s → 全試行 timeout で LLMTimeoutError。"""
    transport = StubTransport(delay_seconds=0.5)
    client = LLMClient(
        transport, RetryConfig(max_attempts=2, timeout_seconds=0.05, **FAST)
    )
    with pytest.raises(LLMTimeoutError):
        await client.chat([{"role": "user", "content": "x"}])
    assert transport.calls == 2


def test_backoff_grows_exponentially_with_jitter():
    """backoff は base * 2^(n-1) に 0.5〜1.5 倍の jitter が乗り、上限で頭打ち。"""
    config = RetryConfig(
        max_attempts=5, base_delay_seconds=0.5, max_delay_seconds=8.0
    )
    rng = random.Random(42)
    for attempt in range(1, 6):
        expected_exp = min(8.0, 0.5 * (2 ** (attempt - 1)))
        delay = config.backoff_delay(attempt, rng)
        assert expected_exp * 0.5 <= delay <= expected_exp * 1.5


async def test_embedding_is_deterministic_and_1536_dims():
    client = LLMClient(StubTransport(), RetryConfig(timeout_seconds=1, **FAST))
    v1 = await client.embed("same input")
    v2 = await client.embed("same input")
    v3 = await client.embed("other input")
    assert len(v1) == EMBEDDING_DIMENSIONS == 1536
    assert v1 == v2  # 同一入力 → 同一ベクトル
    assert v1 != v3  # 異なる入力 → 異なるベクトル


def test_retry_config_rejects_invalid_values():
    with pytest.raises(ValueError):
        RetryConfig(max_attempts=0)
    with pytest.raises(ValueError):
        RetryConfig(timeout_seconds=0)


def test_create_llm_client_rejects_unknown_provider():
    with pytest.raises(ValueError):
        create_llm_client("azure-openai", RetryConfig())
