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
import logging
import random
from dataclasses import dataclass, field

import httpx

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
