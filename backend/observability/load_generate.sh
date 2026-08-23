#!/bin/bash
# フェーズ 2 の負荷生成（Issue #112。Manual トリガーの Container Apps Job から実行）
# 設計の正本: docs/operations/credit-window-execution-plan.md §5-5
#
# - 書き込み先は load スキーマのみ（obs / public に触れない = フェーズ 1 を汚さない）
# - フェーズゲート: obs.phase_config が 'load' / 'gp_load' でなければ即 exit 1。
#   Manual トリガー + このコードゲートの二重で「フェーズ 1 中に一度も起動しない」を担保する
#   （受け入れ条件。誤って Job を起動しても DB には 1 行も書かれない）
# - 各イテレーション: INSERT LOAD_BATCH_ROWS 行 + grp = i % 100 の一括 UPDATE
#   （UPDATE が dead tuple の供給源。grp インデックスにより HOT 最適化を抑制 =
#   実運用の「インデックス付きテーブルの UPDATE 負荷」に寄せる）
# - スループット / レイテンシは機械可読レコード（LOADGEN ts=... elapsed_ms=...）で
#   標準出力へ。H3（クレジット枯渇で劣化）の負荷生成側の証跡になる
# - 負荷強度の上限根拠: B1ms 実測仕様 1 vCore / 2 GiB / 640 IOPS / 10 MiB/s（計画 §5-5）。
#   既定値（batch 500 / sleep 1s）は「まず控えめに始めて CPU Credits Remaining を見ながら
#   env で段階投入する」ための出発点で、数値の実測根拠はまだ無い（デプロイ後に実測で調整）

set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL が未設定}"
LOAD_DURATION_SECONDS="${LOAD_DURATION_SECONDS:-3600}"
LOAD_BATCH_ROWS="${LOAD_BATCH_ROWS:-500}"
LOAD_SLEEP_SECONDS="${LOAD_SLEEP_SECONDS:-1}"

# --- フェーズゲート ---
phase=$(psql "$DATABASE_URL" -X -A -t -v ON_ERROR_STOP=1 \
  -c "SELECT phase FROM obs.phase_config WHERE id = 1")
if [ "$phase" != "load" ] && [ "$phase" != "gp_load" ]; then
  echo "ERROR: phase='${phase}' のため負荷生成を拒否する（'load' / 'gp_load' のみ許可。" \
       "遷移手順は credit-window-execution-plan.md §5-5）" >&2
  exit 1
fi

echo "LOADGEN start phase=${phase} duration_s=${LOAD_DURATION_SECONDS}" \
     "batch=${LOAD_BATCH_ROWS} sleep_s=${LOAD_SLEEP_SECONDS}"

end=$(( $(date +%s) + LOAD_DURATION_SECONDS ))
i=0
while [ "$(date +%s)" -lt "$end" ]; do
  i=$((i + 1))
  grp=$((i % 100))
  t0=$(date +%s%3N)
  # 1 イテレーション = 1 トランザクション（psql -c は単一トランザクション）。
  # 失敗は ON_ERROR_STOP + set -e で fail loud（リトライしない。Job の失敗として残す）
  psql "$DATABASE_URL" -X -q -v ON_ERROR_STOP=1 \
    -v batch="$LOAD_BATCH_ROWS" -v grp="$grp" <<'SQL'
INSERT INTO load.load_rows (grp, payload)
SELECT g % 100, repeat(md5(g::text), 8)
FROM generate_series(1, :batch) AS g;
UPDATE load.load_rows
SET payload = repeat(md5(clock_timestamp()::text), 8), updated_at = now()
WHERE grp = :grp;
SQL
  t1=$(date +%s%3N)
  echo "LOADGEN ts=$(date -u +%Y-%m-%dT%H:%M:%SZ) iter=${i} grp=${grp}" \
       "batch=${LOAD_BATCH_ROWS} elapsed_ms=$((t1 - t0))"
  sleep "$LOAD_SLEEP_SECONDS"
done

echo "LOADGEN done iterations=${i}"
