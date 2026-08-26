# felis-ai-chatbot

pgvector による RAG chatbot（Next.js + FastAPI + PostgreSQL）を Azure 上に Terraform で構築しています。
成果物はアプリではなく、**その PostgreSQL の Backup / PITR / Maintenance / Monitoring / HA を
設定で終わらせずドリルとして実行し、実測値を証跡として残したこと**です。

## 対象ロールと、このリポジトリで示せること

- **対象ロール**: DevOps Engineer / SRE / Platform Engineer / インフラエンジニア
- **基盤**: Terraform で PostgreSQL Flexible Server / Container Apps / ACR / VNet + Private DNS /
  Log Analytics を管理。DB は private access で、運用経路は VNet 内の ops コンテナに一本化
- **可観測性**: `/readyz` の外形監視と、DB 内の観測 3 系列（1 分 / 5 分 / 1 時間）を継続採取。
  可用性と freshness を good events / total events の比として系列別に判定
- **変更管理**: Issue / Branch / PR / 必須ラベル / CI ガードレール。ルールは
  [CONTRIBUTING.md](./CONTRIBUTING.md)、AI Agent 向けの作業ルールは [CLAUDE.md](./CLAUDE.md)
- **公開している弱点**: 本番運用に足りていないものを理由と追跡先つきで 1 枚に集約
  （[docs/production-readiness.md](./docs/production-readiness.md)）

## 実測値

進行中のプロジェクトです。**未実測を先に並べています。**

| 項目 | 状態 |
| --- | --- |
| PITR ドリル（RTO / RPO） | **未実測** — 2026-08-28 実施予定 |
| ゾーン冗長 HA の failover ダウンタイム | **未実測** — 2026-08-31〜09-01 予定 |
| General Purpose へのスケールのダウンタイム | **未実測** — 2026-08-31〜09-01 予定 |
| 低負荷ベースライン観測（フェーズ 1、72h） | **完了** — 2026-08-23T08:16:19Z 起点の 72h を 2026-08-26T08:16:19Z に通過。稼働率・レイテンシ分布の最終値は採取後に確定 |
| 外形監視の実効 coverage | **実測済み** — scheduled run 132 回 ÷ 期待 848 回 = 15.6% |
| 障害通知の到達 | **実測済み** — probe の run failure から 20 秒後に、GitHub の通知インボックスへ配送記録が生成された（メール受信の実証ではない） |
| autovacuum の自然発火 | **実測済み** — 1 行を毎分 UPDATE するテーブルで 22.6 時間に 26 回（約 52 分周期） |
| private access（VNet 統合）への切替 | **実測済み** — VNet 内経路の `/readyz` 200 と、作業端末からの到達不能を両方確認 |

> PITR の RTO も failover のダウンタイムも、この時点ではまだ 1 つも測っていません。

## このプロジェクトの立て付け

実務では DB 運用を担当していません。カタログスペックや手順書の知識ではなく、
**自分で構築して実際に動かした実測値で答えられる状態**を作るために、
Azure 上に PostgreSQL を建てて Backup / PITR / Maintenance / Monitoring / HA を
設計・実行・記録しました。

「実務でやった」とは書きません。立て付けは
「実務では担当していない。だから自分で構築して一通りやった。これがその記録」で固定しています。
勝負どころは追い質問（リストアは試したか / 保持期間はどう決めたか /
メンテナンス中に止まったか / vacuum は見ているか）で、
それに実測で答えるためにこのリポジトリがあります。

## 実測から出た発見

数値と再現手順の正本は
[docs/verification/observation-phase1/observations.md](./docs/verification/observation-phase1/observations.md) です。

- **SQL は完走しているのに job execution は Failed になる。**
  `replicaTimeout` 55 秒での打ち切りで、exit code すら残りません。
  「job status」と「採取データの完全性」は別物として扱う必要があります
- **`gh run view --log` は failure run に対して 0 バイトを返す**（success では取得できる）。
  可用性 SLI の分子だけが黙って落ちます。REST の job logs 経由なら取得できます

## もっと見る

- [docs/production-readiness.md](./docs/production-readiness.md): 本番運用との差分（理由と追跡先つき）
- [docs/adr/README.md](./docs/adr/README.md): 設計判断（ADR）。撤回した判断も削除せず残しています
- [docs/verification/observation-phase1/observations.md](./docs/verification/observation-phase1/observations.md): フェーズ 1 の実測記録・食い違い・未検証項目
- [docs/operations/credit-window-execution-plan.md](./docs/operations/credit-window-execution-plan.md): 進行中のフェーズ計画（PITR ドリル / HA / teardown）

## ローカルで動かす

手順は [docs/development/local-setup.md](./docs/development/local-setup.md) にまとめています
（`cp .env.example .env` のあと `docker compose up -d`）。
