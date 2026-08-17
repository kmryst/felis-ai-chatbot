"""LLM クライアント境界（ADR-0004）。

- 提供元（Azure OpenAI / OpenAI API）は未確定のため、既定はスタブ。
  本実装への差し替えはこのモジュール内の transport 追加だけで行う
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
import logging
import random
from dataclasses import dataclass, field

logger = logging.getLogger("app.llm")

EMBEDDING_DIMENSIONS = 1536


# --- エラー分類 ---------------------------------------------------------------


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


# --- retry 設定 ---------------------------------------------------------------


@dataclass(frozen=True)
class RetryConfig:
    """timeout / retry / backoff の設定。値は環境変数から渡す（config.py）。"""

    max_attempts: int = 3
    timeout_seconds: float = 10.0  # 1 試行あたりの timeout
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0

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


# --- クライアント本体 ---------------------------------------------------------


class LLMClient:
    """timeout / retry / backoff を一手に引き受けるクライアント。

    transport は `async chat(messages) -> str` / `async embed(text) -> list[float]`
    を持つオブジェクト。現状はスタブのみ。本実装（Azure OpenAI / OpenAI API）は
    提供元確定後にこのモジュールへ追加する。
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

        logger.error(
            "llm call failed, retries exhausted",
            extra={
                "llm_operation": operation,
                "error_type": type(last_error).__name__,
                "attempts": self._retry.max_attempts,
            },
        )
        raise last_error


def create_llm_client(provider: str, retry: RetryConfig) -> LLMClient:
    """設定から LLMClient を組み立てる。

    現時点でサポートするのは 'stub' のみ。提供元確定後に
    'azure-openai' / 'openai' をここへ追加する。
    """
    if provider == "stub":
        return LLMClient(StubTransport(), retry=retry)
    raise ValueError(
        f"未対応の LLM_PROVIDER です: {provider}（現在サポート: stub）"
    )
