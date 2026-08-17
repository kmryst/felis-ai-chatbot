"""環境変数ベースの設定。

設定はすべて環境変数から読む（ハードコードしない）。
必須の環境変数が欠けている場合は起動時に即座に fail する
（最初のリクエストで落ちるより起動時に落ちるほうが検知が早い）。

secret（API キー・パスワード・接続文字列）は絶対にログへ出さないこと。
"""

import os
from dataclasses import dataclass


class MissingEnvError(RuntimeError):
    """必須環境変数の欠落。起動時に検出してプロセスを止める。"""

    def __init__(self, names: list[str]) -> None:
        super().__init__(
            "必須環境変数が未設定です: " + ", ".join(names)
        )
        self.names = names


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

    @classmethod
    def from_env(cls) -> "Settings":
        missing: list[str] = []
        # 現時点で必須の環境変数はない。DB 接続情報（PR 2 予定）など
        # 必須項目を足すときは `_require("DATABASE_URL", missing)` の形で追加する。
        settings = cls(
            app_name=os.environ.get("APP_NAME", "felis-ai-chatbot-backend"),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )
        if missing:
            raise MissingEnvError(missing)
        return settings
