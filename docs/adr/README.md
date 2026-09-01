# Architecture Decision Records

このディレクトリは、`felis-ai-chatbot` の重要な設計判断を ADR（Architecture Decision Record）として残す場所です。

## 番号付け

- ファイル名は `NNNN-kebab-case-title.md` とする
- `NNNN` は 4 桁の連番とし、一度使った番号は再利用しない
- 番号は ADR ファイルを追加する PR の時点で、`docs/adr/` 配下の最大番号 + 1 として確定する。Issue / ブランチの段階では番号を予約しない
- supersede する場合も古い ADR は削除せず、新しい ADR から参照する

## 形式

各 ADR は少なくとも次の項目を含めます。

- `ステータス`
- `日付`
- `決定内容`
- `背景`
- `検討した選択肢`
- `採択理由`
- `影響`
- `関連`

### ステータスの語彙

- `Proposed` — 提案中。まだ採択されていない
- `Accepted` — 採択済み。現在有効な判断
- `Superseded` — 後続の ADR に置き換えられた（置き換え先 ADR を `関連` から参照する）
- `Deprecated` — 廃止。置き換え先はないが、もう採用しない

### 日付の扱い

`日付` は **ADR を記録した日**であり、元の判断が行われた時期とは限りません。

## 一覧

| ADR | ステータス | 決定 |
| --- | --- | --- |
| [0001](./0001-bootstrap-by-manual-skeleton-copy.md) | Accepted | idp-golden-path の service-baseline skeleton を手動コピーしてリポジトリを立ち上げる |
| [0002](./0002-alembic-for-schema-migrations.md) | Accepted | DB スキーマ管理に Alembic（raw SQL マイグレーション）を採用する |
| [0003](./0003-provenance-schema-design.md) | Accepted | provenance を数値単位で保持する題材非依存スキーマ（プロパティ行テーブル + sources 正規化・vector(1536) 固定） |
| [0004](./0004-stub-llm-and-no-llm-in-ci.md) | Accepted | LLM は故障注入可能なスタブで開発し、CI・テストから実 LLM を呼ばない |
| [0005](./0005-app-ci-in-repo-not-idp.md) | Accepted | アプリケーション層（build / test / lint）の CI は本リポジトリに置き、idp-golden-path へ共通化しない |
| [0006](./0006-nasa-ai-terms-compliance.md) | Superseded | NASA AI 条項準拠 — 帰属の対象を AI 生成文から未加工の原文抜粋へ付け替える（ADR-0008 により置き換え） |
| [0007](./0007-jma-as-content-source.md) | Accepted | 題材の出典を気象庁ホームページ（気象・防災）に選定する |
| [0008](./0008-jma-attribution-and-weather-act-compliance.md) | Accepted | 気象庁の出典表示（記載例準拠）と気象業務法（17条・23条）への設計対応 |
| [0009](./0009-azure-openai-as-llm-provider.md) | Accepted | LLM 提供元を Azure OpenAI（japaneast。chat は無料試用クォータ制約で GlobalStandard）に確定する |
| [0010](./0010-rag-wiring-and-hallucination-guard.md) | Accepted | RAG を結線し、検索結果が閾値未満なら LLM を呼ばないハルシネーション・ガードをコードで担保する |
| [0011](./0011-backup-retention-and-geo-redundancy.md) | Accepted（geo 冗長は ADR-0019 で変更） | PostgreSQL のバックアップ保持 7 日（検証 3 日 < 窓 7 日）・geo 冗長無効を作成時に確定する |
| [0012](./0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) | Accepted | CI 用 service principal の最小権限化（PR credential / RBAC Administrator を見送り）と Terraform 管理リソース専用 RG の分離 |
| [0013](./0013-azure-resource-naming-convention.md) | Accepted | Azure リソース命名規則（CAF 略語準拠）の制定と未作成リソース名の統一（稼働中の Azure OpenAI は例外として記録） |
| [0014](./0014-keep-azure-openai-out-of-terraform.md) | Accepted | Azure OpenAI を Terraform 管理外に据え置く（import 却下。当初理由のクォータ喪失懸念は誤りと判明し、理由を引き直して確定） |
| [0015](./0015-ephemeral-layer-acr-container-apps-design.md) | Accepted（Log Analytics の配置は ADR-0016、egress IP 許可と 2 段階 apply は ADR-0018、serving のスケールゼロは ADR-0025 で変更） | ephemeral 層（ACR + Container Apps）の設計 — 最小 SKU・スケールゼロ・egress 経路・イメージタグ方針・ACR pull 認証（マネージド ID + AcrPull を管理外で手動払い出し） |
| [0016](./0016-log-analytics-workspace-in-persistent-layer.md) | Accepted | Log Analytics workspace を ephemeral 層から persistent 層へ移す（毎日の destroy から監視ログを切り離す。参照は data source） |
| [0017](./0017-no-nightly-stop-for-postgresql.md) | Accepted | PostgreSQL を夜間 stop しない（12か月無料枠の判明でコスト根拠が消え、停止は新規バックアップ停止という実害だけが残るため） |
| [0018](./0018-postgresql-private-access-and-vnet-integration.md) | Accepted | PostgreSQL を private access（VNet 統合）で確定し、運用経路を VNet 内の ops コンテナ（+ Manual マイグレーション Job）に一本化する |
| [0019](./0019-enable-geo-redundant-backup.md) | Accepted | geo 冗長バックアップを有効化する（無料枠の判明で 2 倍課金の前提が崩れ、cutover の再作成が最後の設定機会のため。ADR-0011 の geo 冗長部分のみ supersede） |
| [0020](./0020-credit-window-resource-strategy.md) | Accepted | クレジット失効日を締め切りとした期間観測方針への転換（Day 4/5 のコスト最小化制約を組み替える） |
| [0021](./0021-heartbeat-table-as-recovery-marker.md) | Accepted | `obs.heartbeat` への毎分書き込みを PITR の recovery marker と位置づける（負荷生成ではない。識別子は据え置き） |
| [0022](./0022-import-azure-monitor-into-terraform.md) | Accepted | Azure Monitor の監視リソース 6 件（Action Group + メトリクスアラート 5）を terraform import で persistent 層へ移行する（ID 不変 = 発火試験の証跡を保全） |
| [0023](./0023-no-second-granularity-downtime-measurement.md) | Accepted | HA ドリルの downtime を秒粒度で測らず 10 秒間隔で測る（RTO 目標 3 時間 と公称 60〜120 秒 は桁が 2 つ違い判定が変わらない。1 秒間隔は `/readyz` のハング時にプローブが積み上がる） |
| [0024](./0024-readyz-freshness-not-completeness.md) | Accepted | `/readyz` の鮮度判定に完全性の検査を持ち込まない（`/readyz` = 「いまの鮮度」／obs テーブルの gap 集計 = 「完全性」。gap スキャンは `statement_timeout` 2 秒の予算を食い、Issue #114 で避けた「観測系の問題が可用性 SLI の欠測に化ける」構造を作り直す） |
| [0025](./0025-serving-min-replicas-1-for-sli-integrity.md) | Accepted | serving を min_replicas 1 へ変更し cold start による可用性 SLI の汚染を排除する（ADR-0015 の serving スケールゼロのみ上書き。probe 失敗 3 件がすべて偽陽性 = 可用性 97.71% は障害 0 件だった実測を根拠とする） |
| [0026](./0026-readyz-repository-variables-as-source-of-truth.md) | Accepted | `readyz-probe` の実行設定を必須 repository variables に一本化し、未設定・不正値を probe 前に fail-closed にする |
| [0027](./0027-frontend-azure-deployment-and-public-surface.md) | Proposed | frontend を Azure Container Apps へデプロイし、公開面を Easy Auth + BFF + backend internal ingress で固定する（`NEXT_PUBLIC_CHAT_API_KEY` の廃止・bootstrap 窓は fail-closed の apply 順序で塞ぐ） |
| [0028](./0028-chat-sse-response-contract.md) | Accepted | `POST /chat` を SSE 化し応答契約を固定する（event 文法・raw stream から wire contract への変換・`content_filter` の fail-closed 撤回契約・retry 境界。SLI threshold の数値は決めない。#183 / #184 の実測を反映して決定 5 の表を追記改訂: error field は単数形・複数形とも明示列挙して検査し、それ以外の未知 field は無視。ingress 240 秒はアイドル timeout と決着） |
