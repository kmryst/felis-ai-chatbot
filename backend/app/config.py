"""環境変数ベースの設定。

設定はすべて環境変数から読む（ハードコードしない）。
必須の環境変数が欠けている場合は起動時に即座に fail する
（最初のリクエストで落ちるより起動時に落ちるほうが検知が早い）。

secret（API キー・パスワード・接続文字列）は絶対にログへ出さないこと。
"""

import os
from dataclasses import dataclass, field


class MissingEnvError(RuntimeError):
    """必須環境変数の欠落。起動時に検出してプロセスを止める。"""

    def __init__(self, names: list[str]) -> None:
        super().__init__(
            "必須環境変数が未設定です: " + ", ".join(names)
        )
        self.names = names


class InvalidEnvError(RuntimeError):
    """環境変数の値が不正。どの変数が原因かを明示して起動時に fail する。"""

    def __init__(self, name: str, value: str, reason: str) -> None:
        # 値そのものは secret の可能性があるためメッセージに含めない
        super().__init__(f"環境変数 {name} の値が不正です（{reason}）")
        self.name = name


def _int_env(name: str, default: int) -> int:
    """整数の環境変数を読む。数値でない場合は変数名を明示して即 fail する。

    黙って既定値へフォールバックしない（設定ミスが運用まで潜伏するため）。
    """
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise InvalidEnvError(name, raw, "整数を指定してください") from exc


def _float_env(name: str, default: float) -> float:
    """小数の環境変数を読む。数値でない場合は変数名を明示して即 fail する。"""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise InvalidEnvError(name, raw, "数値を指定してください") from exc


def _require(name: str, missing: list[str]) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        missing.append(name)
        return ""
    return value


def _require_if(condition: bool, name: str, missing: list[str]) -> str:
    """condition が真のときだけ必須として読む。偽なら空文字を返す。

    LLM_PROVIDER=stub のとき Azure 用変数を要求しないために使う
    （スタブのままローカル起動・CI が通ることを壊さない。ADR-0004）。
    """
    if not condition:
        return os.environ.get(name) or ""
    return _require(name, missing)


@dataclass(frozen=True)
class Settings:
    app_name: str
    log_level: str
    # DB 接続文字列。secret を含むため repr=False（ログ・エラー画面への漏出防止）
    database_url: str = field(repr=False)
    db_connect_timeout_seconds: int
    # LLM（既定はスタブ。提供元確定後に 'azure-openai' / 'openai' を追加）
    llm_provider: str
    llm_timeout_seconds: float
    llm_max_attempts: int
    llm_retry_base_delay_seconds: float
    llm_retry_max_delay_seconds: float
    # Azure OpenAI（LLM_PROVIDER=azure-openai のときのみ必須。ADR-0009）
    azure_openai_endpoint: str
    # API キーは secret のため repr=False（ログ・エラー画面への漏出防止）
    azure_openai_api_key: str = field(repr=False)
    azure_openai_api_version: str
    azure_openai_chat_deployment: str
    azure_openai_embedding_deployment: str
    # RAG 検索（ADR-0010）。閾値の既定値は実測スコア分布にもとづく
    rag_top_k: int
    rag_similarity_threshold: float
    # CORS で許可する origin（カンマ区切り）。既定はローカルの frontend のみ
    cors_allowed_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        missing: list[str] = []
        llm_provider = os.environ.get("LLM_PROVIDER", "stub")
        # Azure 用変数は azure-openai のときだけ必須（stub のままなら不要）
        azure_required = llm_provider == "azure-openai"
        settings = cls(
            app_name=os.environ.get("APP_NAME", "felis-ai-chatbot-backend"),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            database_url=_require("DATABASE_URL", missing),
            db_connect_timeout_seconds=_int_env("DB_CONNECT_TIMEOUT_SECONDS", 2),
            llm_provider=llm_provider,
            llm_timeout_seconds=_float_env("LLM_TIMEOUT_SECONDS", 10.0),
            llm_max_attempts=_int_env("LLM_MAX_ATTEMPTS", 3),
            llm_retry_base_delay_seconds=_float_env(
                "LLM_RETRY_BASE_DELAY_SECONDS", 0.5
            ),
            llm_retry_max_delay_seconds=_float_env(
                "LLM_RETRY_MAX_DELAY_SECONDS", 8.0
            ),
            azure_openai_endpoint=_require_if(
                azure_required, "AZURE_OPENAI_ENDPOINT", missing
            ),
            azure_openai_api_key=_require_if(
                azure_required, "AZURE_OPENAI_API_KEY", missing
            ),
            # api-version は疎通実測済みの GA 版を既定にする（ADR-0009）
            azure_openai_api_version=os.environ.get(
                "AZURE_OPENAI_API_VERSION", "2024-10-21"
            ),
            azure_openai_chat_deployment=os.environ.get(
                "AZURE_OPENAI_CHAT_DEPLOYMENT", "chat"
            ),
            azure_openai_embedding_deployment=os.environ.get(
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "embedding"
            ),
            rag_top_k=_int_env("RAG_TOP_K", 5),
            # 既定値 0.25 の根拠はドメイン内/外の質問群の実測スコア分布
            # （ドメイン内 top1 最小 0.357 / ドメイン外 top1 最大 0.149。
            #   ほぼ中間値をとり両側に約 0.1 のマージンを確保。ADR-0010）
            rag_similarity_threshold=_float_env(
                "RAG_SIMILARITY_THRESHOLD", 0.25
            ),
            cors_allowed_origins=tuple(
                origin.strip()
                for origin in os.environ.get(
                    "CORS_ALLOWED_ORIGINS", "http://localhost:3000"
                ).split(",")
                if origin.strip()
            ),
        )
        if missing:
            raise MissingEnvError(missing)
        return settings
