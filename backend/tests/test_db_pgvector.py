"""pgvector 類似検索と provenance 制約の DB テスト。

手書きの固定ベクトルで距離順序を決定的に検証する（LLM・embedding API 不要）。
TEST_DATABASE_URL の DB（CI では services: の pgvector コンテナ）に対して実行する。
"""

import pytest

pytestmark = pytest.mark.db

DIMS = 1536


def vec(*head: float) -> str:
    """先頭要素だけ指定し、残りを 0 で埋めた 1536 次元ベクトルのリテラルを作る。"""
    values = list(head) + [0.0] * (DIMS - len(head))
    return "[" + ",".join(str(v) for v in values) + "]"


def _insert_source(cur) -> int:
    cur.execute(
        """
        INSERT INTO sources (source_url, source_title, reuse_basis, retrieved_at)
        VALUES ('https://example.com/dummy', 'dummy', 'CC0', now())
        RETURNING id
        """
    )
    return cur.fetchone()[0]


def test_cosine_similarity_order_is_deterministic(db_conn):
    """[1,0,...] のクエリに対し [0.9,0.1,...] が [0,1,...] より近い。"""
    with db_conn.cursor() as cur:
        source_id = _insert_source(cur)
        docs = {
            "identical": vec(1.0),
            "near": vec(0.9, 0.1),
            "orthogonal": vec(0.0, 1.0),
        }
        for content, embedding in docs.items():
            cur.execute(
                "INSERT INTO documents (content, embedding, source_id)"
                " VALUES (%s, %s::vector, %s)",
                (content, embedding, source_id),
            )
        cur.execute(
            "SELECT content, embedding <=> %s::vector AS distance"
            " FROM documents ORDER BY distance",
            (vec(1.0),),
        )
        rows = cur.fetchall()

    assert [r[0] for r in rows] == ["identical", "near", "orthogonal"]
    distances = [r[1] for r in rows]
    assert distances[0] == pytest.approx(0.0)  # 同一ベクトルは距離 0
    assert distances[1] < distances[2]  # 近いものが先
    assert distances[2] == pytest.approx(1.0)  # 直交は cosine 距離 1


def test_embedding_dimension_is_enforced(db_conn):
    """vector(1536) のカラムは次元違いの挿入を拒否する。"""
    import psycopg

    with db_conn.cursor() as cur:
        source_id = _insert_source(cur)
        with pytest.raises(psycopg.errors.DataException):
            cur.execute(
                "INSERT INTO documents (content, embedding, source_id)"
                " VALUES ('bad', '[1,0,0]'::vector, %s)",
                (source_id,),
            )
    db_conn.rollback()


def test_property_value_requires_source(db_conn):
    """object_properties.source_id は NOT NULL（数値ごとの出所を強制）。"""
    import psycopg

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO objects (name) VALUES ('obj-a') RETURNING id"
        )
        object_id = cur.fetchone()[0]
        with pytest.raises(psycopg.errors.NotNullViolation):
            cur.execute(
                "INSERT INTO object_properties"
                " (object_id, property_name, value_numeric, source_id)"
                " VALUES (%s, 'radius', 1.0, NULL)",
                (object_id,),
            )
    db_conn.rollback()


def test_source_cannot_be_deleted_while_referenced(db_conn):
    """参照されている sources 行は削除できない（ON DELETE RESTRICT）。"""
    import psycopg

    with db_conn.cursor() as cur:
        source_id = _insert_source(cur)
        cur.execute(
            "INSERT INTO documents (content, source_id) VALUES ('d', %s)",
            (source_id,),
        )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute("DELETE FROM sources WHERE id = %s", (source_id,))
    db_conn.rollback()


def test_property_requires_some_value(db_conn):
    """value_numeric / value_text の両方 NULL は CHECK 制約で拒否される。"""
    import psycopg

    with db_conn.cursor() as cur:
        source_id = _insert_source(cur)
        cur.execute("INSERT INTO objects (name) VALUES ('obj-b') RETURNING id")
        object_id = cur.fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO object_properties"
                " (object_id, property_name, source_id)"
                " VALUES (%s, 'radius', %s)",
                (object_id, source_id),
            )
    db_conn.rollback()
