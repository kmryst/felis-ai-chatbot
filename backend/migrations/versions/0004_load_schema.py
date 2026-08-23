"""フェーズ 2 負荷生成用の load スキーマ（Issue #112）

- 設計の正本: docs/operations/credit-window-execution-plan.md §5-5
- 負荷生成は専用 load スキーマにのみ書き込み、obs / public に触れない
  （フェーズ 1 のベースラインを汚さない）。採取側（#104 の collect.sql）は
  schemaname IN ('obs','public','load') を既に対象に含むため無変更のまま、
  このテーブルの行が obs.table_stats に phase ラベルつきで積まれる
- grp 列は UPDATE の的（イテレーションごとに grp = i % 100 の行を一括更新して
  dead tuple を量産する）。インデックスは grp のみ（UPDATE を HOT にしない =
  インデックス付き列があると heap-only tuple 最適化が効かず、実運用の
  「インデックスを持つテーブルの UPDATE 負荷」に近づける）

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-23
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA load")
    op.execute(
        """
        CREATE TABLE load.load_rows (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            grp INT NOT NULL,
            payload TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX load_rows_grp_idx ON load.load_rows (grp)")


def downgrade() -> None:
    op.execute("DROP SCHEMA load CASCADE")
