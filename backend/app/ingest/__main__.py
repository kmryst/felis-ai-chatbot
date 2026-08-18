"""取り込みスクリプトのエントリポイント。

実行（backend/ で）: uv run python -m app.ingest

DATABASE_URL の DB へ、気象庁出典のシードデータ（jma_seed.py）を冪等に投入し、
シードに現れない行（旧題材のデータ等）を削除して同期する。再実行しても行数は
増えない。embedding は投入しない（NULL のまま。ADR-0004）。
"""

import os
import sys

import psycopg

from app.ingest.runner import run_ingest


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL が未設定です（.env を読み込んでください）", file=sys.stderr)
        return 1
    try:
        with psycopg.connect(database_url, connect_timeout=5) as conn:
            summary = run_ingest(conn)
    except psycopg.OperationalError as exc:
        # 例外メッセージには DSN（secret）が含まれ得るためクラス名のみ出す
        # （app/db.py と同じ方針）
        print(
            f"DB 接続に失敗しました（{type(exc).__name__}）。"
            "DATABASE_URL と DB の起動状態を確認してください",
            file=sys.stderr,
        )
        return 1
    print("ingest 完了（冪等。再実行しても行数は増えません）")
    for table in ("sources", "objects", "object_properties", "documents"):
        deleted = summary.deleted.get(table, 0)
        deleted_note = f" -{deleted} stale deleted" if deleted else ""
        print(
            f"  {table}: +{summary.inserted[table]} inserted{deleted_note}"
            f" (total {summary.total[table]})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
