"""DB 到達性チェック。

readiness（/readyz）から呼ばれる。接続には必ず明示的な timeout を設定する
（timeout なしの外部通信を作らない）。

接続文字列は secret を含むため、ログや例外メッセージに DSN を出さないこと。
本格的な接続プール・ORM は Day 1 PR 3（スキーマ + マイグレーション）で導入する。
"""

import logging

import psycopg

logger = logging.getLogger("app.db")


async def check_database_ready(database_url: str, connect_timeout_seconds: int) -> bool:
    """DB に接続して SELECT 1 が通るかを返す。

    失敗時は False を返し、原因は例外クラス名のみログに残す
    （メッセージに DSN が含まれ得るため本文は出さない）。
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            database_url,
            connect_timeout=connect_timeout_seconds,
        ) as conn:
            await conn.execute("SELECT 1")
        return True
    except psycopg.Error as exc:
        logger.warning(
            "database readiness check failed",
            extra={"error_type": type(exc).__name__},
        )
        return False
