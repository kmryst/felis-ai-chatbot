# ADR-0012: CI 用 Service Principal の最小権限化と Terraform 管理リソース専用 RG の分離

## ステータス

Accepted

## 日付

2026-08-20

## 決定内容

GitHub Actions（OIDC）から Terraform apply に使う service principal の権限設計を、初回 apply の前に次のとおり確定する。

1. **federated credential は main 用の 1 本のみ登録する。** PR 用（`:pull_request`）は登録しない
2. **`Role Based Access Control Administrator` は付与しない**
3. **Terraform 管理リソース専用の RG `rg-felisaichatbot-dev-tf` を新設し（手動作成・Terraform 管理外）、Contributor のスコープをそこに限定する。** Terraform 管理外の Azure OpenAI が同居する既存 RG `rg-felisaichatbot-dev` には権限を与えない。既存リソースの移動はしない

付与するロールは次の 2 件のみ（bootstrap.md §11-3）。

| ロール | スコープ |
| --- | --- |
| `Contributor` | `rg-felisaichatbot-dev-tf` |
| `Storage Blob Data Contributor` | tfstate Storage Account `felisaichatbottfstate` |

## 背景

初回 apply 前の外部レビューで、当初案（main と全 PR が同一 service principal を共用し、共有 RG への Contributor・無条件の RBAC Administrator・state への Blob Data Contributor を持つ）には次の問題が指摘された。

- PR 側からも既存の Azure OpenAI の変更・削除、管理者パスワードを含む state の読み書き、ロール割当による権限昇格が可能になる
- `Role Based Access Control Administrator` は Azure の Privileged カテゴリのロールで、`Microsoft.Authorization/roleAssignments/write・delete` と全リソースの read を持つ（出典: <https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/privileged>）
- Terraform の state には sensitive 値（DB 管理者パスワード等）が平文で入るため、state へ届く主体は最小にすべき（出典: <https://developer.hashicorp.com/terraform/language/manage-sensitive-data>）
- `rg-felisaichatbot-dev` に稼働中の Azure OpenAI `felisaichatbot-openai-dev` は Day 2 の RAG が依存しており、FreeTrial のクォータを再取得できる保証がないため、壊すことも作り直すことも許されない

## 検討した選択肢

### 1. PR 用 federated credential

- **(a) 登録しない（採択）**: PR 時の `terraform plan` workflow は未実装で、いま権限を開ける理由がない
- (b) 当初案どおり登録する: 使い道のない認証経路を先に開けることになり、least privilege に反する

### 2. RBAC Administrator

- **(a) 付与しない（採択）**: Day 3 の apply（PostgreSQL Flexible Server + サーバーパラメータ + firewall rule）はロール割当を含まず、不要
- (b) condition 付きで付与する: 将来 Container Apps のマネージド ID へ AcrPull 等を割り当てる時には必要になるが、その時点で condition により付与可能ロールを絞ってスコープ最小で追加すればよい。前倒しする利益がない

### 3. Contributor のスコープ

- **(a) Terraform 管理リソース専用 RG `rg-felisaichatbot-dev-tf` を分ける（採択）**
- (b) 共有 RG `rg-felisaichatbot-dev` のまま Contributor を与える: service principal が Azure OpenAI を変更・削除できてしまう。削除ロック（CanNotDelete）で削除は防げても（Contributor は `Microsoft.Authorization/*/Write` を持たずロックを外せない）、**構成変更（デプロイメントの差し替え等）は防げない**。代替不能リソースの保護として不十分
- (c) リソース単位でロールを絞る: Terraform が扱うリソース種別が Day 3〜5 で増えていく（PostgreSQL → ACR → Container Apps）ため、都度の割当追加が実作業のボトルネックになる。RG 分離のほうが単純で誤りにくい

## 採択理由

- RG 分離のコストは小さい: `az group create` 1 回と、手順書内の RG 名参照の置換のみ。Terraform は元々 RG を data source 参照しており、コード変更は変数の既定値だけで済む
- 得られる保護は大きい: 代替不能な Azure OpenAI が service principal の権限スコープから完全に外れる。「間違えても壊せない」構造上の保証であり、運用注意（気をつけて apply する）より強い
- 全消し手順（day3-5-execution-plan.md §8）は `az group delete` が 2 → 3 RG になるが、Azure OpenAI を面談デモ用に残す選択肢が「RG 単位で残す」という形で逆に単純になる

## 影響

- `terraform/persistent/variables.tf`: `resource_group_name` の既定値を `rg-felisaichatbot-dev-tf` に変更
- `docs/operations/bootstrap.md` §11: credential 1 本化・RG 新設・ロール 2 件化
- `docs/operations/day3-5-execution-plan.md`: §3〜§5 の az コマンドの RG 名、§8 の終業チェック・全消し手順（3 RG）
- 将来 PR 時 `terraform plan` を実装する場合は、subject `repo:kmryst@205493351/felis-ai-chatbot@1336699843:pull_request` の credential と読み取り系の最小ロールを別途設計する（本 ADR の 1 を上書きする ADR を書く）

## 関連

- [ADR-0009](./0009-azure-openai-as-llm-provider.md) — Azure OpenAI（`rg-felisaichatbot-dev`）の位置づけ
- [ADR-0011](./0011-backup-retention-and-geo-redundancy.md) — persistent 層の設計判断
- bootstrap.md §11（OIDC / ロール割当）・§12（tfstate Storage）
