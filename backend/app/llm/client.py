"""LLM クライアント境界（ADR-0004 / ADR-0009）。

- 提供元は Azure OpenAI に確定（ADR-0009）。既定はスタブのままとし、
  実 LLM は `LLM_PROVIDER=azure-openai` の明示指定でのみ使う
  （CI・テストから実 LLM を呼ばない決定は維持する。ADR-0004）。
  本実装の追加はこのモジュール内の transport 追加だけで行った
  （Azure / OpenAI 両対応の抽象化レイヤーは作らない。5日制約下では過剰設計）。
- すべての呼び出しに明示的な timeout を設定する（timeout なしの外部通信を作らない）。
- retry は上限回数つき exponential backoff + jitter。retry するのは
  retryable なエラー（timeout / rate limit / server error）だけで、
  リクエスト自体が不正なエラー（bad request）は即座に失敗させる。
- スタブは故障（遅延・例外・先頭 N 回失敗）を注入でき、上記の挙動を
  「意図的に失敗させて確認する」テストの土台になる。
- embedding は 1536 次元固定（text-embedding-3-small 相当。ADR-0003）。
"""

import asyncio
import json
import logging
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx

# エラー分類は errors.py が正本（streaming.py との循環 import 回避）。
# 既存の import 経路（from app.llm.client import LLMError 等）を維持するため
# ここで再 export する
from app.llm.errors import (
    LLMBadRequestError,
    LLMContentFilterError,
    LLMError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
)
from app.llm.streaming import RAW_DONE_SENTINEL, SSEStreamParser, raw_stream_to_deltas

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "AzureOpenAIConfig",
    "AzureOpenAITransport",
    "LLMBadRequestError",
    "LLMClient",
    "LLMContentFilterError",
    "LLMError",
    "LLMRateLimitError",
    "LLMServerError",
    "LLMTimeoutError",
    "RetryConfig",
    "StubTransport",
    "create_llm_client",
]

logger = logging.getLogger("app.llm")

EMBEDDING_DIMENSIONS = 1536


# --- retry 設定 ---------------------------------------------------------------


@dataclass(frozen=True)
class RetryConfig:
    """timeout / retry / backoff の設定。値は環境変数から渡す（config.py）。"""

    max_attempts: int = 3
    timeout_seconds: float = 10.0  # 1 試行あたりの timeout
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        # max_attempts < 1 だと1回も呼ばずに終わる設定になるため、組み立て時に弾く
        if self.max_attempts < 1:
            raise ValueError(
                f"max_attempts は 1 以上を指定してください: {self.max_attempts}"
            )
        if self.timeout_seconds <= 0:
            raise ValueError(
                f"timeout_seconds は正の値を指定してください: {self.timeout_seconds}"
            )

    def backoff_delay(self, attempt: int, rng: random.Random) -> float:
        """attempt（1 始まり）回目の失敗後に待つ秒数。

        指数的に増やし（base * 2^(attempt-1)、上限 max_delay）、
        0.5〜1.5 倍の jitter を乗せて同時リトライの突入を散らす。
        """
        exp = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** (attempt - 1)),
        )
        return exp * rng.uniform(0.5, 1.5)


# --- スタブ transport ---------------------------------------------------------


@dataclass
class StubTransport:
    """決定的な応答を返すスタブ。故障注入パラメータを持つ。

    - delay_seconds: 全呼び出しに遅延を注入する（timeout 挙動の検証用）
    - fail_first_n: 先頭 N 回の呼び出しを失敗させる（retry 挙動の検証用）
    - error_factory: 注入する例外を作る callable（既定は LLMServerError）
    """

    delay_seconds: float = 0.0
    fail_first_n: int = 0
    error_factory: object = None
    calls: int = field(default=0, init=False)

    async def _maybe_inject_fault(self) -> None:
        self.calls += 1
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        if self.calls <= self.fail_first_n:
            factory = self.error_factory or (
                lambda: LLMServerError("injected fault")
            )
            raise factory()

    async def chat(self, messages: list[dict[str, str]]) -> str:
        await self._maybe_inject_fault()
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        return f"[stub] これはスタブ応答です。受け取ったメッセージ: {last_user}"

    async def embed(self, text: str) -> list[float]:
        await self._maybe_inject_fault()
        # 同じ入力には常に同じベクトルを返す（決定的）。
        # random.Random(str) は seed を sha512 で正規化するため実行間で安定
        rng = random.Random(text)
        return [rng.uniform(-1.0, 1.0) for _ in range(EMBEDDING_DIMENSIONS)]

    async def chat_stream(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        """chat と同じ決定的応答を raw stream 形状（SSE data payload 列）で返す。

        Azure OpenAI の実測形状（docs/verification/azure-openai-stream/）を模した
        chunk を生成し、実 transport と同じ変換（streaming.raw_stream_to_deltas）を
        通す。stub provider も同一契約の SSE を生成する（ADR-0004 / Issue #192 の
        受け入れ条件）ための構造で、変換器が CI で常時実行される。
        """
        await self._maybe_inject_fault()
        reply = await StubTransport.chat(
            # 故障注入を二重に踏まないため、注入なしの複製で本文だけ作る
            StubTransport(),
            messages,
        )

        def _chunk(choice: dict) -> str:
            return json.dumps(
                {
                    "choices": [
                        {
                            "content_filter_results": {},
                            "index": 0,
                            "logprobs": None,
                            **choice,
                        }
                    ],
                    "id": "chatcmpl-stub",
                    "model": "stub",
                    "object": "chat.completion.chunk",
                },
                ensure_ascii=False,
            )

        # 実測の先頭 delta は role + content:"" + refusal:null の複合形
        yield _chunk(
            {
                "delta": {"content": "", "refusal": None, "role": "assistant"},
                "finish_reason": None,
            }
        )
        # 本文を複数 chunk に分割して流す（message 複数の系列を作る）
        size = max(1, len(reply) // 3)
        for start in range(0, len(reply), size):
            yield _chunk(
                {
                    "delta": {"content": reply[start : start + size]},
                    "finish_reason": None,
                }
            )
        yield _chunk({"delta": {}, "finish_reason": "stop"})
        yield RAW_DONE_SENTINEL


# --- Azure OpenAI transport（ADR-0009） ---------------------------------------


@dataclass(frozen=True)
class AzureOpenAIConfig:
    """Azure OpenAI transport の接続設定。値は環境変数から渡す（config.py）。"""

    endpoint: str
    # API キーは secret のため repr=False（ログ・エラー画面への漏出防止）
    api_key: str = field(repr=False)
    api_version: str
    chat_deployment: str
    embedding_deployment: str


class AzureOpenAITransport:
    """Azure OpenAI（chat / embedding）への HTTP transport。

    timeout / retry / backoff は LLMClient が一元管理するため、ここでは
    再実装しない。この transport の責務は、HTTP エラーを既存のエラー分類へ
    正しくマッピングすることに絞る。

    - HTTP 429 → LLMRateLimitError（retry する）
    - HTTP 5xx → LLMServerError（retry する）
    - その他の 4xx → LLMBadRequestError（retry しても直らないため即失敗）
    - 接続断など transport 層の例外 → LLMServerError（一時障害として retry）

    この分類を誤ると「直らないリクエストを上限回数まで投げ続ける」
    「一時障害を即諦める」という運用上の実害が出る（テストで検証する）。
    """

    def __init__(
        self,
        config: AzureOpenAIConfig,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        # httpx 既定の 5s timeout は使わない（timeout は LLMClient の
        # asyncio.wait_for が一元管理する。二重 timeout を作らない）
        self._http = http_client or httpx.AsyncClient(
            base_url=config.endpoint.rstrip("/"), timeout=None
        )

    async def chat(self, messages: list[dict[str, str]]) -> str:
        data = await self._post(
            f"/openai/deployments/{self._config.chat_deployment}"
            "/chat/completions",
            {"messages": messages},
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServerError("chat 応答の形式が不正です") from exc
        if not isinstance(content, str):
            # コンテンツフィルタ等で content が null のケース。
            # 同じリクエストを retry しても直らないため即失敗させる
            raise LLMBadRequestError("chat 応答に本文が含まれていません")
        return content

    async def embed(self, text: str) -> list[float]:
        data = await self._post(
            f"/openai/deployments/{self._config.embedding_deployment}"
            "/embeddings",
            {"input": text},
        )
        try:
            return data["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServerError("embedding 応答の形式が不正です") from exc

    async def chat_stream(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        """chat completions を stream=true で呼び、SSE data payload を逐次返す。

        - HTTP エラーの分類は _post と同一（429 → rate limit、5xx → server、
          その他 4xx → bad request、transport 例外 → server / timeout）
        - byte 断片からの payload 復元は SSEStreamParser（ADR-0028 決定 8 の
          upstream 方向。recv 境界の分断耐性）
        - 呼び出し側が generator を close した場合（client 切断・timeout）は
          finally で response を閉じ、provider stream を打ち切る（決定 2。
          課金と接続の垂れ流しを作らない）
        """
        request = self._http.build_request(
            "POST",
            f"/openai/deployments/{self._config.chat_deployment}"
            "/chat/completions",
            params={"api-version": self._config.api_version},
            json={"messages": messages, "stream": True},
            headers={"api-key": self._config.api_key},
        )
        try:
            response = await self._http.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("HTTP timeout: chat stream") from exc
        except httpx.HTTPError as exc:
            raise LLMServerError(
                f"HTTP transport error: {type(exc).__name__}"
            ) from exc
        try:
            status = response.status_code
            if status == 429:
                raise LLMRateLimitError("rate limited (HTTP 429)")
            if status >= 500:
                raise LLMServerError(f"server error (HTTP {status})")
            if status >= 400:
                # レスポンス本文はログへ流さない（_post と同じ方針）
                raise LLMBadRequestError(f"bad request (HTTP {status})")
            parser = SSEStreamParser()
            try:
                async for fragment in response.aiter_bytes():
                    for payload in parser.feed(fragment):
                        yield payload
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("HTTP timeout: chat stream") from exc
            except httpx.HTTPError as exc:
                # stream 途中の接続断等。retry 境界（決定 10）の判断は
                # LLMClient 側が行う
                raise LLMServerError(
                    f"HTTP transport error: {type(exc).__name__}"
                ) from exc
        finally:
            await response.aclose()

    async def _post(self, path: str, payload: dict) -> dict:
        """POST して JSON を返す。HTTP エラーは既存のエラー分類へ変換する。"""
        try:
            response = await self._http.post(
                path,
                params={"api-version": self._config.api_version},
                json=payload,
                headers={"api-key": self._config.api_key},
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"HTTP timeout: {path}") from exc
        except httpx.HTTPError as exc:
            # 接続断・DNS 失敗など。一時障害の可能性があるため retry させる。
            # 例外メッセージは URL（api-version 等）を含み得るため型名だけ出す
            raise LLMServerError(
                f"HTTP transport error: {type(exc).__name__}"
            ) from exc

        status = response.status_code
        if status == 429:
            raise LLMRateLimitError("rate limited (HTTP 429)")
        if status >= 500:
            raise LLMServerError(f"server error (HTTP {status})")
        if status >= 400:
            # レスポンス本文はログへ流さない（エラー詳細に入力の断片が
            # 含まれ得るため）。分類とステータスだけで運用上は切り分け可能
            raise LLMBadRequestError(f"bad request (HTTP {status})")
        try:
            return response.json()
        except ValueError as exc:
            raise LLMServerError("応答が JSON ではありません") from exc


# --- クライアント本体 ---------------------------------------------------------


class LLMClient:
    """timeout / retry / backoff を一手に引き受けるクライアント。

    transport は `async chat(messages) -> str` / `async embed(text) -> list[float]`
    を持つオブジェクト（StubTransport / AzureOpenAITransport）。
    """

    def __init__(
        self,
        transport,
        retry: RetryConfig | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._transport = transport
        self._retry = retry or RetryConfig()
        self._rng = rng or random.Random()

    async def chat(self, messages: list[dict[str, str]]) -> str:
        return await self._call_with_retry(
            "chat", lambda: self._transport.chat(messages)
        )

    async def chat_stream(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        """chat 応答を content delta（非空 str）列として stream で返す。

        - transport の raw stream を streaming.raw_stream_to_deltas（決定 5 の
          表）で変換した結果を中継する。正常 return は「有効な done」を意味し、
          失敗は LLMError（error event への変換は呼び出し側 = app.main）
        - retry 境界（ADR-0028 決定 10）: retry は**最初の content delta を
          受信する前**に限る。受信後の upstream 失敗は retry せず即座に送出する
          （部分出力の重複送出を作らない）
        - timeout_seconds（1 試行あたり）は「最初の content delta の受信まで」に
          適用する（接続確立局面 = retry 可能域と一致させる）。以後の delta 間隔
          への timeout は閾値の数値決定と一体のため本実装では設けない
          （SLO 側の決定手順で決める。ADR-0028 決定 10 / 11）
        - 呼び出し側が generator を close した場合（client 切断）は transport の
          stream まで連鎖して閉じる（決定 2）
        """
        last_error: LLMError | None = None
        for attempt in range(1, self._retry.max_attempts + 1):
            deltas = raw_stream_to_deltas(self._transport.chat_stream(messages))
            try:
                first = await asyncio.wait_for(
                    anext(deltas), timeout=self._retry.timeout_seconds
                )
            except StopAsyncIteration:
                # content 0 件の done。文法（message 1 回以上 → done。決定 2）を
                # 満たせないため fail-closed（server error 系として retry 対象）
                last_error = LLMServerError(
                    "stream に content delta が含まれていません"
                )
            except TimeoutError:
                await self._aclose_quietly(deltas)
                last_error = LLMTimeoutError(
                    "chat stream の最初の content delta が"
                    f" {self._retry.timeout_seconds}s で timeout"
                )
            except LLMError as exc:
                await self._aclose_quietly(deltas)
                if not exc.retryable:
                    logger.warning(
                        "llm stream failed (non-retryable)",
                        extra={
                            "llm_operation": "chat_stream",
                            "error_type": type(exc).__name__,
                        },
                    )
                    raise
                last_error = exc
            else:
                try:
                    # 最初の content delta を受信した。以後は retry しない
                    yield first
                    async for delta in deltas:
                        yield delta
                    return
                finally:
                    # client 切断（GeneratorExit）・下流の例外でも upstream を
                    # 確実に打ち切る（決定 2）
                    await self._aclose_quietly(deltas)

            if attempt == self._retry.max_attempts:
                break
            delay = self._retry.backoff_delay(attempt, self._rng)
            logger.warning(
                "llm stream failed, retrying",
                extra={
                    "llm_operation": "chat_stream",
                    "error_type": type(last_error).__name__,
                    "attempt": attempt,
                    "max_attempts": self._retry.max_attempts,
                    "backoff_seconds": round(delay, 3),
                },
            )
            await asyncio.sleep(delay)

        logger.error(
            "llm stream failed, retries exhausted",
            extra={
                "llm_operation": "chat_stream",
                "error_type": type(last_error).__name__,
                "attempts": self._retry.max_attempts,
            },
        )
        raise last_error

    @staticmethod
    async def _aclose_quietly(agen: AsyncIterator) -> None:
        """async generator を close する。close 時の二次例外は握りつぶさない。

        aclose は generator 内の finally（transport の response.aclose 等）を
        実行させるための呼び出しで、既に終了済みなら no-op。
        """
        aclose = getattr(agen, "aclose", None)
        if aclose is not None:
            await aclose()

    async def embed(self, text: str) -> list[float]:
        vector = await self._call_with_retry(
            "embed", lambda: self._transport.embed(text)
        )
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise LLMError(
                f"embedding 次元が不正です: {len(vector)}"
                f"（期待値 {EMBEDDING_DIMENSIONS}）"
            )
        return vector

    async def _call_with_retry(self, operation: str, fn):
        last_error: LLMError | None = None
        for attempt in range(1, self._retry.max_attempts + 1):
            try:
                return await asyncio.wait_for(
                    fn(), timeout=self._retry.timeout_seconds
                )
            except TimeoutError:
                last_error = LLMTimeoutError(
                    f"{operation} が {self._retry.timeout_seconds}s で timeout"
                )
            except LLMError as exc:
                if not exc.retryable:
                    logger.warning(
                        "llm call failed (non-retryable)",
                        extra={
                            "llm_operation": operation,
                            "error_type": type(exc).__name__,
                        },
                    )
                    raise
                last_error = exc

            if attempt == self._retry.max_attempts:
                break
            delay = self._retry.backoff_delay(attempt, self._rng)
            logger.warning(
                "llm call failed, retrying",
                extra={
                    "llm_operation": operation,
                    "error_type": type(last_error).__name__,
                    "attempt": attempt,
                    "max_attempts": self._retry.max_attempts,
                    "backoff_seconds": round(delay, 3),
                },
            )
            await asyncio.sleep(delay)

        if last_error is None:
            # RetryConfig が max_attempts >= 1 を保証するため通常到達しない防御
            raise LLMError(f"{operation} が一度も実行されませんでした")
        logger.error(
            "llm call failed, retries exhausted",
            extra={
                "llm_operation": operation,
                "error_type": type(last_error).__name__,
                "attempts": self._retry.max_attempts,
            },
        )
        raise last_error


def create_llm_client(
    provider: str,
    retry: RetryConfig,
    azure: AzureOpenAIConfig | None = None,
) -> LLMClient:
    """設定から LLMClient を組み立てる。

    サポートは 'stub'（既定。ADR-0004）と 'azure-openai'（ADR-0009）。
    """
    if provider == "stub":
        return LLMClient(StubTransport(), retry=retry)
    if provider == "azure-openai":
        if azure is None:
            raise ValueError(
                "LLM_PROVIDER=azure-openai には AzureOpenAIConfig が必要です"
            )
        return LLMClient(AzureOpenAITransport(azure), retry=retry)
    raise ValueError(
        f"未対応の LLM_PROVIDER です: {provider}"
        "（現在サポート: stub / azure-openai）"
    )
