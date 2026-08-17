"""初期スキーマ: pgvector + provenance 対応の題材非依存スキーマ

- 設計判断は ADR-0002（マイグレーションツール）/ ADR-0003（スキーマ設計）を参照
- embedding は vector(1536) 固定（text-embedding-3-small 相当。提供元によらず同一）
- 実データは投入しない（題材未確定）

Revision ID: 0001
Revises:
Create Date: 2026-08-17
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # provenance の正本。データの出所を1行で表し、他テーブルから参照する
    op.execute(
        """
        CREATE TABLE sources (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_url TEXT NOT NULL,
            source_title TEXT NOT NULL,
            -- 再利用・ライセンスの根拠（例: 'CC0', 'public domain (NASA media guidelines)'）
            reuse_basis TEXT NOT NULL,
            retrieved_at TIMESTAMPTZ NOT NULL,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (source_url, retrieved_at)
        )
        """
    )

    # 題材のオブジェクト（天体・生物など題材非依存）。固有カラムは持たせない
    op.execute(
        """
        CREATE TABLE objects (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            kind TEXT,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # プロパティは行として持つ（オブジェクトごとに取得可能な property が異なる前提）。
    # source_id NOT NULL により「数値ごとの出所」を強制する
    op.execute(
        """
        CREATE TABLE object_properties (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            object_id BIGINT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
            property_name TEXT NOT NULL,
            value_numeric DOUBLE PRECISION,
            value_text TEXT,
            unit TEXT,
            -- 出所が参照されている限り sources の行は消せない（provenance 保護）
            source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT object_properties_value_present
                CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL),
            UNIQUE (object_id, property_name, source_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX object_properties_object_id_idx"
        " ON object_properties (object_id)"
    )

    # RAG 用ドキュメント（チャンク）。embedding は ingest 後に埋める場合があるため NULL 許容
    op.execute(
        """
        CREATE TABLE documents (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            content TEXT NOT NULL,
            embedding vector(1536),
            -- 出所が参照されている限り sources の行は消せない（provenance 保護）
            source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # sources との JOIN / sources 削除時の参照チェック用
    op.execute(
        "CREATE INDEX documents_source_id_idx ON documents (source_id)"
    )
    # cosine 距離での近傍検索用。データ量が小さいうちから作っておいて害はない
    op.execute(
        "CREATE INDEX documents_embedding_hnsw_idx"
        " ON documents USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS object_properties")
    op.execute("DROP TABLE IF EXISTS objects")
    op.execute("DROP TABLE IF EXISTS sources")
    # この DB はアプリ専用のため extension も落として往復を対称にする
    op.execute("DROP EXTENSION IF EXISTS vector")
