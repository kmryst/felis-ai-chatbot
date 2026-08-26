# felis-ai-chatbot

Azure Database for PostgreSQL Flexible Server の **Backup / Restore (PITR) / Maintenance / Monitoring / HA** を、
自分で設計・実装し、実測で検証している個人開発リポジトリ。
DevOps / SRE / Platform Engineering 向けのポートフォリオです。

## 採用担当者向けサマリー（30秒）

- **対象ロール**: DevOps Engineer / SRE / Platform Engineer / インフラエンジニア
- **主成果物**: 「Azure 上に AI チャットボットを作ったこと」では**ありません**。
  **PostgreSQL の Backup / PITR / Maintenance / Monitoring / HA を設計・実行し、
  実測値と失敗をそのまま記録に残したこと**が成果物です
- **題材**: pgvector RAG チャットボット。運用対象の PostgreSQL に現実的な読み書きを流すためのワークロードです
- **基盤構成**: Terraform で PostgreSQL Flexible Server / Container Apps / ACR / VNet + Private DNS /
  Log Analytics を管理。DB は private access で、対話経路は VNet 内の ops コンテナに一本化
- **可観測性**: `/readyz` の外形監視（5 分間隔の probe）と、DB 内の観測 3 系列（1 分 / 5 分 / 1 時間）を継続採取。
  可用性と freshness を good events / total events の比として扱い、系列別に判定
- **変更管理**: Issue / Branch / PR / 必須ラベル / CI ガードレール。
  AI Agent が関与した変更も、意図・差分・検証結果を追える履歴として残す
- **設計判断**: ADR 20 本・約 2,000 行。撤回した判断・引き直した理由も削除せず残す（[docs/adr/](./docs/adr/README.md)）
- **production readiness**: 本番運用に足りていないものを 1 枚に集約し、理由と追跡先つきで公開
  （[docs/production-readiness.md](./docs/production-readiness.md)）
- **コスト設計**: 無料枠と検証ウィンドウを前提に、HA / General Purpose のような高コスト構成は常設せず、
  「測ったら戻す」運用にしている

## このプロジェクトの起点

面談で「実務で DB のバックアップ・メンテナンスをやったことがありますか」と訊かれて、答えられませんでした。
実務では担当していません。だから **Azure 上に自分で構築して、
Backup / PITR / Maintenance / Monitoring / HA を設計・実行・実測しました。これはその記録です。**

「実務でやった」とは書きません。立て付けは
「実務では担当していない。訊かれて答えられなかったので、自分で構築して一通りやった。これがその記録」で固定しています。
勝負どころは追い質問（リストアは試したか / 保持期間はどう決めたか / メンテナンス中に止まったか / vacuum は見ているか）で、
それに実測で答えるためにこのリポジトリがあります。

立て付けの正本は [day3-5-execution-plan.md §0](./docs/operations/day3-5-execution-plan.md)、
進行中の計画は [credit-window-execution-plan.md](./docs/operations/credit-window-execution-plan.md) です。

## いま何を測っていて、何がまだ測れていないか

**このプロジェクトは進行中です。** 下表は 2026-08-26 時点の状態で、
**実測済みと未実測を厳密に分けています。未実測の項目には数値を書きません。**

| 項目 | 状態 | 実測値 / 予定 |
| --- | --- | --- |
| private access（VNet 統合）への切替 | **実測済み**（2026-08-22） | apply は 7 added / 0 changed / 3 destroyed。VNet 内経路の `/readyz` 200 と、作業端末から DB FQDN が DNS 解決すらできないこと（到達不能）の両方を実測 |
| バックアップの復旧ウィンドウの立ち上がり | **実測済み**（2026-08-21） | サーバー作成直後は `earliestRestoreDate` が `null`。Ready から数分内に初回スナップショット由来の値が入る遷移を実測 |
| バックアップ使用量の推移 | **実測済み**（進行中） | 1 時間の間に 10.4 MB → 1.33 GB のステップを観測。無料枠 32 GB に対し 4%。**ステップの周期が日次か週次かは未検証** |
| 低負荷ベースライン観測（フェーズ 1、72h） | **観測中** | T_obs_start 2026-08-23T08:16:19Z 起点、+72h で終了。3 系列を設計間隔で継続採取中。稼働率・レイテンシ分布の**最終値は完了後に確定** |
| 外形監視の実効稼働 | **実測済み** | scheduled run 132 回 / 期待 848 回 = **15.6%**（後述） |
| 障害通知の到達（意図的欠落試験） | **実測済み**（2026-08-23） | probe の run failure から **20 秒後**に GitHub 通知インボックスへ配送記録が生成された。**メール受信の実証ではありません** |
| autovacuum の自然発火 | **一部実測済み** | 1 行を毎分 UPDATE するテーブルで 22.6 時間に **26 回**発火（約 52 分周期）。INSERT-only テーブル側は発火 1 回のみで、傾向を語るには点数が足りない |
| WAL / DB サイズ / XID age の増加レート | **実測済み**（低負荷時） | WAL 約 5.2 MiB/日、DB サイズ約 +0.64 MiB/日、XID age 約 +13,200/日（22.63 時間の差分を線形換算） |
| PITR ドリル 1（RTO / RPO） | **未実測** | 2026-08-28 実施予定 |
| 高負荷観測（フェーズ 2a / Burstable B1ms） | **未実施** | 2026-08-29〜30 予定。bloat と vacuum の追いつきを負荷下で観測する |
| General Purpose へのスケール（ダウンタイム） | **未実測** | 2026-08-31〜09-01 予定 |
| ゾーン冗長 HA の failover（ダウンタイム） | **未実測** | 2026-08-31〜09-01 予定。計画 failover / 強制 failover の 2 種 |
| PITR ドリル 2（24 時間以上前への復元） | **未実測** | 2026-09-02 実施予定 |
| teardown | 未実施 | 2026-09-03〜04 予定 |

> **PITR の RTO も failover のダウンタイムも、この時点ではまだ 1 つも測っていません。**
> 「これから測る」と「測った」を混ぜないために、上表は項目ごとに状態を持たせています。
> 実測でき次第、この表と証跡を更新します。

## 実測から出てきた、設計に効く発見

数値と再現手順の正本は
[docs/verification/observation-phase1/observations.md](./docs/verification/observation-phase1/observations.md) です。

### 外形監視は、cron の宣言値どおりには動かない

`/readyz` の probe は `cron: "*/5 * * * *"` で回していますが、実際に起動した scheduled run は
**132 回 / 期待 848 回 = 15.6%** でした
（2026-08-23T07:21:18Z 〜 2026-08-26T06:03:17Z の 70.7 時間。
`gh run list -w readyz-probe.yml --limit 1000 --json event,createdAt` の `event == "schedule"` を数えた実測）。

意味するところは 2 つあります。

1. **SLI の分母を cron の宣言値で置いてはいけない。** 分母は「実際に起動した run」で数える必要がある
2. **freshness ゲートの検知遅延は、probe 間隔ではなく実効間隔で決まる。**
   宣言 5 分に対し、run と run の最大間隔は **98.8 分**（2026-08-24 時点の実測）だった

この事実自体を証跡として固定してあり、probe 側の条件は**観測期間中に変更していません**
（観測条件を変えると、それまでのベースラインが比較不能になるため）。

### そのほかの発見（§3-1 〜 §3-5）

| # | 発見 |
| --- | --- |
| [§3-1](./docs/verification/observation-phase1/observations.md) | cron Job を migration より先に作る apply 順序では、**初回の 1 回失敗が構造的に不可避**。「Job 失敗 0 件」を受け入れ条件に置くと必ず落ちる |
| §3-2 | 経過時間ベースの採取判定により、5 分系列の実間隔が **300 秒台と 360 秒台の 2 モードを行き来する**。名目 5 分に対し実効は約 5.6 分 |
| §3-3 | **SQL は完走しているのに execution は Failed** になる。`replicaTimeout` 55 秒での打ち切りで、exit code すら残らない。「job status」と「採取データの完全性」は別物 |
| §3-4 | `az containerapp job execution list` は履歴上限があり、**成功件数（= 分母）が切られる**。失敗率の分母には使えない |
| §3-5 | `gh run view --log` は **failure run に対して 0 バイトを返す**（success では取れる）。可用性 SLI の分子だけが黙って落ちる。REST の job logs 経由なら取得できる |

計画書の記載と実測が食い違った点は、直さずに
[§6 の食い違い一覧](./docs/verification/observation-phase1/observations.md)に残しています。
未検証のまま残っている項目も [§7](./docs/verification/observation-phase1/observations.md) に明示しています。

## 本番運用との差分（production readiness）

「本番でそのまま使えますか？」に対して
「使えません。差分はこれで、それぞれ理由と追跡先があります」と 1 枚で答えるためのドキュメントです。
production readiness review の考え方に沿って、ネットワーク境界 / 認証・secret / 可用性・DR /
監視・運用 / CI/CD / IaC カバレッジ / アプリケーションの 7 領域を横断で並べています。

各行は「現状」「なぜ現状こうなのか」「本番ならどうすべきか」「追跡先」だけを持ち、
追跡先が無い項目は「追跡先なし」と明記しています。

→ [docs/production-readiness.md](./docs/production-readiness.md)

## 設計判断（ADR）

トレードオフのある判断は ADR に残しています（20 本・約 2,000 行）。
**撤回した判断も削除せず、なぜ引き直したかを新しい ADR に書いて残す**方針です。

| ADR | 決定 |
| --- | --- |
| [0011](./docs/adr/0011-backup-retention-and-geo-redundancy.md) | バックアップ保持 7 日を作成時に確定（検証 3 日 < 復旧ウィンドウ 7 日）。長期保持は選択肢として検討し却下 |
| [0019](./docs/adr/0019-enable-geo-redundant-backup.md) | geo 冗長バックアップを有効化。無料枠の判明で「2 倍課金」の前提が崩れ、**作成時のみ設定可**という制約から cutover の再作成が最後の機会だった（0011 の該当部分を supersede） |
| [0017](./docs/adr/0017-no-nightly-stop-for-postgresql.md) | PostgreSQL を夜間 stop しない。停止中は新規バックアップが取得されないため、コスト根拠が消えた時点で実害だけが残る |
| [0018](./docs/adr/0018-postgresql-private-access-and-vnet-integration.md) | DB を private access（VNet 統合）で確定し、運用経路を VNet 内の ops コンテナに一本化 |
| [0012](./docs/adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) | CI 用 service principal の最小権限化と、Terraform 管理リソース専用 RG の分離 |
| [0016](./docs/adr/0016-log-analytics-workspace-in-persistent-layer.md) | Log Analytics workspace を ephemeral 層から persistent 層へ移し、毎日の destroy から監視ログを切り離す |
| [0020](./docs/adr/0020-credit-window-resource-strategy.md) | 実行計画を「課金を極力抑える」から「消費上限の内側で、時間をかけないと取得できない証跡を取り切る」へ組み替える |
| [0010](./docs/adr/0010-rag-wiring-and-hallucination-guard.md) | RAG を結線し、検索結果が閾値未満なら LLM を呼ばないガードをコードで担保 |

一覧と運用ルールは [docs/adr/README.md](./docs/adr/README.md) にあります。

## 変更管理と CI ガードレール

Issue / PR 駆動の開発フローと CI ガードレールが最初から有効です
（[idp-golden-path](https://github.com/kmryst/idp-golden-path) の service-baseline テンプレートから生成。
[ADR-0001](./docs/adr/0001-bootstrap-by-manual-skeleton-copy.md)）。

| 領域 | 実装 |
| --- | --- |
| Issue | `目的` / `対象` / `受け入れ条件` と `type` / `area` / `risk` / `cost` ラベルを必須化し、Issue Template Check で検査 |
| PR | Issue link と必須ラベル 4 種を PR Policy Check で検査。厳密運用の PR は rollback 欄を必須にする |
| Commit | Conventional Commits を Commitlint で強制 |
| Secret | Gitleaks Secret Scan |
| Docs | Markdown Lint |
| Toolchain | `.mise.toml` と workflow の pin の一致を Toolchain Version Check で検査 |
| Labels | `.github/labels.yml` を正本に Sync Labels workflow で同期 |

workflow の実体は idp-golden-path の reusable workflows をタグ固定 `@v1` で参照し、
更新は Dependabot の PR で取り込みます。
運用ルールの正本は [CONTRIBUTING.md](./CONTRIBUTING.md)、
AI Agent 向けの作業ルールは [CLAUDE.md](./CLAUDE.md) です。

```bash
# Issue 作成
./scripts/github/create-issue-with-labels.sh --title "短い要約" \
  --body-file docs/issue-templates/feature_request.md \
  --type type:feature --area area:app --risk risk:low --cost cost:none

# PR 作成（draft で作成される）
./scripts/github/create-pr-with-labels.sh --title "feat: 変更の要約" \
  --body-file /path/to/filled-pr-body.md --issue <issue番号> \
  --type type:feature --area area:app --risk risk:low --cost cost:none --base main
```

## 記録の作法

- **数値には必ず取得コマンドと取得時刻（UTC）を添える。** 再確認できなかったものは「未検証」と書き、断定しない
- **公式ドキュメントの記載は逐語で引用し、実測と突き合わせる。** 食い違ったら実測を残し、計画書の記載も消さない
- **失敗と誤りを消さない。** 見立てが外れた費目、初回に必ず落ちる Job、SLI 集計コマンドの欠陥は、
  そのまま証跡に残す

## ドキュメント

| ドキュメント | 内容 |
| --- | --- |
| [docs/production-readiness.md](./docs/production-readiness.md) | 本番運用との差分（横断の状態一覧。理由と追跡先つき） |
| [docs/adr/](./docs/adr/README.md) | 設計判断（ADR 20 本） |
| [docs/operations/day3-5-execution-plan.md](./docs/operations/day3-5-execution-plan.md) | Backup / PITR / Maintenance / HA / Monitoring の実行計画と判断基準 |
| [docs/operations/credit-window-execution-plan.md](./docs/operations/credit-window-execution-plan.md) | 進行中のフェーズ計画（フェーズ 1 / 2、PITR ドリル、teardown） |
| [docs/verification/observation-phase1/observations.md](./docs/verification/observation-phase1/observations.md) | フェーズ 1 の実測記録（構造的な発見・食い違い・未検証項目） |
| [docs/verification/vnet-cutover/observations.md](./docs/verification/vnet-cutover/observations.md) | VNet 統合 cutover の実測記録 |
| [docs/verification/restore-drill/observations.md](./docs/verification/restore-drill/observations.md) | バックアップ観測記録（PITR ドリルの前提） |
| [docs/operations/azure-resource-inventory.md](./docs/operations/azure-resource-inventory.md) | Azure リソース台帳（層・寿命・課金、Terraform 管理外リソース） |
| [docs/operations/bootstrap.md](./docs/operations/bootstrap.md) | Day 0 bootstrap の手順と検証証跡 |
| [docs/operations/branch-protection.md](./docs/operations/branch-protection.md) | main ブランチ保護の適用手順 |
| [docs/data-sources.md](./docs/data-sources.md) | 利用データソース一覧（気象庁ホームページ） |
| [docs/development/local-setup.md](./docs/development/local-setup.md) | ローカルで動かす手順（docker compose / alembic / FastAPI / Next.js / pytest） |

## ローカルで動かす

手順は [docs/development/local-setup.md](./docs/development/local-setup.md) にまとめています。

```bash
cp .env.example .env   # 初回のみ（.env はコミット禁止）
docker compose up -d   # pgvector 入り PostgreSQL 17
```

## 補足

本リポジトリは skeleton の手動コピーで立ち上げたため、Backstage TechDocs / Software Catalog 用ファイル
（`mkdocs.yml` / `catalog-info.yaml`）は含まれていません
（[ADR-0001](./docs/adr/0001-bootstrap-by-manual-skeleton-copy.md)）。
