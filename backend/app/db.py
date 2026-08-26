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
    except Exception as exc:
        # readiness probe は落とさない。DB ドライバ以外の例外（OSError 等）も
        # ここで受けて 503 に変換する。asyncio.CancelledError は BaseException
        # 系のためここでは捕捉されない（キャンセルは妨げない）
        logger.warning(
            "database readiness check failed",
            extra={"error_type": type(exc).__name__},
        )
        return False


# 3 系列の鮮度クエリ（Issue #104。/readyz が返し、外形監視 #106 が系列別に判定する。
# 設計と閾値の根拠は docs/operations/credit-window-execution-plan.md §5-3）
_OBS_FRESHNESS_SQL = """
SELECT
  (extract(epoch FROM now() - (SELECT max(ts) FROM obs.heartbeat)))::bigint,
  (extract(epoch FROM now() - (SELECT max(ts) FROM obs.db_stats)))::bigint,
  (extract(epoch FROM now() - (SELECT max(ts) FROM obs.bloat_stats)))::bigint
"""


async def fetch_observation_freshness(
    database_url: str, connect_timeout_seconds: int
) -> dict[str, int | None] | None:
    """観測 3 系列（heartbeat / 統計 / pgstattuple）の最新レコード経過秒を返す。

    - 系列がまだ空なら該当キーは None（max() が NULL）
    - obs スキーマ未作成・接続失敗など取得自体ができない場合は None を返す
      （/readyz の可否には影響させない。readiness は DB 到達性の話であり、
      観測が止まっているかどうかの判定は外形監視 #106 の役割）
    - statement_timeout を接続時に明示する（Issue #114 の 3）。エラーは上の設計で
      吸収できるが、クエリの遅延はそのまま /readyz の遅延になり、外形監視の
      30 秒 timeout に達すると観測系の問題が可用性 SLI の欠測に化ける。
      上限は接続 timeout と同じ秒数（既定 2 秒。ロック待ちや高負荷時のフルスキャン
      遅延を probe の時間予算より十分内側で打ち切る）
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            database_url,
            connect_timeout=connect_timeout_seconds,
            options=f"-c statement_timeout={connect_timeout_seconds * 1000}",
        ) as conn:
            cur = await conn.execute(_OBS_FRESHNESS_SQL)
            row = await cur.fetchone()
        return {
            "heartbeat_age_seconds": row[0],
            "stats_age_seconds": row[1],
            "pgstattuple_age_seconds": row[2],
        }
    except Exception as exc:
        logger.warning(
            "observation freshness query failed",
            extra={"error_type": type(exc).__name__},
        )
        return None
