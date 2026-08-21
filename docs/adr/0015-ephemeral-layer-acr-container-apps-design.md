# ADR-0015: ephemeral 層（ACR + Container Apps）の設計 — 最小 SKU・スケールゼロ・egress 経路・イメージタグ方針

## ステータス

Accepted

（起案時に未確定だった ACR pull の認証方式は、2026-08-21 のユーザー判断で選択肢 6-(b) に確定した）

（**Log Analytics workspace の配置（ephemeral 層）のみ [ADR-0016](./0016-log-analytics-workspace-in-persistent-layer.md) により persistent 層へ変更された**。設定値（PerGB2018 / 保持 30 日 / 日次取込上限 1 GB）と他の決定はすべて引き続き有効）

## 日付

2026-08-21

## 決定内容

walking skeleton（[day3-5-execution-plan.md §3-2](../operations/day3-5-execution-plan.md)）用の `terraform/ephemeral/` を次の構成で作る。この層は毎日 destroy / apply を繰り返す（同 §3-6 / §8）。

| リソース | 名前（ADR-0013 準拠） | 主要な設計値 |
| --- | --- | --- |
| ACR | `felisaichatbotacrdev` | **Basic** / admin user 無効（pull はマネージド ID。選択肢 6） |
| Log Analytics workspace | `log-felisaichatbot-dev` | PerGB2018 / 保持 **30 日（最小）** / 日次取込上限 **1 GB** |
| Container Apps Environment | `cae-felisaichatbot-dev` | **VNet 統合なし**（既定の Azure ネットワーク） |
| Container App | `ca-felisaichatbot-dev` | **min_replicas 0（スケールゼロ）** / max 1 / 0.25 vCPU / 0.5 GiB / 外部 ingress |
| PostgreSQL firewall rule | `aca-egress-<ip>` | Container App の `outbound_ip_addresses` を 1 IP ずつ許可（persistent 層のサーバーへ data source 参照） |

イメージは **hello-world から始めて backend に差し替える 2 段階**とし、タグは **git commit SHA 由来の不変タグ（`latest` 禁止）** を使う。

Container App が ACR から pull する際の認証は、**user-assigned managed identity `id-felisaichatbot-dev` + AcrPull ロール割当（スコープは RG `rg-felisaichatbot-dev-tf`）** で行う。**ID とロール割当はどちらも Terraform 管理外（手動作成 + [管理外リソース台帳](../operations/azure-resource-inventory.md) #8 / #9）**、ID を Container App に紐付ける記述は Terraform（data source 参照）が持つ。トレードオフと採択理由は「検討した選択肢 6」。ID とロール割当が手動作成されるまで、この層の apply は行わない。

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

### 6. ACR pull の認証方式（2026-08-21 ユーザー判断で (b) に確定）

前提: マネージド ID で pull するには ID への **AcrPull ロール割当**が必要だが、CI 用 SP は `Microsoft.Authorization/roleAssignments/write` を持たない（ADR-0012 で RBAC Administrator を意図的に不付与）。Terraform にロール割当を書くと **CI からの apply は必ず失敗**する（ローカルの Owner 実行なら通ってしまい、CI と挙動が割れるのがなお悪い）。

誤読を防ぐための整理: **3 案のうち「RBAC を使わない」のは (a) だけ**である。(b) と (c) の認証はどちらも同じ「マネージド ID + AcrPull ロール割当」（= RBAC）であり、両者の違いは**そのロール割当を誰が・どの管理下で払い出すか**（手動・Terraform 管理外か、CI の Terraform 管理下か）でしかない。(b) の採択は「RBAC を諦めた」のではなく、「RBAC の払い出しを Terraform の外に置いた」である。

- (a) ACR の admin user を有効化し username/password で pull（**却下**）: ロール割当が不要になるため権限問題は消えるが、admin user は **ACR 単位の共有パスワードで、pull した主体を追跡できない**。パスワードのローテーションが運用負荷として残り、資格情報が tfstate に平文で載る（state の sensitive 値の扱いは <https://developer.hashicorp.com/terraform/language/manage-sensitive-data> ）。3 案で唯一 RBAC を使わない選択であり、リポジトリ全体で積んできた最小権限の一貫性（ADR-0012）を壊す。Microsoft 自身も admin user を「主に単一ユーザーによるテスト用途」と位置づけ、複数ユーザーでの共有を非推奨としている（出典: <https://learn.microsoft.com/en-us/azure/container-registry/container-registry-authentication> の Admin account 節、2026-08-21 確認）
- **(b) user-assigned managed identity `id-felisaichatbot-dev` + AcrPull を手動作成し、Terraform 管理外にする（採択）**: 手動作成は 1 回きり（`az identity create` + `az role assignment create`）。ADR-0012 の決定（SP のロールは 2 件のみ）は不変のまま成立する。管理外の代償（`terraform plan` による drift 検出なし）は、ADR-0014 と同じ枠組みで[管理外リソース台帳](../operations/azure-resource-inventory.md)（#8 / #9）の読み取り確認コマンドが代替する
- (c) CI 用 SP に条件付き・スコープ限定の RBAC 権限を追加（**却下**）: ロール割当も Terraform 管理下に置けるため、コードと実物の一致という意味での一貫性は 3 案で最も高い。しかし CI の SP に「権限を与える権限」（`roleAssignments/write`）を持たせることになり、condition で付与可能ロールを AcrPull に絞っても**権限昇格の経路そのものを新設する**ことに変わりはない。ADR-0012 で RBAC Administrator を意図的に外した決定を一部覆すことにもなる（覆すなら上書き ADR が必要）。5 日間の制約下で得られる利得（ロール割当 1 件の宣言的管理）に見合わない

採択理由:

- **職務分掌（separation of duties）**: アイデンティティと権限の払い出し（人が・承認を経て・まれに行う操作）を、ワークロードの払い出し（CI が・毎日・自動で行う操作）から分離する。CI の自動実行主体には権限を配る力を持たせない。ADR-0012（CI の権限を Terraform 管理リソースの RG に限定）と一貫し、ADR-0014（Azure OpenAI を管理外に据え置く）と同型の「管理対象・破壊経路にそもそも入れない」判断
- **寿命が違うものを同じ層に置かない**: ID と AcrPull 割当は据え置き（1 回作れば残り続ける）、ACR / Container Apps は毎日 destroy / apply で作り直す。寿命の違うものを ephemeral 層に混ぜると、毎朝の再構築のたびに権限の再払い出しが発生する。ID と権限を層の外に出せば、ephemeral 層は「毎日全部消して全部作る」を純粋に保てる

付随する 2 つの設計値:

- **ロール割当のスコープは ACR 個体ではなく RG `rg-felisaichatbot-dev-tf`**: ACR は毎日 destroy / 再作成される。ACR 個体スコープの割当はリソース削除と同時に消え、毎朝手動で作り直すことになる（= 手動作成 1 回きりの利点が消える）。RG スコープなら **ACR を作り直してもロール割当が生き残る**。スコープを広げる代償は小さい: AcrPull の権限は `Microsoft.ContainerRegistry/registries/pull/read` の 1 action のみ（`az role definition list --name AcrPull` 実測 2026-08-21。定義: <https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/containers#acrpull> ）で、RG スコープにしても届く先は RG 内の ACR（現状 1 個）からの pull だけ
- **ID の置き場も RG `rg-felisaichatbot-dev-tf`**: CI 用 SP はこの RG への Contributor しか持たない（ADR-0012）。Terraform が ID を data source で読み、Container App へ紐付ける操作には `Microsoft.ManagedIdentity/userAssignedIdentities/assign/action` が必要で（この action を持つ組み込みロールの定義: <https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/identity#managed-identity-operator> ）、Contributor は RG 内でこれを含む。**ID を SP の権限が届かない別 RG に置くと、CI の plan / apply が ID の読み取り・紐付けの時点で失敗する**ため、置き場は権限スコープ内の一択である。この RG は手動作成・Terraform 管理外（台帳 #3）で ephemeral 層の destroy では消えないため、据え置きリソースの置き場として寿命も合う

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
- [azure-resource-inventory.md](../operations/azure-resource-inventory.md) に #8（マネージド ID）/ #9（AcrPull ロール割当）を追記する（本 ADR と同じ PR で実施）。手動作成コマンドの正本は台帳の「作り直す手順」
- 本層の apply は、ID とロール割当の手動作成（ユーザー承認のうえ実行）が済むまで行わない（CI のデプロイ workflow 整備も同様に保留）

## 関連

- [ADR-0012](./0012-least-privilege-oidc-sp-and-dedicated-terraform-rg.md) — CI 用 SP の権限 2 件のみ（AcrPull 割当を Terraform で作れない制約の源）
- [ADR-0013](./0013-azure-resource-naming-convention.md) — 本層の全リソース名の予約元
- [ADR-0014](./0014-keep-azure-openai-out-of-terraform.md) — 「管理外に置く」判断の先行例（選択肢 6-(b) と同型）
- [day3-5-execution-plan.md](../operations/day3-5-execution-plan.md) §3-2（walking skeleton 正本）/ §3-6（毎日の destroy）/ §8（コスト見張り）/ §9（VNet 統合をやらない）
- [bootstrap.md](../operations/bootstrap.md) 「Day 3 の方針」方針1（hello-world 先行の根拠）
- [ADR-0016](./0016-log-analytics-workspace-in-persistent-layer.md) — Log Analytics workspace の配置のみ本 ADR から変更
- Issue: #70
