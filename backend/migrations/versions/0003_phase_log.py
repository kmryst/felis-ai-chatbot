"""フェーズ遷移の追記専用履歴 obs.phase_log（Issue #114 の 1）

- obs.phase_config は 1 行上書きのため「baseline がいつ終わったか」を後から
  復元できない（外部レビュー指摘）。追記専用の履歴テーブルを足す
- 遷移は 1 文の CTE（UPDATE ... RETURNING → INSERT）で行い、履歴の書き忘れを
  構造的に防ぐ（手順は docs/operations/credit-window-execution-plan.md §5-5）。
  トリガーでの自動記録も検討したが、観測スキーマに隠れた副作用を持ち込まない
  方針（採取系はすべて明示的な文）を優先した
- 初期行は phase_config の現在行から複製する（履歴の起点 = baseline の開始時刻を
  失わない）

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-23
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # INSERT-only（採取系と同じ方針。UPDATE / DELETE はしない運用）
    op.execute(
        """
        CREATE TABLE obs.phase_log (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            phase TEXT NOT NULL CHECK (
                phase IN ('baseline', 'load', 'gp_load', 'cooldown')
            ),
            since TIMESTAMPTZ NOT NULL,
            logged_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # 現在フェーズを履歴の起点として複製（phase_config が無い・空の状態は
    # 0002 が保証しないため、ここでは存在する行だけを写す）
    op.execute(
        """
        INSERT INTO obs.phase_log (phase, since)
        SELECT phase, since FROM obs.phase_config WHERE id = 1
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE obs.phase_log")
