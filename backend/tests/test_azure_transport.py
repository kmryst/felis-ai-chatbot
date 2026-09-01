"""AzureOpenAITransport のエラーマッピング検証（ADR-0009）。

実 LLM・外部 API は一切呼ばない（ADR-0004）。httpx.MockTransport で
HTTP レイヤーをモックし、ステータスコード → LLMError 分類のマッピングが
意図どおりであることを検証する。

この分類は retry 挙動に直結する（429/5xx は retry、4xx は即失敗）。
分類を誤ると「直らないリクエストを上限回数まで投げる」「一時障害を
即諦める」という運用上の実害が出るため、ここが本テストの主眼。
"""

import json

import httpx
import pytest

from app.llm.client import (
    EMBEDDING_DIMENSIONS,
    AzureOpenAIConfig,
    AzureOpenAITransport,
    LLMBadRequestError,
    LLMClient,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
    RetryConfig,
    create_llm_client,
)

CONFIG = AzureOpenAIConfig(
    endpoint="https://example-resource.openai.azure.com/",
    api_key="test-key-not-real",
    api_version="2024-10-21",
    chat_deployment="chat",
    embedding_deployment="embedding",
)

FAST = RetryConfig(
    max_attempts=3,
    timeout_seconds=1,
    base_delay_seconds=0.01,
    max_delay_seconds=0.05,
)

MESSAGES = [{"role": "user", "content": "こんにちは"}]


def _transport_returning(handler) -> tuple[AzureOpenAITransport, list]:
    """MockTransport を仕込んだ AzureOpenAITransport と請求記録を返す。"""
    requests: list[httpx.Request] = []

    def record_and_handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    http_client = httpx.AsyncClient(
        base_url=CONFIG.endpoint.rstrip("/"),
        transport=httpx.MockTransport(record_and_handle),
    )
    return AzureOpenAITransport(CONFIG, http_client=http_client), requests


def _status_handler(status: int, body: dict | None = None):
    return lambda request: httpx.Response(status, json=body or {})


# --- 正常系: リクエストの形と応答の取り出し -----------------------------------


async def test_chat_success_parses_content_and_sends_expected_request():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "やあ"}}
                ]
            },
        )

    transport, requests = _transport_returning(handler)
    reply = await transport.chat(MESSAGES)
    assert reply == "やあ"

    request = requests[0]
    assert request.url.path == "/openai/deployments/chat/chat/completions"
    assert request.url.params["api-version"] == "2024-10-21"
    assert request.headers["api-key"] == "test-key-not-real"
    assert json.loads(request.content) == {"messages": MESSAGES}


async def test_embed_success_parses_vector():
    vector = [0.1] * EMBEDDING_DIMENSIONS

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/openai/deployments/embedding/embeddings"
        return httpx.Response(200, json={"data": [{"embedding": vector}]})

    transport, _ = _transport_returning(handler)
    result = await transport.embed("台風とは")
    assert result == vector


# --- エラーマッピング（本丸）: 429 / 5xx / その他 4xx ---------------------------


async def test_http_429_maps_to_rate_limit_error():
    """429 → LLMRateLimitError（retryable=True）。"""
    transport, _ = _transport_returning(_status_handler(429))
    with pytest.raises(LLMRateLimitError) as excinfo:
        await transport.chat(MESSAGES)
    assert excinfo.value.retryable is True


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_http_5xx_maps_to_server_error(status: int):
    """5xx → LLMServerError（retryable=True）。"""
    transport, _ = _transport_returning(_status_handler(status))
    with pytest.raises(LLMServerError) as excinfo:
        await transport.chat(MESSAGES)
    assert excinfo.value.retryable is True


@pytest.mark.parametrize("status", [400, 401, 404])
async def test_http_other_4xx_maps_to_bad_request_error(status: int):
    """429 以外の 4xx → LLMBadRequestError（retryable=False）。"""
    transport, _ = _transport_returning(_status_handler(status))
    with pytest.raises(LLMBadRequestError) as excinfo:
        await transport.chat(MESSAGES)
    assert excinfo.value.retryable is False


async def test_transport_layer_error_maps_to_server_error():
    """接続断など transport 層の例外 → LLMServerError（一時障害として retry）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport, _ = _transport_returning(handler)
    with pytest.raises(LLMServerError):
        await transport.chat(MESSAGES)


async def test_http_timeout_maps_to_timeout_error():
    """httpx 側の timeout → LLMTimeoutError（retryable=True）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timeout")

    transport, _ = _transport_returning(handler)
    with pytest.raises(LLMTimeoutError):
        await transport.chat(MESSAGES)


# --- マッピングが LLMClient の retry 挙動へ正しく効くこと -----------------------


async def test_rate_limit_is_retried_then_succeeds():
    """429 → 429 → 200 と返すと、LLMClient が retry して 3 回目で成功する。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(429, json={})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "回復"}}]}
        )

    transport, _ = _transport_returning(handler)
    client = LLMClient(transport, FAST)
    assert await client.chat(MESSAGES) == "回復"
    assert calls["n"] == 3


async def test_bad_request_is_not_retried():
    """400 は retry しても直らないため 1 回で即失敗する（無駄撃ち防止）。"""
    transport, requests = _transport_returning(_status_handler(400))
    client = LLMClient(transport, FAST)
    with pytest.raises(LLMBadRequestError):
        await client.chat(MESSAGES)
    assert len(requests) == 1


# --- 応答形式の防御 ------------------------------------------------------------


async def test_malformed_chat_response_raises_server_error():
    transport, _ = _transport_returning(
        _status_handler(200, {"unexpected": "shape"})
    )
    with pytest.raises(LLMServerError):
        await transport.chat(MESSAGES)


async def test_null_content_raises_bad_request_error():
    """コンテンツフィルタ等で content が null → retry せず即失敗。"""
    transport, _ = _transport_returning(
        _status_handler(200, {"choices": [{"message": {"content": None}}]})
    )
    with pytest.raises(LLMBadRequestError):
        await transport.chat(MESSAGES)


# --- create_llm_client の分岐 --------------------------------------------------


def test_create_llm_client_supports_azure_openai():
    client = create_llm_client("azure-openai", FAST, azure=CONFIG)
    assert isinstance(client, LLMClient)


def test_create_llm_client_azure_requires_config():
    with pytest.raises(ValueError):
        create_llm_client("azure-openai", FAST, azure=None)


# --- chat_stream（ADR-0028。stream=true の transport と byte 復元） -------------


RAW_STREAM_BODY = (
    b'data: {"choices":[{"content_filter_results":{},"delta":{"content":"",'
    b'"refusal":null,"role":"assistant"},"finish_reason":null,"index":0,'
    b'"logprobs":null}]}\n\n'
    b'data: {"choices":[{"content_filter_results":{},"delta":'
    b'{"content":"\xe3\x82\x84\xe3\x81\x82"},"finish_reason":null,"index":0,'
    b'"logprobs":null}]}\n\n'
    b'data: {"choices":[{"content_filter_results":{},"delta":{},'
    b'"finish_reason":"stop","index":0,"logprobs":null}]}\n\n'
    b"data: [DONE]\n\n"
)


async def test_chat_stream_yields_payloads_and_sends_stream_true():
    """chat_stream は stream: true を送り、SSE data payload を逐次返す。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            content=RAW_STREAM_BODY,
        )

    transport, requests = _transport_returning(handler)
    payloads = [p async for p in transport.chat_stream(MESSAGES)]
    assert len(payloads) == 4
    assert payloads[-1] == "[DONE]"

    request = requests[0]
    assert request.url.path == "/openai/deployments/chat/chat/completions"
    assert request.url.params["api-version"] == "2024-10-21"
    assert request.headers["api-key"] == "test-key-not-real"
    assert json.loads(request.content) == {
        "messages": MESSAGES,
        "stream": True,
    }


async def test_chat_stream_http_429_maps_to_rate_limit_error():
    transport, _ = _transport_returning(_status_handler(429))
    with pytest.raises(LLMRateLimitError):
        async for _ in transport.chat_stream(MESSAGES):
            pass


@pytest.mark.parametrize("status", [500, 503])
async def test_chat_stream_http_5xx_maps_to_server_error(status: int):
    transport, _ = _transport_returning(_status_handler(status))
    with pytest.raises(LLMServerError):
        async for _ in transport.chat_stream(MESSAGES):
            pass


@pytest.mark.parametrize("status", [400, 401, 404])
async def test_chat_stream_http_4xx_maps_to_bad_request_error(status: int):
    transport, _ = _transport_returning(_status_handler(status))
    with pytest.raises(LLMBadRequestError):
        async for _ in transport.chat_stream(MESSAGES):
            pass


async def test_chat_stream_transport_layer_error_maps_to_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport, _ = _transport_returning(handler)
    with pytest.raises(LLMServerError):
        async for _ in transport.chat_stream(MESSAGES):
            pass


async def test_chat_stream_timeout_maps_to_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timeout")

    transport, _ = _transport_returning(handler)
    with pytest.raises(LLMTimeoutError):
        async for _ in transport.chat_stream(MESSAGES):
            pass


async def test_chat_stream_via_llm_client_returns_deltas():
    """LLMClient.chat_stream 経由で raw stream が content delta 列になる。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            content=RAW_STREAM_BODY,
        )

    transport, _ = _transport_returning(handler)
    client = LLMClient(transport, FAST)
    deltas = [d async for d in client.chat_stream(MESSAGES)]
    assert deltas == ["やあ"]
