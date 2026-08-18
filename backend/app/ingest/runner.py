"""NASA シードデータの冪等な取り込み（ADR-0003 / ADR-0006）。

冪等性の設計:

- sources: UNIQUE (source_url, retrieved_at) を活かし ON CONFLICT DO NOTHING。
  retrieved_at は「実際に取得した時刻」の固定値なので、再実行しても同じ行に
  解決される（再取得したときだけ新しい行が増える。ADR-0003 の履歴方針どおり）
- objects: UNIQUE (name) で ON CONFLICT DO NOTHING
- object_properties: UNIQUE (object_id, property_name, source_id) で
  ON CONFLICT DO NOTHING
- documents: UNIQUE 制約がないため、(source_id, content) の完全一致で
  存在チェックしてから挿入する（チャンクは静的データなので完全一致で足りる。
  この用途のために新しい制約・マイグレーションは追加しない）

embedding は投入しない（NULL のまま。LLM プロバイダ未確定。ADR-0004）。
"""

import logging
from dataclasses import dataclass, field

import psycopg

from app.ingest import nasa_seed

logger = logging.getLogger("app.ingest")


@dataclass
class IngestSummary:
    """テーブルごとの挿入件数と、実行後の総行数。"""

    inserted: dict[str, int] = field(default_factory=dict)
    total: dict[str, int] = field(default_factory=dict)


def run_ingest(conn: psycopg.Connection) -> IngestSummary:
    """シードデータを冪等に投入する。再実行しても行数は増えない。"""
    summary = IngestSummary()
    with conn.cursor() as cur:
        source_ids = _upsert_sources(cur, summary)
        object_ids = _upsert_objects(cur, summary)
        _upsert_properties(cur, summary, object_ids, source_ids)
        _upsert_documents(cur, summary, source_ids)
        for table in ("sources", "objects", "object_properties", "documents"):
            cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 (固定名)
            summary.total[table] = cur.fetchone()[0]
    conn.commit()
    return summary


def _upsert_sources(cur, summary: IngestSummary) -> dict[str, int]:
    inserted = 0
    ids: dict[str, int] = {}
    for key, src in nasa_seed.SOURCES.items():
        cur.execute(
            """
            INSERT INTO sources
                (source_url, source_title, reuse_basis, retrieved_at, note)
            VALUES (%(source_url)s, %(source_title)s, %(reuse_basis)s,
                    %(retrieved_at)s, %(note)s)
            ON CONFLICT (source_url, retrieved_at) DO NOTHING
            RETURNING id
            """,
            src,
        )
        row = cur.fetchone()
        if row is not None:
            inserted += 1
            ids[key] = row[0]
        else:
            cur.execute(
                "SELECT id FROM sources"
                " WHERE source_url = %s AND retrieved_at = %s",
                (src["source_url"], src["retrieved_at"]),
            )
            ids[key] = cur.fetchone()[0]
    summary.inserted["sources"] = inserted
    return ids


def _upsert_objects(cur, summary: IngestSummary) -> dict[str, int]:
    inserted = 0
    ids: dict[str, int] = {}
    for obj in nasa_seed.OBJECTS:
        cur.execute(
            """
            INSERT INTO objects (name, kind, note)
            VALUES (%(name)s, %(kind)s, %(note)s)
            ON CONFLICT (name) DO NOTHING
            RETURNING id
            """,
            obj,
        )
        row = cur.fetchone()
        if row is not None:
            inserted += 1
            ids[obj["name"]] = row[0]
        else:
            cur.execute(
                "SELECT id FROM objects WHERE name = %s", (obj["name"],)
            )
            ids[obj["name"]] = cur.fetchone()[0]
    summary.inserted["objects"] = inserted
    return ids


def _upsert_properties(
    cur,
    summary: IngestSummary,
    object_ids: dict[str, int],
    source_ids: dict[str, int],
) -> None:
    inserted = 0
    for prop in nasa_seed.PROPERTIES:
        cur.execute(
            """
            INSERT INTO object_properties
                (object_id, property_name, value_numeric, value_text,
                 unit, source_id, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (object_id, property_name, source_id) DO NOTHING
            RETURNING id
            """,
            (
                object_ids[prop["object"]],
                prop["property_name"],
                prop.get("value_numeric"),
                prop.get("value_text"),
                prop.get("unit"),
                source_ids[prop["source"]],
                prop["note"],
            ),
        )
        if cur.fetchone() is not None:
            inserted += 1
    summary.inserted["object_properties"] = inserted


def _upsert_documents(
    cur, summary: IngestSummary, source_ids: dict[str, int]
) -> None:
    inserted = 0
    for doc in nasa_seed.DOCUMENTS:
        cur.execute(
            """
            INSERT INTO documents (content, source_id)
            SELECT %(content)s, %(source_id)s
            WHERE NOT EXISTS (
                SELECT 1 FROM documents
                WHERE content = %(content)s AND source_id = %(source_id)s
            )
            RETURNING id
            """,
            {
                "content": doc["content"],
                "source_id": source_ids[doc["source"]],
            },
        )
        if cur.fetchone() is not None:
            inserted += 1
    summary.inserted["documents"] = inserted
