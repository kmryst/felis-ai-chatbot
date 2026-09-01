"""wire contract（ADR-0028）の SSE event 組み立て。

- 各 event は `event:` 行 1 本 + `data:` 行 1 本、data は必ず JSON object
  （決定 2）。LLM 出力の改行は JSON 文字列内へ escape されるため SSE の
  行指向 framing を壊さない
- JSON の直列化は決定的（ensure_ascii=False・separators 固定）にする。
  共有 fixture（docs/contracts/chat-sse/）の canonical wire example と
  byte 単位で一致させ、consumer 側の byte 分断テスト（決定 8）が producer の
  実出力と同じ byte 列で行えるようにするため
- `error` event の data は error class のみ（詳細メッセージ・プロンプト断片・
  upstream 応答本文を含めない）。class 識別子の表記の正本は共有 fixture
"""

import json

from app.llm.errors import (
    LLMBadRequestError,
    LLMContentFilterError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)

# charset を明示する（SSE は UTF-8。決定 1）
SSE_MEDIA_TYPE = "text/event-stream; charset=utf-8"

# 中間 proxy・ブラウザにキャッシュ・バッファさせない（SSE の定石）
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def format_sse_event(event: str, data: dict) -> str:
    """wire contract の 1 event を SSE テキストへ直列化する。"""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def error_class_for(exc: LLMError) -> str:
    """LLMError の分類を wire の error class 識別子へ写す。

    識別子の表記の正本は共有 fixture（docs/contracts/chat-sse/README.md）。
    未知の LLMError は server_error に倒す（fail-closed 側の既定）。
    """
    if isinstance(exc, LLMContentFilterError):
        return "content_filter"
    if isinstance(exc, LLMTimeoutError):
        return "timeout"
    if isinstance(exc, LLMRateLimitError):
        return "rate_limit"
    if isinstance(exc, LLMBadRequestError):
        return "bad_request"
    return "server_error"
