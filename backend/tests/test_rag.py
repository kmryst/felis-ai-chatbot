"""RAG 検索と embedding backfill のテスト（ADR-0010）。

- 実 LLM・外部 API は呼ばない（ADR-0004）。embedding はスタブの決定的
  ベクトルを使う
- DB テスト（@pytest.mark.db）は TEST_DATABASE_URL を使う。未設定なら skip
"""

import pytest

from app.ingest.embeddings import backfill_embeddings
from app.ingest.runner import run_ingest
from app.llm.client import LLMClient, RetryConfig, StubTransport
from app.rag import format_embedding, search_similar_documents

def _stub_client() -> LLMClient:
    return LLMClient(
        StubTransport(), RetryConfig(max_attempts=1, timeout_seconds=5)
    )


@pytest.mark.db
async def test_backfill_fills_null_embeddings_and_is_idempotent(
    db_conn, test_db_url
):
    """1 回目で NULL 全行が埋まり、2 回目は 0 件生成（冪等）。"""
    run_ingest(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM documents WHERE embedding IS NULL")
        total_null = cur.fetchone()[0]
    assert total_null > 0, "前提: ingest 直後は embedding が NULL"

    first = await backfill_embeddings(test_db_url, _stub_client())
    assert first == total_null

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM documents WHERE embedding IS NULL")
        assert cur.fetchone()[0] == 0

    second = await backfill_embeddings(test_db_url, _stub_client())
    assert second == 0


@pytest.mark.db
async def test_search_returns_top_k_ordered_by_similarity(
    db_conn, test_db_url
):
    """検索結果が類似度の降順で top_k 件返る。"""
    run_ingest(db_conn)
    await backfill_embeddings(test_db_url, _stub_client())
    query = await _stub_client().embed("台風について")
    chunks = await search_similar_documents(
        test_db_url, query, top_k=5, connect_timeout_seconds=5
    )
    assert len(chunks) == 5
    similarities = [c.similarity for c in chunks]
    assert similarities == sorted(similarities, reverse=True)


@pytest.mark.db
async def test_search_excludes_rows_with_null_embedding(
    db_conn, test_db_url
):
    """embedding が NULL の行（backfill 前）は検索結果に含まれない。"""
    run_ingest(db_conn)  # backfill しない = 全行 NULL
    query = await _stub_client().embed("台風について")
    chunks = await search_similar_documents(
        test_db_url, query, top_k=5, connect_timeout_seconds=5
    )
    assert chunks == []


@pytest.mark.db
async def test_search_finds_exact_content_first(db_conn, test_db_url):
    """あるチャンクの内容そのもので検索すると、そのチャンクが最上位に来る。

    スタブ embedding は同一入力に同一ベクトルを返すため、cosine 類似度は
    1.0（自分自身）が最大になる。ベクトル検索の結線が正しいことの決定的検証。
    """
    run_ingest(db_conn)
    await backfill_embeddings(test_db_url, _stub_client())
    with db_conn.cursor() as cur:
        cur.execute("SELECT content FROM documents ORDER BY id LIMIT 1")
        target = cur.fetchone()[0]
    query = await _stub_client().embed(target)
    chunks = await search_similar_documents(
        test_db_url, query, top_k=3, connect_timeout_seconds=5
    )
    assert chunks[0].content == target
    assert chunks[0].similarity == pytest.approx(1.0, abs=1e-6)


def test_format_embedding_roundtrip():
    """pgvector リテラル表現の基本形（DB 不要）。"""
    assert format_embedding([1.0, -0.5]) == "[1.0,-0.5]"
