"""気象庁シードデータ取り込みの冪等性・差分同期・provenance テスト（ADR-0003 / ADR-0007 / ADR-0008）。

- シードデータ自体の整合性（DB 不要）と、DB への投入（@pytest.mark.db）を検証する
- 実 LLM・外部 API は呼ばない。embedding は投入しない（NULL のまま）
"""

import pytest

from app.ingest import jma_seed
from app.ingest.runner import run_ingest

# --- シードデータ整合性（DB 不要） --------------------------------------------


def test_seed_properties_reference_known_objects_and_sources():
    object_names = {obj["name"] for obj in jma_seed.OBJECTS}
    for prop in jma_seed.PROPERTIES:
        assert prop["object"] in object_names
        assert prop["source"] in jma_seed.SOURCES
    for doc in jma_seed.DOCUMENTS:
        assert doc["source"] in jma_seed.SOURCES


def test_seed_properties_have_value_and_verbatim_note():
    """全プロパティが値を持ち、note に根拠原文（引用符付き）が残っている。"""
    for prop in jma_seed.PROPERTIES:
        has_value = (
            prop.get("value_numeric") is not None
            or prop.get("value_text") is not None
        )
        assert has_value, f"{prop['property_name']} に値がない"
        # 根拠となったページ上の原文を引用符付きで保持していること
        assert '"' in prop["note"], f"{prop['property_name']} の note に原文引用がない"


def test_seed_sources_record_reuse_basis():
    """全 source の reuse_basis に公共データ利用規約準拠が記録されている。"""
    for key, src in jma_seed.SOURCES.items():
        assert "公共データ利用規約" in src["reuse_basis"], key
        assert src["retrieved_at"] == jma_seed.RETRIEVED_AT, key
        assert src["source_url"].startswith("https://www."), key


def test_seed_sources_are_jma_pages_only():
    """出典は気象庁ホームページのみ（docs/data-sources.md と対応する）。"""
    for key, src in jma_seed.SOURCES.items():
        assert ".jma.go.jp/" in src["source_url"], key


def test_seed_contains_no_forecast_data():
    """予報に当たるデータを含まない（気象業務法対応。ADR-0008）。

    シードは過去の記録と解説のみ。将来の予測を示す表現が値・チャンクに
    含まれないことを機械的に確認する（網羅はできないため既知の表現に限る）。
    """
    forecast_markers = ("明日の天気", "週間予報", "降水確率")
    for prop in jma_seed.PROPERTIES:
        text = str(prop.get("value_text") or "")
        for marker in forecast_markers:
            assert marker not in text, prop["property_name"]
    for doc in jma_seed.DOCUMENTS:
        for marker in forecast_markers:
            assert marker not in doc["content"]


def test_seed_keeps_jma_sensory_expressions_verbatim():
    """企画の核である気象庁自身の比喩・体感表現が逐語で保持されている。"""
    all_chunks = "\n".join(doc["content"] for doc in jma_seed.DOCUMENTS)
    assert "バケツをひっくり返したように降る" in all_chunks
    assert "滝のように降る" in all_chunks
    assert "息苦しくなるような圧迫感がある。恐怖を感ずる" in all_chunks
    assert "沖合いではジェット機に匹敵する速さ" in all_chunks
    assert "立っていることができず、はわないと動くことができない" in all_chunks
    assert "テレビが台から落ちることがある" in all_chunks


# --- DB 投入（TEST_DATABASE_URL 未設定なら skip） -----------------------------


@pytest.mark.db
def test_ingest_is_idempotent(db_conn):
    """2 回実行しても行数が増えない（UNIQUE 制約 + 存在チェック）。"""
    first = run_ingest(db_conn)
    second = run_ingest(db_conn)

    assert first.inserted["sources"] == len(jma_seed.SOURCES)
    assert first.inserted["objects"] == len(jma_seed.OBJECTS)
    assert first.inserted["object_properties"] == len(jma_seed.PROPERTIES)
    assert first.inserted["documents"] == len(jma_seed.DOCUMENTS)

    # 2 回目は 1 行も挿入されず、総行数は変わらない
    assert all(count == 0 for count in second.inserted.values()), second.inserted
    assert second.total == first.total
    # シードと DB が一致していれば削除も発生しない
    assert all(count == 0 for count in second.deleted.values()), second.deleted


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
        assert cur.fetchone()[0] == len(jma_seed.PROPERTIES)
        # documents の embedding は投入しない（NULL のまま。次フェーズで結線）
        cur.execute("SELECT count(*) FROM documents WHERE embedding IS NOT NULL")
        assert cur.fetchone()[0] == 0


@pytest.mark.db
def test_ingest_replaces_stale_data_from_previous_theme(db_conn):
    """旧題材のデータが投入済みの DB に実行すると、シードの全量に置き換わる。

    題材の乗り換え（NASA → 気象庁。ADR-0007）で、既存 DB に旧題材の
    objects / sources / object_properties / documents が残り続けない
    ことを検証する（Issue #41 の主目的）。
    """
    with db_conn.cursor() as cur:
        # 旧題材（NASA 相当）のデータを直接投入して「乗り換え前の DB」を再現する
        cur.execute(
            """
            INSERT INTO sources
                (source_url, source_title, reuse_basis, retrieved_at)
            VALUES ('https://science.nasa.gov/universe/black-holes/',
                    'Black Holes - NASA Science',
                    'public domain (NASA media usage guidelines)',
                    '2026-08-18T05:50:45+00:00')
            RETURNING id
            """
        )
        old_source_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO objects (name, kind) VALUES ('ブラックホール',"
            " 'black_hole') RETURNING id"
        )
        old_object_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO object_properties
                (object_id, property_name, value_numeric, unit, source_id, note)
            VALUES (%s, 'most_massive_known_mass', 6.6e10, 'solar_mass', %s,
                    'stale note')
            """,
            (old_object_id, old_source_id),
        )
        cur.execute(
            "INSERT INTO documents (content, source_id)"
            " VALUES ('旧題材のチャンク', %s)",
            (old_source_id,),
        )
    db_conn.commit()

    result = run_ingest(db_conn)

    assert result.deleted["object_properties"] == 1
    assert result.deleted["documents"] == 1
    assert result.deleted["objects"] == 1
    assert result.deleted["sources"] == 1
    assert result.total == {
        "sources": len(jma_seed.SOURCES),
        "objects": len(jma_seed.OBJECTS),
        "object_properties": len(jma_seed.PROPERTIES),
        "documents": len(jma_seed.DOCUMENTS),
    }
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM objects WHERE name = 'ブラックホール'")
        assert cur.fetchone()[0] == 0
        cur.execute(
            "SELECT count(*) FROM sources WHERE source_url LIKE '%%nasa%%'"
        )
        assert cur.fetchone()[0] == 0


@pytest.mark.db
def test_document_revision_replaces_stale_chunk(db_conn, monkeypatch):
    """シード文面を改訂して再実行すると、旧チャンクが消え新チャンクに置き換わる。

    挿入だけの実装だと、文面修正後も既存 DB に誤った旧文面が残り続ける
    （Issue #37 で顕在化した経路）。
    """
    run_ingest(db_conn)

    revised = [dict(doc) for doc in jma_seed.DOCUMENTS]
    old_content = revised[-1]["content"]
    new_content = old_content + "（改訂版）"
    revised[-1] = {**revised[-1], "content": new_content}
    monkeypatch.setattr(jma_seed, "DOCUMENTS", revised)

    result = run_ingest(db_conn)

    assert result.inserted["documents"] == 1
    assert result.deleted["documents"] == 1
    assert result.total["documents"] == len(revised)
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM documents WHERE content = %s", (old_content,)
        )
        assert cur.fetchone()[0] == 0, "旧チャンクが DB に残っている"
        cur.execute(
            "SELECT count(*) FROM documents WHERE content = %s", (new_content,)
        )
        assert cur.fetchone()[0] == 1
