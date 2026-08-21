# ADR-0015: ephemeral 層（ACR + Container Apps）の設計 — 最小 SKU・スケールゼロ・egress 経路・イメージタグ方針

## ステータス

Proposed

（ACR pull の認証方式 1 点が未確定のため。他の決定はレビュー・マージをもって Accepted 化する）

## 日付

2026-08-21

## 決定内容

walking skeleton（[day3-5-execution-plan.md §3-2](../operations/day3-5-execution-plan.md)）用の `terraform/ephemeral/` を次の構成で作る。この層は毎日 destroy / apply を繰り返す（同 §3-6 / §8）。

| リソース | 名前（ADR-0013 準拠） | 主要な設計値 |
| --- | --- | --- |
| ACR | `felisaichatbotacrdev` | **Basic** / admin user 無効（下記・未確定事項参照） |
| Log Analytics workspace | `log-felisaichatbot-dev` | PerGB2018 / 保持 **30 日（最小）** / 日次取込上限 **1 GB** |
| Container Apps Environment | `cae-felisaichatbot-dev` | **VNet 統合なし**（既定の Azure ネットワーク） |
| Container App | `ca-felisaichatbot-dev` | **min_replicas 0（スケールゼロ）** / max 1 / 0.25 vCPU / 0.5 GiB / 外部 ingress |
| PostgreSQL firewall rule | `aca-egress-<ip>` | Container App の `outbound_ip_addresses` を 1 IP ずつ許可（persistent 層のサーバーへ data source 参照） |

イメージは **hello-world から始めて backend に差し替える 2 段階**とし、タグは **git commit SHA 由来の不変タグ（`latest` 禁止）** を使う。

**未確定（本 ADR で確定させない）**: Container App が ACR から pull する際の認証方式。選択肢とトレードオフは「検討した選択肢 6」に整理し、ユーザー判断を待つ。確定までこの層の apply は行わない。

## 背景

- Day 3 の walking skeleton は「hello world を ACR → Container Apps で動かし、`/readyz`（DB へ `SELECT 1`）まで通す」こと（計画書 §3-2 が正本）
- コスト方針は「使っていない時間帯は課金を止める」（計画書 §8）。PostgreSQL は stop、ephemeral 層は destroy で対応する
- CI 用 service principal は `rg-felisaichatbot-dev-tf` への Contributor と tfstate への Storage Blob Data Contributor しか持たず、**`Microsoft.Authorization/roleAssignments/write` を持たない**（ADR-0012）。Terraform でロール割当（AcrPull）を作ると CI からの apply が権限不足で失敗する
- 本 ADR の単価はすべて Azure Retail Prices API（認証不要の公開 API <https://prices.azure.com/api/retail/prices> 、`armRegionName eq 'japaneast'` / `type eq 'Consumption'`）で 2026-08-21 に実測した。通貨は USD

## 検討した選択肢

### 1. ACR の SKU

- **(a) Basic（採択）**: 0.1666 USD/日。included storage 10 GiB。walking skeleton のイメージは hello-world + backend の 2 種・数百 MB 規模で収まる
- (b) Standard: 0.6666 USD/日（Basic の 4 倍）。増えるのは storage（100 GiB）と webhook 数等で、本プロジェクトに使い道がない。却下

### 2. Container App のスケール設定

- **(a) min_replicas 0 / max_replicas 1（採択）**: 無リクエスト時にレプリカ 0 へ縮退し、コンピュート課金が止まる。コールドスタート遅延は walking skeleton の検証（`/readyz` を叩いて 200 を見る）に影響しない
- (b) min_replicas 1: 常駐分の active/idle 課金が 24 時間発生する。「使っていないときに課金を止める」方針（計画書 §8）に反する。却下

### 3. Log Analytics の保持と取込上限

- **(a) 保持 30 日（設定可能な最小値）+ 日次取込上限 1 GB（採択）**: Analytics テーブルの interactive retention は 31 日まで取込料金に含まれるため、30 日設定なら保持コストは 0（出典: <https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-retention-configure> "Keeping data in interactive retention for 31 days or less is included in the ingestion price"）。取込は 3.34 USD/GB（実測単価）のため、日次上限 1 GB で暴走時の損失を最大 3.34 USD/日に固定する
- (b) 既定のまま（上限なし）: ログ暴走（クラッシュループ等）時に取込課金が青天井になる。却下
- (c) Log Analytics を作らない: Container Apps Environment はログ出力先を要求し、デバッグ（コンテナ起動失敗・DB 接続失敗の切り分け）に console ログが必須。却下

### 4. Container Apps → PostgreSQL の接続経路

- **(a) VNet 統合なし + `outbound_ip_addresses` を firewall rule で許可（採択）**: 追加リソース・追加コストなし。Terraform は `azurerm_container_app` がエクスポートする `outbound_ip_addresses`（azurerm 5.1.0 の provider スキーマで存在を確認済み・2026-08-21）を `azurerm_postgresql_flexible_server_firewall_rule` の for_each に流すだけ
  - **既知の不確実性**: この outbound IP は**静的保証がない**。「Outbound IPs might change over time.」（出典: <https://learn.microsoft.com/en-us/azure/container-apps/networking> の Ports and IP addresses 節、2026-08-21 確認）。静的 egress（NAT Gateway）は workload profiles 環境 + VNet 統合が前提で、本構成では使えない（同出典）
  - **リスク受容の根拠**: この層は毎日 destroy / apply され、rule は毎朝その時点の実 IP で作り直される。IP 変更に晒される窓は最長でも当日の稼働時間帯だけで、変わった場合も `/readyz` の失敗で即検知でき、`terraform apply` 再実行で追随できる
- (b) VNet 統合 + NAT Gateway で静的 egress: 計画書 §9 の「やらないこと」（VNet 統合は検証目的に寄与せず作業量だけ増える）に反する。subnet 設計・NAT Gateway・Public IP（Standard 静的 IP 0.005 USD/時 = 0.12 USD/日は実測）が増える。NAT Gateway 本体の japaneast 単価は Retail Prices API で該当メーターを特定できず**未取得**。採るなら Day 3 の作業から何かを削る必要があるが、削ってまで得るものがない。却下
- (c) firewall を広く開ける（`0.0.0.0` の特殊 rule = Azure 内サービス全許可）: 作業量最小だが、他テナントを含む Azure 上の全発信元に開く。恒久採用はしない。**(a) の IP 変動が実際に頻発して検証を阻害した場合の一時的な逃げ道**としてのみ位置づける（使ったら証跡に記録し、当日の teardown で消す）

### 5. イメージと 2 段階デプロイ

- **(a) hello-world → backend の 2 段階（採択）**: bootstrap.md「Day 3 の方針」方針1 が正本（「hello world だけのコンテナを ACR に push し…経路が通ってから本体を載せる」）。デプロイ経路の問題（OIDC・push 権限・ingress・ポート）をアプリの複雑さ（DB 接続・TLS・環境変数）から切り離して潰す。`/readyz` は backend のエンドポイントなので、最終検証（`SELECT 1`）は backend への差し替え後に行う。Terraform 側はイメージを変数（`container_image`）にしてあり、差し替えは変数値の変更だけで済む。なお backend の Dockerfile は未作成（2026-08-21 時点でリポジトリに Dockerfile が存在しないことを確認）。Day 3 の CI 整備時に作る
- (b) 最初から backend を載せる: ビッグバン統合になり、計画書が明示的に避けている経路（bootstrap.md 方針1 の狙い欄）。却下

- タグ方針: **git commit SHA 由来の不変タグ（例 `sha-abc1234`）を使い、`latest` を使わない**。`latest` は「どのコードが動いているか」を state からもログからも特定できなくする。digest 固定（`@sha256:...`）は他リポジトリ（terraform-hannibal 等）で CI 基盤イメージに採用している方針だが、ここでのデプロイ対象イメージは自分でビルドして push した直後の SHA タグを参照するため、タグ改竄への防御を足す意味が薄く、5 日間プロジェクトには過剰と判断して見送る。Terraform には `:latest` を拒否する validation を入れた

### 6. ACR pull の認証方式（未確定・ユーザー判断待ち）

前提: マネージド ID で pull するには ID への **AcrPull ロール割当**が必要だが、CI 用 SP は `Microsoft.Authorization/roleAssignments/write` を持たない（ADR-0012 で RBAC Administrator を意図的に不付与）。Terraform にロール割当を書くと **CI からの apply は必ず失敗**する（ローカルの Owner 実行なら通ってしまい、CI と挙動が割れるのがなお悪い）。

- (a) ACR の admin user を有効化し username/password で pull: 権限問題は消えるが、リポジトリ全体で積んできた least privilege の設計（ADR-0012）と不整合。資格情報が tfstate に平文で入る
- (b) **user-assigned managed identity `id-felisaichatbot-dev` + AcrPull を手動作成し Terraform 管理外にする（起案者の推奨）**: 手動作成は 1 回きり（`az identity create` + `az role assignment create`）。ロール割当のスコープを ACR 個体ではなく **RG `rg-felisaichatbot-dev-tf`** にすれば、ACR が毎日 destroy / 再作成されてもロール割当は生き残り、毎朝の再設定が不要。管理外リソース台帳へ 2 エントリ追記する。ADR-0012 の決定（SP の権限 2 件のみ）は不変
- (c) CI 用 SP に条件付き・スコープ限定の RBAC 権限を追加: ADR-0012 の決定の一部変更。割当可能ロールを AcrPull に限る condition を付ければ昇格リスクは小さいが、5 日間プロジェクトで得るもの（ロール割当の Terraform 管理）に対して ADR 改定 + 権限追加の作業が重い

現時点の Terraform コードは (b) を仮置き（identity を data source 参照）している。(a)/(c) 採択時は該当箇所（`data "azurerm_user_assigned_identity"` / `identity` / `registry` ブロック）を差し替える。

### 7. Terraform 上の実装形（補足決定）

- persistent 層のサーバーへは `data "azurerm_postgresql_flexible_server"` で参照する（`terraform_remote_state` で persistent の state を読まない。state には DB 管理者パスワード等の sensitive 値が入っており、読み取り面を増やさない）
- firewall rule の for_each が apply 後にしか確定しない `outbound_ip_addresses` に依存するため、**初回構築は 2 段階 apply**（`-target=azurerm_container_app.main` → 全体 apply）とする。手順は `terraform/ephemeral/main.tf` 冒頭コメントに明記

## 採択理由（コスト実測）

単価（Retail Prices API、japaneast、Consumption、2026-08-21 取得。生データは PR の検証記録参照）:

| 項目 | 実測単価 | 24 時間あたり見込み |
| --- | --- | --- |
| ACR Basic Registry Unit | 0.1666 USD/日 | **0.1666 USD** |
| ACR Data Stored | 0.1 USD/GB/月 | 0（included 10 GiB 内） |
| ACA Standard vCPU Active Usage | 0.000024 USD/vCPU 秒 | 0.0864 USD（前提: 0.25 vCPU × 4 時間稼働） |
| ACA Standard Memory Active Usage | 0.000003 USD/GiB 秒 | 0.0216 USD（前提: 0.5 GiB × 4 時間稼働） |
| ACA Standard Requests | 0.4 USD/100 万件 | ~0（検証の手動リクエストのみ） |
| Log Analytics 取込（PerGB2018） | 3.34 USD/GB | 未実測（上限ガードで最大 3.34 USD。実測は Day 3） |
| Log Analytics 保持 | 0.15 USD/GB/月（31 日超過分） | 0（保持 30 日設定） |

- ACA の「4 時間稼働」は検証作業中に replica 1 が立ち続ける保守的な仮定。スケールゼロが効けばさらに下がる。また Consumption には **月あたり 180,000 vCPU 秒 + 360,000 GiB 秒 + 200 万リクエストの無料枠**があり（出典: <https://azure.microsoft.com/en-us/pricing/details/container-apps/> 、2026-08-21 確認）、上記の想定使用量（3,600 vCPU 秒/日）は枠内に収まるため、**実請求見込みは ACA 分 ≒ 0 USD**
- 合計（24 時間・ログ 0.1 GB/日と仮定した場合）: **約 0.5 USD/日、うち確定的な固定費は ACR の 0.1666 USD/日のみ**。Day 3〜5 総額見込み約 3.3 USD（計画書）を崩さない

## 影響

- `terraform/ephemeral/`: backend.tf / provider.tf / variables.tf / main.tf / outputs.tf を新設（state key は `ephemeral/terraform.tfstate`）
- `.github/workflows/terraform-checks.yml`: fmt / validate の対象に `terraform/ephemeral` を追加
- ACR 認証方式の確定後: (b) なら [terraform-unmanaged-resources.md](../operations/terraform-unmanaged-resources.md) に identity とロール割当を追記する PR を出す。(a)/(c) なら本 ADR を更新し、(c) の場合は ADR-0012 を上書きする ADR を別に書く
- 本層の apply は認証方式確定まで行わない（CI のデプロイ workflow 整備も同様に保留）

## 関連

- [ADR-0012](./0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — CI 用 SP の権限 2 件のみ（AcrPull 割当を Terraform で作れない制約の源）
- [ADR-0013](./0013-azure-resource-naming-convention.md) — 本層の全リソース名の予約元
- [ADR-0014](./0014-keep-azure-openai-out-of-terraform.md) — 「管理外に置く」判断の先行例（選択肢 6-(b) と同型）
- [day3-5-execution-plan.md](../operations/day3-5-execution-plan.md) §3-2（walking skeleton 正本）/ §3-6（毎日の destroy）/ §8（コスト見張り）/ §9（VNet 統合をやらない）
- [bootstrap.md](../operations/bootstrap.md) 「Day 3 の方針」方針1（hello-world 先行の根拠）
- Issue: #70
