"""取り込みスクリプトのエントリポイント。

実行（backend/ で）: uv run python -m app.ingest

DATABASE_URL の DB へ、NASA 出典のシードデータ（nasa_seed.py）を冪等に投入する。
再実行しても行数は増えない。embedding は投入しない（NULL のまま。ADR-0004）。
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
    with psycopg.connect(database_url, connect_timeout=5) as conn:
        summary = run_ingest(conn)
    print("ingest 完了（冪等。再実行しても行数は増えません）")
    for table in ("sources", "objects", "object_properties", "documents"):
        print(
            f"  {table}: +{summary.inserted[table]} inserted"
            f" (total {summary.total[table]})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
