"""documents.embedding の冪等な backfill。

- 対象は `embedding IS NULL` の行のみ。埋まっている行は再生成しない
  （再実行しても embedding API を無駄に呼ばない。冪等）
- ingest の diff-sync（runner.py）で content が変わった行は削除・再挿入され
  embedding が NULL に戻るため、ingest → backfill の順で実行すれば
  文面改訂も自然に再生成対象になる
- LLM クライアント境界（app.llm）経由で embedding を生成する（ADR-0004 /
  ADR-0009）。CI・テストからは stub のみ使い、実 LLM は呼ばない
"""

import logging

import psycopg

from app.llm.client import LLMClient
from app.rag import format_embedding

logger = logging.getLogger("app.ingest")


async def backfill_embeddings(
    database_url: str,
    llm_client: LLMClient,
    connect_timeout_seconds: int = 5,
) -> int:
    """embedding が NULL の documents 行だけ embedding を生成して埋める。

    生成した行数を返す（全行埋まっていれば 0。冪等）。
    1 行ずつ UPDATE し、最後にまとめて commit する（途中失敗時は
    未 commit 分が巻き戻り、次回実行で NULL の行だけ再対象になる）。
    """
    async with await psycopg.AsyncConnection.connect(
        database_url, connect_timeout=connect_timeout_seconds
    ) as conn:
        cur = await conn.execute(
            "SELECT id, content FROM documents WHERE embedding IS NULL ORDER BY id"
        )
        rows = await cur.fetchall()
        for doc_id, content in rows:
            vector = await llm_client.embed(content)
            await conn.execute(
                "UPDATE documents SET embedding = %s::vector WHERE id = %s",
                (format_embedding(vector), doc_id),
            )
        await conn.commit()
    if rows:
        logger.info(
            "embedding backfill done", extra={"generated": len(rows)}
        )
    return len(rows)
