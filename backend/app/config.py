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


def _require(name: str, missing: list[str]) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        missing.append(name)
        return ""
    return value


@dataclass(frozen=True)
class Settings:
    app_name: str
    log_level: str
    # DB 接続文字列。secret を含むため repr=False（ログ・エラー画面への漏出防止）
    database_url: str = field(repr=False)
    db_connect_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        missing: list[str] = []
        settings = cls(
            app_name=os.environ.get("APP_NAME", "felis-ai-chatbot-backend"),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            database_url=_require("DATABASE_URL", missing),
            db_connect_timeout_seconds=_int_env("DB_CONNECT_TIMEOUT_SECONDS", 2),
        )
        if missing:
            raise MissingEnvError(missing)
        return settings
