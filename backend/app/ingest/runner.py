"""気象庁シードデータの冪等な取り込みと差分同期（ADR-0003 / ADR-0007 / ADR-0008）。

冪等性の設計（挿入側）:

- sources: UNIQUE (source_url, retrieved_at) を活かし ON CONFLICT DO NOTHING。
  retrieved_at は「実際に取得した時刻」の固定値なので、再実行しても同じ行に
  解決される
- objects: UNIQUE (name) で ON CONFLICT DO NOTHING
- object_properties: UNIQUE (object_id, property_name, source_id) で
  ON CONFLICT DO NOTHING
- documents: UNIQUE 制約がないため、(source_id, content) の完全一致で
  存在チェックしてから挿入する（この用途のために新しい制約・マイグレーション
  は追加しない）

差分同期の設計（削除側）:

シードは 4 テーブルすべての「あるべき全量」を表すものとし、シードに現れない
行は削除して同期する。理由:

- 題材の乗り換え（NASA → 気象庁。ADR-0007）で、既存 DB に旧題材の
  objects / sources / documents が残り続ける問題があるため、挿入だけの実装では
  投入経路が旧データを置き換えられない
- シード文面の改訂（誤記修正など）を既存 DB に反映するため（Issue #37 で
  顕在化した経路。documents のみの同期は PR #38 で導入済みで、これを
  全テーブルへ一般化した）

削除は参照の依存関係の逆順（object_properties → documents → objects →
sources）で行う。sources の削除は「シードに現れず、かつどこからも参照されて
いない行」に限定し、FK（ON DELETE RESTRICT）と衝突しないようにする。

embedding は投入しない（NULL のまま。LLM プロバイダ未確定。ADR-0004）。
"""

import logging
from dataclasses import dataclass, field

import psycopg

from app.ingest import jma_seed

logger = logging.getLogger("app.ingest")


@dataclass
class IngestSummary:
    """テーブルごとの挿入件数・削除件数と、実行後の総行数。"""

    inserted: dict[str, int] = field(default_factory=dict)
    deleted: dict[str, int] = field(default_factory=dict)
    total: dict[str, int] = field(default_factory=dict)


def run_ingest(conn: psycopg.Connection) -> IngestSummary:
    """シードデータを冪等に投入し、シードに現れない行を削除して同期する。

    再実行しても行数は増えない。シード（= あるべき全量）と DB が一致する。
    """
    summary = IngestSummary()
    with conn.cursor() as cur:
        source_ids = _upsert_sources(cur, summary)
        object_ids = _upsert_objects(cur, summary)
        _upsert_properties(cur, summary, object_ids, source_ids)
        _upsert_documents(cur, summary, source_ids)
        # 削除は参照の依存関係の逆順で行う（module docstring 参照）
        _delete_stale_properties(cur, summary, object_ids, source_ids)
        _delete_stale_documents(cur, summary, source_ids)
        _delete_stale_objects(cur, summary)
        _delete_stale_sources(cur, summary)
        for table in ("sources", "objects", "object_properties", "documents"):
            cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 (固定名)
            summary.total[table] = cur.fetchone()[0]
    conn.commit()
    return summary


def _upsert_sources(cur, summary: IngestSummary) -> dict[str, int]:
    inserted = 0
    ids: dict[str, int] = {}
    for key, src in jma_seed.SOURCES.items():
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
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(
                    f"conflict したのに sources 行が見つかりません: {key}"
                )
            ids[key] = row[0]
    summary.inserted["sources"] = inserted
    return ids


def _upsert_objects(cur, summary: IngestSummary) -> dict[str, int]:
    inserted = 0
    ids: dict[str, int] = {}
    for obj in jma_seed.OBJECTS:
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
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(
                    f"conflict したのに objects 行が見つかりません: {obj['name']}"
                )
            ids[obj["name"]] = row[0]
    summary.inserted["objects"] = inserted
    return ids


def _upsert_properties(
    cur,
    summary: IngestSummary,
    object_ids: dict[str, int],
    source_ids: dict[str, int],
) -> None:
    inserted = 0
    for prop in jma_seed.PROPERTIES:
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
    for doc in jma_seed.DOCUMENTS:
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


def _delete_stale_properties(
    cur,
    summary: IngestSummary,
    object_ids: dict[str, int],
    source_ids: dict[str, int],
) -> None:
    """シードに現れない object_properties 行を削除する。

    シードの (object_id, property_name, source_id) の組に一致しない行が対象。
    旧題材の属性や、シードから外した属性が既存 DB に残り続けないようにする。
    """
    expected = {
        (
            object_ids[prop["object"]],
            prop["property_name"],
            source_ids[prop["source"]],
        )
        for prop in jma_seed.PROPERTIES
    }
    cur.execute("SELECT id, object_id, property_name, source_id FROM object_properties")
    stale_ids = [
        row[0] for row in cur.fetchall() if (row[1], row[2], row[3]) not in expected
    ]
    if stale_ids:
        cur.execute(
            "DELETE FROM object_properties WHERE id = ANY(%s)", (stale_ids,)
        )
    summary.deleted["object_properties"] = len(stale_ids)


def _delete_stale_documents(
    cur, summary: IngestSummary, source_ids: dict[str, int]
) -> None:
    """シードに現れない documents 行を削除する。

    シードの (source_id, content) の組に一致しない行が対象。旧題材のチャンク
    に加え、シード文面を改訂（誤記修正など）したときの旧文面も置き換わる
    （Issue #37 / PR #38 の同期を全行対象に一般化したもの）。
    """
    contents_by_source_id: dict[int, list[str]] = {}
    for doc in jma_seed.DOCUMENTS:
        contents_by_source_id.setdefault(
            source_ids[doc["source"]], []
        ).append(doc["content"])
    deleted = 0
    # シードに現れる source_id: シードにない文面を削除
    for source_id, contents in contents_by_source_id.items():
        cur.execute(
            "DELETE FROM documents"
            " WHERE source_id = %s AND content != ALL(%s)",
            (source_id, contents),
        )
        deleted += cur.rowcount
    # シードに現れない source_id: 全行削除（旧題材のチャンク）
    cur.execute(
        "DELETE FROM documents WHERE source_id != ALL(%s)",
        (list(contents_by_source_id.keys()),),
    )
    deleted += cur.rowcount
    summary.deleted["documents"] = deleted


def _delete_stale_objects(cur, summary: IngestSummary) -> None:
    """シードに現れない objects 行を削除する（旧題材のオブジェクト）。

    object_properties は先行の削除で一致済みだが、FK は ON DELETE CASCADE の
    ため参照が残っていても整合は保たれる。
    """
    cur.execute(
        "DELETE FROM objects WHERE name != ALL(%s)",
        ([obj["name"] for obj in jma_seed.OBJECTS],),
    )
    summary.deleted["objects"] = cur.rowcount


def _delete_stale_sources(cur, summary: IngestSummary) -> None:
    """シードに現れず、どこからも参照されていない sources 行を削除する。

    documents / object_properties からの FK は ON DELETE RESTRICT のため、
    参照が残っている行は削除対象にしない（先行の削除で旧題材の参照は消えて
    いるので、旧題材の sources はここで削除される）。
    """
    seed_keys = [
        (src["source_url"], src["retrieved_at"])
        for src in jma_seed.SOURCES.values()
    ]
    cur.execute(
        """
        DELETE FROM sources s
        WHERE NOT EXISTS (
                SELECT 1 FROM unnest(%s::text[], %s::text[]) AS t(u, r)
                WHERE s.source_url = t.u
                  AND s.retrieved_at = t.r::timestamptz
              )
          AND NOT EXISTS (
                SELECT 1 FROM documents d WHERE d.source_id = s.id
              )
          AND NOT EXISTS (
                SELECT 1 FROM object_properties p WHERE p.source_id = s.id
              )
        """,
        (
            [k[0] for k in seed_keys],
            [k[1] for k in seed_keys],
        ),
    )
    summary.deleted["sources"] = cur.rowcount
