"""obs.marker を obs.heartbeat へ改名する（Issue #133）

一定間隔で 1 行だけ書き込み、最新行との時刻差から遅れを測るこのパターンは、一般に
**heartbeat table** と呼ばれる（代表例: Percona Toolkit の `pt-heartbeat`。MySQL の
replication lag 計測で、親側が定期的に 1 行書き、子側で時刻差を取る）。本テーブルは
同じ仕組みを PITR の RPO 実測に転用したもの。`marker` は説明的だが業界標準語ではないため、
標準語に接続する名前へ改める。

なお PostgreSQL 自身の restore point（`pg_create_restore_point()` /
`recovery_target_name`）は「1 点に打つ目印」であり、連続的に刻む本テーブルとは用途が異なる。
名前が似ているだけで別物なので、混同しないこと。

0002 は書き換えない（既存 DB に適用済みの revision を後から書き換えると、
適用済み環境と新規構築環境でスキーマ履歴が食い違う）。改名は追加の revision で行う。

**適用順序の注意**: rename した瞬間、旧 `collect.sql`（`INSERT INTO obs.marker`）を持つ
採取 Job は `relation "obs.marker" does not exist` で失敗する。適用は新しい ops イメージの
デプロイと組で行うこと（手順は PR / 適用プラン側）。

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-26
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # RENAME は列・型・制約・identity シーケンスをそのまま引き継ぐ（データ移行は発生しない）。
    # PRIMARY KEY 制約名（obs.marker_pkey）は追随しないが、名前で参照している箇所は無いため放置する
    op.execute("ALTER TABLE obs.marker RENAME TO heartbeat")


def downgrade() -> None:
    op.execute("ALTER TABLE obs.heartbeat RENAME TO marker")
