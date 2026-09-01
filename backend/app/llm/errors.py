"""LLM 呼び出しのエラー分類（ADR-0009 / ADR-0028）。

client.py（transport・retry）と streaming.py（raw stream の変換）の両方が
参照するため、循環 import を避けて独立モジュールに置く。既存の公開名は
client.py が再 export しており、`from app.llm.client import LLMError` は
従来どおり使える。

wire contract の `error` event の class 識別子（表記の正本は共有 fixture =
`docs/contracts/chat-sse/`。ADR-0028 決定 2）との対応:

- LLMTimeoutError → `timeout`
- LLMRateLimitError → `rate_limit`
- LLMServerError → `server_error`
- LLMBadRequestError → `bad_request`
- LLMContentFilterError → `content_filter`
"""


class LLMError(Exception):
    """LLM 呼び出しの失敗。retryable かどうかをクラスで表す。"""

    retryable: bool = False


class LLMTimeoutError(LLMError):
    """呼び出しが timeout した。一時的な混雑の可能性があるため retry する。"""

    retryable = True


class LLMRateLimitError(LLMError):
    """レート制限（HTTP 429 相当）。retry する。"""

    retryable = True


class LLMServerError(LLMError):
    """提供元側の一時障害（HTTP 5xx 相当）。retry する。"""

    retryable = True


class LLMBadRequestError(LLMError):
    """リクエスト自体が不正（HTTP 4xx 相当）。retry しても直らないため即失敗。"""

    retryable = False


class LLMContentFilterError(LLMError):
    """content filter 起因の終端（ADR-0028 決定 5 / 6）。

    `finish_reason: "content_filter"`、または chunk 内の error field
    （複数形 `content_filter_results` / 単数形 `content_filter_result` の
    `error`）の検出。filter の判定が得られなかった応答を完了扱いにしない
    fail-closed であり、同じリクエストの retry で直る性質ではないため
    retry しない。wire では `error`（class: `content_filter`）で終端し
    `done` を送らない（撤回契約の producer 義務）。
    """

    retryable = False
