"""NASA シードデータ取り込みの冪等性・provenance テスト（ADR-0003 / ADR-0006）。

- シードデータ自体の整合性（DB 不要）と、DB への投入（@pytest.mark.db）を検証する
- 実 LLM・外部 API は呼ばない。embedding は投入しない（NULL のまま）
"""

import pytest

from app.ingest import nasa_seed
from app.ingest.runner import run_ingest

# --- シードデータ整合性（DB 不要） --------------------------------------------


def test_seed_properties_reference_known_objects_and_sources():
    object_names = {obj["name"] for obj in nasa_seed.OBJECTS}
    for prop in nasa_seed.PROPERTIES:
        assert prop["object"] in object_names
        assert prop["source"] in nasa_seed.SOURCES
    for doc in nasa_seed.DOCUMENTS:
        assert doc["source"] in nasa_seed.SOURCES


def test_seed_properties_have_value_and_verbatim_note():
    """全プロパティが値を持ち、note に根拠原文（引用符付き）が残っている。"""
    for prop in nasa_seed.PROPERTIES:
        has_value = (
            prop.get("value_numeric") is not None
            or prop.get("value_text") is not None
        )
        assert has_value, f"{prop['property_name']} に値がない"
        # 根拠となったページ上の原文を引用符付きで保持していること
        assert '"' in prop["note"], f"{prop['property_name']} の note に原文引用がない"


def test_seed_sources_record_reuse_basis_and_citation_status():
    """reuse_basis に再利用根拠と原典提示の有無が記録されている。"""
    for key, src in nasa_seed.SOURCES.items():
        assert "public domain" in src["reuse_basis"], key
        assert src["retrieved_at"] == nasa_seed.RETRIEVED_AT, key
    # NASA 解説ページは原典（論文）を示していない事実を記録する
    assert (
        "does not cite primary literature"
        in nasa_seed.SOURCES["science-black-holes"]["reuse_basis"]
    )
    # マグネターのニュース記事のみ Nature 論文を典拠として明示している
    magnetar = nasa_seed.SOURCES["nasa-magnetar-eruptions"]["reuse_basis"]
    assert "Nature" in magnetar
    assert "does not cite" not in magnetar


# --- DB 投入（TEST_DATABASE_URL 未設定なら skip） -----------------------------


@pytest.mark.db
def test_ingest_is_idempotent(db_conn):
    """2 回実行しても行数が増えない（UNIQUE 制約 + 存在チェック）。"""
    first = run_ingest(db_conn)
    second = run_ingest(db_conn)

    assert first.inserted["sources"] == len(nasa_seed.SOURCES)
    assert first.inserted["objects"] == len(nasa_seed.OBJECTS)
    assert first.inserted["object_properties"] == len(nasa_seed.PROPERTIES)
    assert first.inserted["documents"] == len(nasa_seed.DOCUMENTS)

    # 2 回目は 1 行も挿入されず、総行数は変わらない
    assert all(count == 0 for count in second.inserted.values()), second.inserted
    assert second.total == first.total


@pytest.mark.db
def test_ingested_properties_have_source_and_note(db_conn):
    """投入された全プロパティに source_id と根拠原文（note）が埋まっている。"""
    run_ingest(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM object_properties"
            " WHERE source_id IS NULL OR note IS NULL OR note = ''"
        )
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM object_properties")
        assert cur.fetchone()[0] == len(nasa_seed.PROPERTIES)
        # documents の embedding は投入しない（NULL のまま。次フェーズで結線）
        cur.execute("SELECT count(*) FROM documents WHERE embedding IS NOT NULL")
        assert cur.fetchone()[0] == 0


@pytest.mark.db
def test_same_property_can_hold_multiple_sources(db_conn):
    """同一属性を複数出典から保持できる（食い違いを両方残す設計の実証）。"""
    run_ingest(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM object_properties op
            JOIN objects o ON o.id = op.object_id
            WHERE o.name = '中性子星'
              AND op.property_name = 'magnetic_field_vs_earth'
            """
        )
        assert cur.fetchone()[0] == 2
