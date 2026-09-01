"""Azure OpenAI raw stream の incremental parse と wire contract への変換。

ADR-0028 の producer 側の中核 2 段を持つ（Issue #192）。

1. `SSEStreamParser`: byte 列から SSE の data payload を復元する incremental
   parser（決定 8 の upstream 方向）。recv 境界が UTF-8 マルチバイト文字の途中・
   `data:` プレフィクスの途中・event 区切りの空行の直前後のどこで分断されても、
   無分割時と同一の payload 列を復元する。行分割を byte のまま LF で行い、
   完成した行だけを UTF-8 decode することでマルチバイト分断を吸収する
2. `raw_stream_to_deltas`: raw chunk（JSON payload）列を決定 5 の表のとおり
   content delta 列へ変換する。error 終端は例外
   （`LLMContentFilterError` / `LLMServerError`）で表し、呼び出し側
   （`LLMClient.chat_stream` → `app.main`）が wire の `error` event へ写す

CI から実 LLM は呼ばない（ADR-0004）。この変換の検証は
`docs/contracts/chat-sse/` の共有 fixture（決定 9）をスタブ入力として行う。
"""

import json
from collections.abc import AsyncIterator

from app.llm.errors import LLMContentFilterError, LLMServerError

# raw stream の終端センチネル（Azure OpenAI / OpenAI 互換の SSE 仕様）
RAW_DONE_SENTINEL = "[DONE]"

# 決定 5 の表: error を運ぶ field はこの 2 つを明示列挙して検査する
# （複数形 `content_filter_results` と単数形 `content_filter_result`。
#   実測（run3-long）では単数形のみが届いた = 2026-09-01 追記改訂）。
# これ以外の未知 field（obfuscation / usage: null / latency_checkpoint /
# routing 等）は無視し、error 終端の条件にしない
CONTENT_FILTER_ERROR_FIELDS = (
    "content_filter_results",
    "content_filter_result",
)


class SSEStreamParser:
    """SSE byte stream から data payload を復元する incremental parser。

    - `feed(data)` に任意長の byte 断片を渡すと、その時点で完成した event の
      data payload（str）のリストを返す
    - 行分割は byte のまま LF（0x0A）で行う。LF は UTF-8 の継続 byte に
      現れないため、マルチバイト文字の途中で分断された断片は次の feed まで
      buffer に残り、完成した行の decode で正しく復元される
    - WHATWG "the event stream format" に従い、行末の CR は落とし、
      `data:` 以外の field（`event:` / `id:` / comment 行等）は読み飛ばす
      （実測では `data:` 行のみが届いた。observations.md §5-4）。
      複数の `data:` 行は LF で連結する
    - stream が event 区切りの空行なしに終わった場合、未完成の event は
      仕様どおり破棄する（終端判定は上位の `raw_stream_to_deltas` が行う）
    """

    def __init__(self) -> None:
        self._buffer = b""
        self._data_lines: list[str] = []
        self._has_data = False

    def feed(self, data: bytes) -> list[str]:
        """byte 断片を追加し、完成した data payload のリストを返す。"""
        self._buffer += data
        payloads: list[str] = []
        while True:
            newline_at = self._buffer.find(b"\n")
            if newline_at < 0:
                break
            raw_line = self._buffer[:newline_at]
            self._buffer = self._buffer[newline_at + 1 :]
            payload = self._process_line(raw_line)
            if payload is not None:
                payloads.append(payload)
        return payloads

    def _process_line(self, raw_line: bytes) -> str | None:
        if raw_line.endswith(b"\r"):
            raw_line = raw_line[:-1]
        line = raw_line.decode("utf-8")
        if line == "":
            # event 区切りの空行 → data 行があれば event を確定する
            if not self._has_data:
                return None
            payload = "\n".join(self._data_lines)
            self._data_lines = []
            self._has_data = False
            return payload
        if line.startswith("data:"):
            value = line[len("data:") :]
            if value.startswith(" "):
                value = value[1:]
            self._data_lines.append(value)
            self._has_data = True
        # `data:` 以外の field・comment 行は読み飛ばす（前方互換）
        return None


def _chunk_error_termination(choice: dict) -> bool:
    """決定 5 の表の error field 検査（単数形・複数形の明示列挙）。

    どちらかの field が `error` を持てば True。`finish_reason` の値・
    `stop` の前後に関わらず、検出時は `error`（class: `content_filter`）で
    終端し `done` を送らない（決定 6 の fail-closed・撤回契約）。
    """
    for field_name in CONTENT_FILTER_ERROR_FIELDS:
        value = choice.get(field_name)
        if isinstance(value, dict) and "error" in value:
            return True
    return False


async def raw_stream_to_deltas(
    payloads: AsyncIterator[str],
) -> AsyncIterator[str]:
    """raw chunk 列を決定 5 の表のとおり content delta 列へ変換する。

    - 非空 content の delta だけを yield する（決定 4: 空 `message` を作らない）
    - 正常終了（return）は「`finish_reason: "stop"` 観測済みで raw `[DONE]` に
      到達」の場合のみ。`done` の送出は raw `[DONE]` まで遅延する（決定 5）
    - error 終端は例外で表す:
      - `LLMContentFilterError`: error field の検出（決定 6）または
        `finish_reason: "content_filter"`
      - `LLMServerError`: `[DONE]` なしの stream 終了・`stop` 未観測の
        `[DONE]`・未知の chunk 形状（fail-closed）
    """
    try:
        async for delta in _convert(payloads):
            yield delta
    finally:
        # error 終端（例外）・呼び出し側の close（client 切断）を含む
        # すべての終了経路で raw stream 側の generator を閉じ、
        # transport の finally（provider stream の打ち切り）まで連鎖させる
        aclose = getattr(payloads, "aclose", None)
        if aclose is not None:
            await aclose()


async def _convert(payloads: AsyncIterator[str]) -> AsyncIterator[str]:
    """raw_stream_to_deltas の変換本体（close 連鎖は外側が担う）。"""
    stop_seen = False
    async for payload in payloads:
        if payload == RAW_DONE_SENTINEL:
            if stop_seen:
                return
            raise LLMServerError(
                "raw [DONE] が finish_reason: stop の観測前に到達しました"
            )
        try:
            chunk = json.loads(payload)
        except ValueError as exc:
            raise LLMServerError("raw chunk が JSON ではありません") from exc
        if not isinstance(chunk, dict):
            raise LLMServerError("raw chunk が JSON object ではありません")

        choices = chunk.get("choices")
        if not isinstance(choices, list):
            # 未知の chunk 形状 → fail-closed（決定 5 の表の最終行）
            raise LLMServerError("raw chunk に choices がありません")
        if not choices:
            # `choices` が空のメタ chunk（prompt annotation・usage 等）
            # → 出力しない（検査対象の error field は choice 内のため検査なし）
            continue
        choice = choices[0]
        if not isinstance(choice, dict):
            raise LLMServerError("raw chunk の choice が object ではありません")

        # error field の検査を最優先で行う（`stop` の前後に関わらず検出する）
        if _chunk_error_termination(choice):
            raise LLMContentFilterError(
                "content filter の error field を検出しました"
            )

        finish_reason = choice.get("finish_reason")
        if finish_reason == "content_filter":
            raise LLMContentFilterError(
                "finish_reason: content_filter で終端しました"
            )
        if finish_reason == "stop":
            # `done` の送出候補として記録し、`[DONE]` まで検査を続ける
            stop_seen = True
            continue
        if finish_reason is not None:
            # 表に列挙のない finish_reason（例: length）は未知の chunk 形状
            # として fail-closed（正当な形状が観測されたら表を追記改訂する）
            raise LLMServerError(
                "未知の finish_reason で終端しようとしました"
            )

        delta = choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if content is None or content == "":
                # role delta（実測は role + content:"" + refusal:null の複合形）・
                # 空/null content の delta → 出力しない
                continue
            if isinstance(content, str):
                yield content
                continue
            raise LLMServerError("delta.content が文字列ではありません")
        if delta is None and isinstance(
            choice.get("content_filter_results"), dict
        ):
            # content を持たず content_filter_results（error なし）だけを持つ
            # annotation chunk → 出力しない（検査は上で実施済み）
            continue
        raise LLMServerError("未知の chunk 形状です")

    # 終端 event なしの stream 終了（raw `[DONE]` 未到達）は契約違反
    raise LLMServerError("raw stream が [DONE] なしで終了しました")
