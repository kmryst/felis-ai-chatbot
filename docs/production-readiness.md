# 本番運用との差分（production readiness）

本書は、このプロジェクトが**本番運用の水準に対して何が足りていないか**を横断で 1 枚にまとめたものです。

## 位置づけ

- このリポジトリは**個人開発のポートフォリオ**であり、本番運用を想定した完成物ではない
- **主成果物は PostgreSQL の Backup / PITR / Maintenance の設計・実施・記録**（[day3-5-execution-plan.md §0](./operations/day3-5-execution-plan.md)）であり、**それ以外は意図的にスコープ外**にしている
- 本書は、足りていないことを隠さず、**理由と追跡先とともに提示する**ためのドキュメントである。「本番でそのまま使えますか？」に対して「使えません。差分はこれで、それぞれ理由と追跡先があります」と 1 枚で答えられる状態を作る

## 既存ドキュメントとの役割分担

| ドキュメント | 役割 |
| --- | --- |
| [azure-resource-inventory.md](./operations/azure-resource-inventory.md) | いま何があるか（層・寿命・課金） |
| [day3-5-execution-plan.md](./operations/day3-5-execution-plan.md) | これから何をやるか（Day 3〜5 の手順） |
| [docs/adr/](./adr/README.md) | なぜそう決めたか（個別の判断） |
| **本書** | **本番との差分は何か（横断の状態一覧）** |

本書の各行は「現状」「なぜ現状こうなのか（1 行）」「本番ならどうすべきか」「追跡先」だけを持つ。**事実の詳細（数値・手順・出典）は追跡先が正本**であり、本書には書かない。同じ事実を 2 箇所に書くと必ず片方が腐る（管理外リソース台帳を全リソース台帳へ統合した経緯 #76 と同じ論点）。追跡先が無い項目は「**追跡先なし**」と明記する。

## 差分一覧

### 1. ネットワーク境界

| 項目 | 現状 | なぜ現状こうなのか | 本番なら | 追跡先 |
| --- | --- | --- | --- | --- |
| DB のネットワーク境界 | private access（VNet 統合）を**実機に適用済み**（2026-08-22 ステップ A〜C 完了。VNet 内経路の `/readyz` 200 と、作業端末から DB FQDN が DNS 解決すらできないこと（到達不能）の両方を実測。DB への対話経路は ops コンテナ経由のみ = [実測記録](./verification/vnet-cutover/observations.md)） | 当初の public access + firewall は walking skeleton 開通までの暫定で、egress IP の変動が実測で確認されたため確定構成へ引き上げた | private access（この移行の方向そのもの） | [ADR-0018](./adr/0018-postgresql-private-access-and-vnet-integration.md) / Issue #81（CLOSED） / [vnet-integration-cutover.md](./operations/vnet-integration-cutover.md) |
| tfstate のネットワーク境界 | RBAC のみ。公開ネットワークから到達可 | tfstate backend を Day 0 に最短で確立し、主成果物（PITR / Maintenance）の実測を優先した | ネットワーク境界（selected networks / Private Endpoint）+ 共有アクセスキー無効化 | **Issue #87** |
| `/chat` の公開面 | 外部 ingress を認証・レート制限なしで公開 | 検証経路（`/readyz` を外部から叩く）の確保が目的で、認証・流量制御は 5 日間のスコープ外 | 認証（少なくとも API キー / IP 制限）+ レート制限。LLM 課金を伴うエンドポイントを匿名公開しない | **追跡先なし**（本書が初出） |

### 2. 認証・シークレット

| 項目 | 現状 | なぜ現状こうなのか | 本番なら | 追跡先 |
| --- | --- | --- | --- | --- |
| DB 認証 | パスワード認証のまま（接続文字列は Container Apps の secret） | ネットワーク方式と違い後から追加できるため、PITR / Maintenance の実測が終わるまで触らない | Microsoft Entra 認証 + マネージド ID（鍵を隠すより無くす） | **Issue #86** |
| アプリ用 DB ユーザー | 専用の最小権限ロールがなく、管理者ユーザーの DSN を共用 | walking skeleton の最短経路を優先し、ロール設計は主成果物の外に置いた | アプリ専用の最小権限ロールと管理者の分離 | **追跡先なし**（#86 のマネージド ID 化と同時に設計するのが自然） |
| Azure OpenAI の認証 | API キー（`.env` / 環境変数のみ。コミット禁止） | Day 0 の可否判定で疎通を最優先し、マネージド ID 化は「Day 3 で検討」のまま未実施 | マネージド ID によるキーレス認証 | [ADR-0009](./adr/0009-azure-openai-as-llm-provider.md)（検討予告のみ。**Issue なし**） |
| Key Vault | 未使用（secret は Container Apps secret + `TF_VAR_*` 環境変数） | Day 3〜5 のスコープに Key Vault を要する要件がなかった | Key Vault への集約とローテーション運用 | [bootstrap.md §5-4 補足](./operations/bootstrap.md)（判断の記録のみ。**Issue なし**） |
| tfstate 内の平文 secret | DB 管理者パスワード等が state に平文で入る（Terraform の仕様） | 到達できる主体を実行者本人と CI 用 SP の 2 者に限定して受容した | 到達面の最小化（#87）に加え、そもそも secret が state に入らない認証方式（#86）へ | [台帳 §B-5](./operations/azure-resource-inventory.md) / Issue #86 / #87 |

### 3. 可用性・冗長・DR

| 項目 | 現状 | なぜ現状こうなのか | 本番なら | 追跡先 |
| --- | --- | --- | --- | --- |
| HA / 冗長構成 | 常設では無し。Day 5 に数時間だけ検証 | HA（GP ×2 台）の常設は課金が大きく、検証目的はフェイルオーバーの実測で足りる | 要件に応じたゾーン冗長 HA の常設 | [計画書 §5](./operations/day3-5-execution-plan.md) / ADR は Day 5 で作成予定 |
| geo 冗長バックアップ | 有効へ確定（コード反映済み。実機反映は cutover の apply 時）。ただし geo リストアの手順整備・演習は未実施 | 無料枠の判明で 2 倍課金の前提が崩れ、作成時のみ設定可の制約を cutover の再作成で解消した。geo リストアは PITR 不可・RPO 最大 1 時間で主成果物に寄与しないため演習はスコープ外 | DR 要件に基づく geo リストア手順（ペアリージョン側 VNet 含む）の整備と定期演習 | [ADR-0019](./adr/0019-enable-geo-redundant-backup.md) / [ADR-0011](./adr/0011-backup-retention-and-geo-redundancy.md) |
| 長期保持（LTR） | 未使用（保持は 7 日のみ） | 要件（検証 3 日）< 復旧ウィンドウ（7 日）で、延長は無料枠超過リスクを増やすだけ | 保持要件（監査・コンプライアンス）に応じた LTR | [ADR-0011](./adr/0011-backup-retention-and-geo-redundancy.md)（選択肢 4 で却下） / [計画書 §9](./operations/day3-5-execution-plan.md) |
| 読み取りレプリカ | 無し | 読み取り負荷分散・参照系分離の要件がない | 負荷・DR 要件に応じたレプリカ設計 | [計画書 §9](./operations/day3-5-execution-plan.md) |
| リージョン構成 | japaneast 単一。ただし chat 推論（GlobalStandard SKU）のみリージョンを跨ぎ得る | 無料試用サブスクリプションでは japaneast の Standard 系 chat クォータが取れなかった | データ所在要件に応じ Standard SKU へ切替（コード変更不要）。DB / アプリのマルチリージョンは DR 要件次第 | [ADR-0009](./adr/0009-azure-openai-as-llm-provider.md) |

### 4. 監視・運用

| 項目 | 現状 | なぜ現状こうなのか | 本番なら | 追跡先 |
| --- | --- | --- | --- | --- |
| 監視・アラート | 無し（Log Analytics 基盤と、指標・閾値根拠の表のみ） | Monitoring は面談で名指しされておらず、**時間不足なら削る筆頭**と計画に明記されている | メトリックアラート + 通知経路 + 初動 Runbook | [計画書 §7 / §1-2](./operations/day3-5-execution-plan.md) |
| コスト監視 | 手動（CLI での残高・リソース確認を終業時に実施） | 5 日間の検証では日次の手動見張りで足りる | Budget + コストアラートによる自動検知 | [計画書 §8](./operations/day3-5-execution-plan.md)（手動手順のみ。**Issue なし**） |
| リストア試験の継続性 | PITR ドリルは Day 4 の単発実測（定期・自動化なし） | 目的が「設計・実行した記録」であり、継続運用のフェーズがない | 定期リストア試験のスケジュール化と演習記録 | [計画書 §4](./operations/day3-5-execution-plan.md) |
| LLM モデルの更改 | chat モデルは lifecycleStatus Legacy（廃止期限あり）。更改プロセスなし | 5 日間の題材としては現行モデルで十分 | モデルライフサイクルの追跡と更改計画 | [ADR-0014](./adr/0014-keep-azure-openai-out-of-terraform.md)（「モデルの寿命」節） |

### 5. CI/CD・変更管理

| 項目 | 現状 | なぜ現状こうなのか | 本番なら | 追跡先 |
| --- | --- | --- | --- | --- |
| CI からのデプロイ | OIDC は構築済みだが**一度も通していない**（apply はすべてローカルの Owner 実行） | ネットワーク構成の確定（#81）後に通すほうが手戻りがないと判断した | CI 経由のみのデプロイと、その動作実証 | **Issue #82** |
| PR 時の `terraform plan` | 無し（PR 用 federated credential も意図的に未登録） | 使い道のない権限経路を先に開けない（least privilege） | PR で plan を提示しレビューする運用 | [ADR-0012](./adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md)（実装時に上書き ADR。**Issue なし**） |
| コードレビュー | required approving reviews は 0 | 単独開発で承認者が存在しない | 1 名以上の必須レビュー | [branch-protection.md](./operations/branch-protection.md)（**Issue なし**） |
| コンテナイメージの固定 | git SHA 由来の不変タグまで（digest 固定は見送り） | 自分でビルドして push した直後のタグを参照するため、タグ改竄への防御を足す実益が薄い | digest 固定または署名検証 | [ADR-0015](./adr/0015-ephemeral-layer-acr-container-apps-design.md)（選択肢 5） |
| マイグレーション適用 | Manual Job を人が起動（デプロイパイプライン未組込・自動リトライなし） | スキーマ変更の再試行は人間が状態を確認してから行う運用を選んだ | パイプラインへの組込とロールバック方針の自動化 | [ADR-0018](./adr/0018-postgresql-private-access-and-vnet-integration.md) / Issue #82 |
| 依存更新 | typescript のメジャー更新を一時 ignore 中 | 上流（typescript-eslint）の対応待ちで、グループ PR の巻き添え fail を止めるため | 上流対応後に ignore を解除 | **Issue #28** |

### 6. 構成管理（IaC のカバレッジ）

| 項目 | 現状 | なぜ現状こうなのか | 本番なら | 追跡先 |
| --- | --- | --- | --- | --- |
| Azure OpenAI の構成管理 | Terraform 管理外（drift 検出は台帳の読み取りコマンドで代替） | import の利得が主成果物に見合わず、管理下に入れると誤 destroy が purge まで進む事故経路が増える | IaC 管理下へ（安全装置と手順は ADR に固定済み） | [ADR-0014](./adr/0014-keep-azure-openai-out-of-terraform.md) / [台帳 §B-1](./operations/azure-resource-inventory.md) |
| 管理外リソース 9 件 | OIDC アプリ / RG / tfstate Storage / マネージド ID / ロール割当等が手動管理 | 鶏と卵（Terraform の足場）・権限の器・据え置き判断のいずれかで、台帳 + 読み取り確認コマンドを差分検出の代替とした | bootstrap 層も別 state で IaC 化するか、台帳運用を継続的に検証する | [台帳 §B](./operations/azure-resource-inventory.md) / [ADR-0012](./adr/0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) / [ADR-0015](./adr/0015-ephemeral-layer-acr-container-apps-design.md) |
| リソースプロバイダー登録 | 手動側の前提作業（CI の SP はサブスクリプションスコープの登録権限を持たない） | RG スコープ Contributor という最小権限の代償として受容し、手動登録を運用として固定した | 権限分掌の明文化（platform チーム側の作業として定義）または事前登録の自動化 | [台帳「リソースプロバイダー登録」節](./operations/azure-resource-inventory.md) / Issue #82 |
| 環境分離 | dev のみ（staging / prod なし） | 検証プロジェクトで環境昇格の要件がない | 環境ごとの分離（RG / state / 変数）とプロモーションフロー | **追跡先なし** |

### 7. アプリケーション（RAG / チャット）

| 項目 | 現状 | なぜ現状こうなのか | 本番なら | 追跡先 |
| --- | --- | --- | --- | --- |
| 数値質問への RAG 構造 | 数値はベクトル検索では原理的に到達できず、`object_properties` 全件の常時併載で補っている。類似度閾値は現データ規模の実測分布に依存する | 5 日制約で entity 抽出等の複雑な検索設計を避けた最小実装を選んだ | データ規模に応じた検索設計（ハイブリッド検索・絞り込み）と、データ追加時の閾値再測定の運用化 | [ADR-0010](./adr/0010-rag-wiring-and-hallucination-guard.md) |
| LLM retry の既定値 | 実測に基づかない一般的な初期値のまま | 提供元確定前の初期値で、実運用でレート制限に当たっていない | 実 API のレート制限仕様・実測に基づく調整 | [ADR-0004](./adr/0004-stub-llm-and-no-llm-in-ci.md)（「未確定・要レビュー」） / [ADR-0009](./adr/0009-azure-openai-as-llm-provider.md) |
| フロントエンドの配信 | Azure 上に未デプロイ（ローカル開発のみ。Container Apps で動くのは backend のみ） | walking skeleton の検証は `/readyz` / `/chat` で足り、UI の配信は主成果物に寄与しない | 静的ホスティング / CDN 等での配信と CORS / ドメイン設計 | **追跡先なし** |

## 本書の更新ルール

- 差分を解消した・新しく作った場合は、**同じ PR で本書の該当行を更新する**（台帳と同じ運用）
- 「追跡先なし」の項目に着手する場合は、先に Issue を起票して本書の追跡先を埋めてから進める
