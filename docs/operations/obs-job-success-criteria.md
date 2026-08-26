# obs 採取 Job の合否判定基準と運用クエリ（#137）

obs 採取 Job（`caj-felisaichatbot-dev-obs`）の実行結果をどう判定し、失敗をどう数えるかの正本。
原因切り分けの実測と証跡は
[Issue #131 のコメント](https://github.com/kmryst/felis-ai-chatbot/issues/131#issuecomment-5426795451)
にあり、本書はその運用面の結論だけを持つ。実測値を本書へ転記しない
（[production-readiness.md](../production-readiness.md) と同じ「事実の詳細は追跡先が正本」の運用）。

## 1. 合否判定基準

**obs Job の合否は execution status ではなく、採取データの完全性で判定する。**
`DeadlineExceeded` の件数は合否に使わず、**別指標**として件数と原因を記録する。

- この基準は Issue #104 の実装時に採用済みで、フェーズ 1 の 72h 実測
  （[観測記録 §9-2](../verification/observation-phase1/observations.md#9-2-execution-status-と採取データの完全性は別物である実測での裏取り)）
  で裏が取れている（execution Failed 41 件 / heartbeat 欠落 0 件）。本書は基準の再決定ではなく、
  既存決定の参照先を固定するもの
- データ完全性の一次証拠は **obs テーブルの実データ**（heartbeat の分単位カウント、
  各系列の gap 分布）であり、Log Analytics のログ件数は補助に留める（同 §3-4）
- フェーズ間比較の基準値: フェーズ 1（固定 72h 窓）の execution 失敗率 **0.95%（41 / 4,320）**、
  データ欠落 **0 件（4,320 / 4,320）**

## 2. 失敗の 2 モードと、対処しない判断（#131）

`DeadlineExceeded` の実体は SQL ではなく **Container Apps 側のコンテナ起動パイプライン**にあり、
2 モードに分かれる（いずれも psql は完走しており、採取データは欠けていない）:

- **モード A（起動遅延）**: pod 作成から image pull 開始までに通常 ~13s のところ ~38s の空白が
  入り、コンテナ起動が +52s 超にずれ込んで完了ステータス登録が deadline に間に合わない
- **モード B（完了イベントの喪失）**: コンテナは exit 0 で終了しているのに `Completed`
  イベントが記録されず、deadline で殺される

空白の内部要因・イベント喪失の機構はテナント可視ログから特定できない（プラットフォーム内部）。
対処候補（`replica_timeout` 延長 / cron 間隔変更 / SQL 分割）はいずれも副作用が実害
（= ゼロ）に見合わず、**「何もしない + 本書による判定基準の明文化」を採用した**。
`replica_timeout_in_seconds = 55` を上げない個別の理由は
`terraform/ephemeral/main.tf` の該当箇所のコメントに記載している。

## 3. 運用クエリ: DB だけでモード A を計数する

モード A の遅延起動は heartbeat の `ts`（`now()` = トランザクション開始時刻）を分内 +52s 超へ
押し出すため、**秒オフセット > 45s の件数がモード A の失敗件数と 1 対 1 で一致する**
（#131 で実測確認済み: 8/23: 0 / 8/24: 4 / 8/25: 11 / 8/26: 20 で、Log Analytics の
イベント時系列から分類したモード A の日別失敗件数と完全一致。遅延起動が成功した例は 0 件）。
Log Analytics を使わず、ops コンテナ経由の SELECT 1 本で数えられる。

```sql
SELECT (ts AT TIME ZONE 'UTC')::date AS day, count(*) AS mode_a
FROM obs.heartbeat
WHERE extract(second FROM ts) > 45
GROUP BY 1 ORDER BY 1;
```

実行例（ops コンテナ内。2026-08-26T14:26Z 実測。読み取りのみ）:

```console
$ psql "$DATABASE_URL" -X -At -F'|' -c "SELECT (ts AT TIME ZONE 'UTC')::date AS day, count(*) FROM obs.heartbeat WHERE extract(second FROM ts) > 45 GROUP BY 1 ORDER BY 1;"
2026-08-24|4
2026-08-25|11
2026-08-26|21
```

前提と限界:

- cron の起動秒はゼロ（[観測記録 §9-3](../verification/observation-phase1/observations.md#9-3-azurerm-provider-の-schedule-トリガー-cron-記法schema-確認)）、
  SQL 所要は 1 秒未満、成功 execution の psql 終了は最大 +42.1s（#131 の成功側ベースライン）
  という実測に依存する。cron 記法・SQL の構成を変えたら閾値 45s を再検証する
- **モード B はこのクエリでは検知できない**（DB 上は正常な行になる）。総失敗件数は従来どおり
  `az containerapp job execution list` / Log Analytics の `DeadlineExceeded` で数える
- 件数の日次推移の継続観測は **Issue #138** で行う（8/23 以降、日次で単調増加しており、
  原因はテナント側から特定できないため傾向の見張りに切り替える）

## 4. フェーズ 2 への影響

- **pgstattuple の採取コストは高負荷フェーズでも悪化しない**: `collect.sql` の bloat 走査対象は
  VALUES リストで `obs.heartbeat` / `obs.counter` の固定 2 テーブルのみで、フェーズ 2 の
  `load` スキーマは走査対象に入らない。heartbeat の成長は 1,440 行/日 ≈ 63KB/日 で、
  実測 2.29ms（#131）から 55s まで 4 桁以上の余裕がある
- 一方、失敗の実駆動因（ACA 起動パイプライン）は日次で悪化傾向にあり、負荷 Job が同じ
  Container Apps environment に乗ることによる影響は**不確実（推測。定量根拠なし）**。
  フェーズ 2 の記録では §1 の基準値（失敗率 0.95% / 欠落 0 件）と §3 の日別件数を比較する

## 5. 鮮度ゲートのスイッチ名の対応（ENFORCE / OBS_FRESHNESS_ENFORCE。#141）

外形監視 workflow（`.github/workflows/readyz-probe.yml`）の鮮度ゲートでは、
**job env の `ENFORCE` と repository variable の `OBS_FRESHNESS_ENFORCE` は同一のスイッチ**である
（workflow が `ENFORCE: ${{ vars.OBS_FRESHNESS_ENFORCE || 'true' }}` と束ねており、既定 true = ゲート有効。
運用上の設定・確認先は repository variable 側。
[credit-window-execution-plan.md §4](./credit-window-execution-plan.md) の項目 4 参照）。
`enforce` という語の選択自体はポリシー系ツールの標準語彙に沿っている
（Kyverno の `validationFailureAction: Enforce / Audit`、Gatekeeper の `enforcementAction`）。

注意: `scripts/test/readyz-probe-freshness-test.sh` が workflow 定義の `.jobs.probe.env.ENFORCE` を
逐語パースして既定値を検証しているため、将来 workflow 側の名前を repository variable に揃える場合は
workflow とテストスクリプトの 2 箇所を同時に修正する必要がある。
