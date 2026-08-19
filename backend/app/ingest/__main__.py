"""取り込みスクリプトのエントリポイント。

実行（backend/ で）:

- `uv run python -m app.ingest`          … シード投入（diff-sync）のみ
- `uv run python -m app.ingest --embed`  … シード投入後に embedding backfill

DATABASE_URL の DB へ、気象庁出典のシードデータ（jma_seed.py）を冪等に投入し、
シードに現れない行（旧題材のデータ等）を削除して同期する。再実行しても行数は
増えない。

`--embed` は `embedding IS NULL` の行だけを対象に embedding を生成する（冪等。
embeddings.py）。生成には LLM_PROVIDER の設定に従った LLM クライアントを使う
（実 LLM を使うには LLM_PROVIDER=azure-openai を明示する。ADR-0009）。
"""

import asyncio
import os
import sys

import psycopg

from app.ingest.runner import run_ingest


def main(argv: list[str]) -> int:
    embed = "--embed" in argv
    unknown = [a for a in argv if a != "--embed"]
    if unknown:
        print(f"未対応の引数です: {unknown}（対応: --embed）", file=sys.stderr)
        return 2
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
    if embed:
        generated = _run_backfill(database_url)
        print(
            f"embedding backfill 完了: {generated} 行生成"
            "（embedding IS NULL の行のみ対象。冪等）"
        )
    return 0


def _run_backfill(database_url: str) -> int:
    """LLM クライアントを組み立てて embedding backfill を実行する。

    クライアントの組み立ては app.main と同じく設定（環境変数）に従う。
    LLM_PROVIDER=stub のままでも動く（決定的なダミーベクトル）が、
    実運用の embedding には LLM_PROVIDER=azure-openai を明示すること。
    """
    from app.config import Settings
    from app.ingest.embeddings import backfill_embeddings
    from app.llm.client import AzureOpenAIConfig, RetryConfig, create_llm_client

    settings = Settings.from_env()
    llm = create_llm_client(
        settings.llm_provider,
        RetryConfig(
            max_attempts=settings.llm_max_attempts,
            timeout_seconds=settings.llm_timeout_seconds,
            base_delay_seconds=settings.llm_retry_base_delay_seconds,
            max_delay_seconds=settings.llm_retry_max_delay_seconds,
        ),
        azure=(
            AzureOpenAIConfig(
                endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                chat_deployment=settings.azure_openai_chat_deployment,
                embedding_deployment=settings.azure_openai_embedding_deployment,
            )
            if settings.llm_provider == "azure-openai"
            else None
        ),
    )
    return asyncio.run(backfill_embeddings(database_url, llm))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
