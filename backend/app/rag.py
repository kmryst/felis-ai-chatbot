"""RAG 検索（pgvector cosine 類似度 + object_properties の数値記録参照）。

- documents はユーザー質問の embedding と cosine 類似度で検索する
  （`<=>` は cosine 距離。similarity = 1 - distance）。HNSW インデックス
  （vector_cosine_ops）を使う前提のため、WHERE 句で embedding を絞らない。
  embedding が NULL の行は距離が NULL になり ORDER BY ... ASC の末尾に
  回るので、コード側で除外する（インデックス利用を妨げない）
- object_properties は全件を決定的にレンダリングして返す。歴代最高気温の
  ような数値記録は documents 側チャンクに存在しないことを実測で確認済み
  （ADR-0010）。53 行・約 6KB と小さいため entity 抽出はせず全件を
  コンテキストへ載せる（5日制約下で実装量を増やさない）
- 出典（sources）は FK で JOIN 可能な状態を保つが、コンテキストには
  URL 等を含めない。回答ごとの出典表示は行わない方針のため（ADR-0008）
- 接続には必ず明示的な timeout を設定する（timeout なしの外部通信を作らない）
"""

import logging
from dataclasses import dataclass

import psycopg

logger = logging.getLogger("app.rag")


@dataclass(frozen=True)
class ScoredChunk:
    """類似度つきの検索結果チャンク。"""

    content: str
    similarity: float


def format_embedding(vector: list[float]) -> str:
    """embedding を pgvector のリテラル表現（'[1,2,...]'）へ変換する。"""
    return "[" + ",".join(repr(v) for v in vector) + "]"


async def search_similar_documents(
    database_url: str,
    query_embedding: list[float],
    top_k: int,
    connect_timeout_seconds: int,
) -> list[ScoredChunk]:
    """documents を cosine 類似度で検索し、上位 top_k 件を返す。

    embedding が NULL の行（backfill 前）は similarity が NULL になるため
    除外する。結果は類似度の降順。
    """
    literal = format_embedding(query_embedding)
    async with await psycopg.AsyncConnection.connect(
        database_url, connect_timeout=connect_timeout_seconds
    ) as conn:
        cur = await conn.execute(
            """
            SELECT content, 1 - (embedding <=> %(q)s::vector) AS similarity
            FROM documents
            ORDER BY embedding <=> %(q)s::vector
            LIMIT %(k)s
            """,
            {"q": literal, "k": top_k},
        )
        rows = await cur.fetchall()
    return [
        ScoredChunk(content=row[0], similarity=row[1])
        for row in rows
        if row[1] is not None
    ]


async def fetch_property_records(
    database_url: str, connect_timeout_seconds: int
) -> list[str]:
    """object_properties 全件を「数値記録」の行テキストとして返す。

    note には取り込み時の根拠原文（地点・年月日等の引用）が含まれるため、
    値と併せてそのまま載せる。source は JOIN 可能だがコンテキストへは
    含めない（ADR-0008: 回答ごとの出典表示は行わない）。
    """
    async with await psycopg.AsyncConnection.connect(
        database_url, connect_timeout=connect_timeout_seconds
    ) as conn:
        cur = await conn.execute(
            """
            SELECT o.name, p.property_name, p.value_numeric, p.value_text,
                   p.unit, p.note
            FROM object_properties p
            JOIN objects o ON o.id = p.object_id
            ORDER BY o.name, p.property_name
            """
        )
        rows = await cur.fetchall()
    lines: list[str] = []
    for name, prop, num, text, unit, note in rows:
        value = num if num is not None else text
        unit_part = f" {unit}" if unit else ""
        note_part = f"（根拠原文: {note}）" if note else ""
        lines.append(f"{name} / {prop}: {value}{unit_part}{note_part}")
    return lines
