"""観測スキーマ: マーカー常時書き込みとスナップショット採取（Issue #104）

- 設計の正本: docs/operations/credit-window-execution-plan.md §5-3
- 観測する側（スナップショット）とされる側（マーカー / カウンタ）を同居させるが、
  テーブルを分けることで pg_stat_user_tables のテーブル単位統計により
  観測者効果を定量化できるようにする（同 §5-3）
- **前提**: pgstattuple 拡張は Azure ではサーバーパラメータ azure.extensions の
  許可リストに PGSTATTUPLE が含まれている必要がある（SHOW azure.extensions で確認。
  未許可のままこの migration を実行すると CREATE EXTENSION で失敗する = 意図的に
  fail loud。許可リスト変更は Azure への書き込みのためデプロイ手順側で行う）

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-23
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 実 bloat 測定用（credit-window-execution-plan.md §3 の 2）
    op.execute("CREATE EXTENSION IF NOT EXISTS pgstattuple")

    op.execute("CREATE SCHEMA obs")

    # --- 観測される側（書き込みワークロード） ---

    # マーカー: 1 分間隔の INSERT-only。PITR の RPO 物差し + insert-vacuum
    # （閾値 1000 + 0.2×N。実測値）の「伸びる発火カデンツ」の観測対象
    op.execute(
        """
        CREATE TABLE obs.marker (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            ts TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # カウンタ: 毎分 UPDATE される 1 行。dead tuple の供給源
    # （閾値 50 + 0.2×1 ≈ 50 → 約 50 分周期の自然発火。実測パラメータで計算済み）
    op.execute(
        """
        CREATE TABLE obs.counter (
            id INT PRIMARY KEY,
            n BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("INSERT INTO obs.counter (id, n) VALUES (1, 0)")

    # --- 観測する側（スナップショット。すべて INSERT-only） ---

    # テーブル単位統計（5 分間隔。autovacuum 発火の鋸歯を挟む）
    op.execute(
        """
        CREATE TABLE obs.table_stats (
            ts TIMESTAMPTZ NOT NULL DEFAULT now(),
            relname TEXT NOT NULL,
            n_live_tup BIGINT,
            n_dead_tup BIGINT,
            n_tup_ins BIGINT,
            n_tup_upd BIGINT,
            autovacuum_count BIGINT,
            last_autovacuum TIMESTAMPTZ,
            autoanalyze_count BIGINT,
            last_autoanalyze TIMESTAMPTZ
        )
        """
    )

    # DB 単位統計（5 分間隔。WAL 生成レート / サイズ / XID age）
    op.execute(
        """
        CREATE TABLE obs.db_stats (
            ts TIMESTAMPTZ NOT NULL DEFAULT now(),
            wal_records BIGINT,
            wal_bytes NUMERIC,
            db_size_bytes BIGINT,
            frozen_xid_age BIGINT
        )
        """
    )

    # 実 bloat（1 時間間隔。フルスキャンを伴うため間隔を粗くする = 観測者効果の抑制）
    op.execute(
        """
        CREATE TABLE obs.bloat_stats (
            ts TIMESTAMPTZ NOT NULL DEFAULT now(),
            relname TEXT NOT NULL,
            table_len BIGINT,
            tuple_percent DOUBLE PRECISION,
            dead_tuple_percent DOUBLE PRECISION,
            free_percent DOUBLE PRECISION
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA obs CASCADE")
    op.execute("DROP EXTENSION IF EXISTS pgstattuple")
