# ADR-0033: 構成図の作図スクリプトと inventory を公開リポジトリに置く

## ステータス

Accepted

## 日付

2026-11-02

## 決定内容

1. **構成図の作図スクリプトと inventory を `docs/architecture/src/` に置く。**
   置くのは作図スクリプト（`elements.py` / `gen.py`）、図と全体図の一致を検査するスクリプト（`check_views.py`）、
   inventory（`inventory.md`）、全体図（`architecture.drawio`）。README に載せる図 2 枚
   （`docs/architecture/architecture-request-flow.{drawio,png}` / `architecture-operations.{drawio,png}`）の位置は変えず、
   スクリプトはその場所へ相対パスで書き出す
2. **inventory の識別子は外さない。** リソース名、resource group 名、CIDR、FQDN、secret 名はそのまま載せる。
   同じ値が `terraform/` と `docs/operations/`（`azure-resource-inventory.md` など）で既に公開されているためである。
   まだ公開されていない値（subscription ID・tenant ID、メールアドレス、人の名前、アカウントや契約の事情、secret の値）は載せない
3. **公開前の検査に使う deny list / allow list は公開リポジトリに置かない。** 非公開リポジトリ `check-publish-lists` で管理する
4. **本番の環境なら、inventory と IaC は非公開リポジトリに置く。** 本リポジトリが公開で置いているのは、個人の検証環境だからである

## 背景

README の構成図 2 枚は、リポジトリ外の作業フォルダにある作図スクリプトから生成していた。
スクリプトと、図の元になった inventory（リソース一覧と接続関係、根拠の `ファイル:行`）がリポジトリに無いため、
図を直す人が再生成できず、図の根拠もたどれなかった。

また、作業フォルダのスクリプトは図 1 と全体図に同じ線（例: ④ 質問の転送 `[JSON/HTTP, SSE]`）を別々に書いていた。
片方だけ直すと図どうしが食い違う。リポジトリに入れるにあたり、線とノードの意味（ID・始点・終点・目的のラベル・`[技術]`・線種、
ラベル・アイコン）を `elements.py` の 1 か所に定義し、`gen.py` の図ごとの関数には座標とラベル位置だけを書く形にした。
生成結果は移す前の図とバイト単位で一致する。

inventory はリソース名・CIDR・FQDN・secret 名を含む。公開リポジトリに置いてよいかを判断する必要があった。

## 検討した選択肢

### 選択肢 A: スクリプトと inventory を識別子ごと公開リポジトリに置く（採択）

- 利点: 図の根拠（`ファイル:行`）をリポジトリ内でたどれる。識別子は既に `terraform/` と `docs/operations/` で公開済みのため、新たに公開される情報が無い
- 欠点: 偵察に使える情報を 1 か所にまとめた文書を増やす（下記「影響」）

### 選択肢 B: inventory から識別子を伏せて置く

- 利点: inventory 単体からは名前が読めない
- 欠点: 同じ値は `terraform/` に残るため、隠す効果が無い。伏せた inventory はコードと突き合わせられず、根拠の文書として使えなくなる

### 選択肢 C: スクリプトと inventory をリポジトリに置かない（現状維持）

- 利点: 公開範囲が増えない
- 欠点: 図を再生成できる人がいない。図と根拠の対応が失われる

## 採択理由

この環境の守りの本体は、識別子を隠すことではなく、**識別子を知られても入れない作り**である。

- frontend の前段は built-in authentication（Easy Auth）で、未認証の要求はサインインへ送られる（[ADR-0027](0027-frontend-azure-deployment-and-public-surface.md)）
- backend は internal ingress で、internet から到達できない（[ADR-0027](0027-frontend-azure-deployment-and-public-surface.md)）
- PostgreSQL は private access（VNet 統合）で public network access が無く、認証は Microsoft Entra 認証のみ（[ADR-0018](0018-postgresql-private-access-and-vnet-integration.md)、[ADR-0031](0031-entra-managed-identity-auth-and-remaining-secrets.md)）
- Key Vault は Microsoft Entra 認証と Azure RBAC で守る。Azure OpenAI は API キー認証を無効にし、managed identity の Microsoft Entra 認証だけで使う（[ADR-0031](0031-entra-managed-identity-auth-and-remaining-secrets.md)、[ADR-0032](0032-key-vault-references-for-container-apps-secrets.md)）

これは NIST SP 800-123（Guide to General Server Security、2008 年 7 月）の 2.4 Server Security Principles にある Open Design の原則に沿う。

> Open Design—System security should not depend on the secrecy of the implementation or its components.
>
> （訳）Open Design — システムのセキュリティは、実装やその構成要素が秘密であることに依存すべきではない。

出典: <https://csrc.nist.gov/pubs/sp/800/123/final>

Open Design は「実装を秘密にしなくても安全な作りにせよ」という原則であり、識別子を隠す根拠ではない。
本 ADR では、識別子を公開しても安全性が下がらない作りになっていることの根拠として使う。

## 影響

- 図を直すときは `docs/architecture/src/gen.py` を実行して drawio を再生成し、`check_views.py` で図と全体図の線・ラベルが一致することを確かめる。
  ラベルやアイコンを変えるときは `elements.py` を直す。図ごとの関数でラベルを上書きしない
- PNG は生成した drawio を draw.io で書き出す。スクリプトは drawio だけを生成する
- 公開リポジトリは偵察の材料になる。MITRE ATT&CK の T1593.003 は、攻撃者が公開リポジトリから標的の情報を集める手法として記載している。

  > Adversaries may search public code repositories for information about victims that can be used during targeting.
  >
  > （訳）攻撃者は、標的への攻撃に使える被害者の情報を求めて、公開のコードリポジトリを検索することがある。

  出典: <https://attack.mitre.org/techniques/T1593/003/>（Search Open Websites/Domains: Code Repositories）

  そのため、本番の環境なら inventory と IaC は非公開リポジトリに置く（決定 4）。「知られても入れない作り」が本体であることは変わらないが、
  本番では偵察の手間を増やす意味がある。本リポジトリは個人の検証環境で、IaC を公開することが目的の一部であるため、公開のまま置く
- deny list / allow list は「隠したい値」そのものの一覧であり、公開すると隠す対象を教えることになる。そのため公開リポジトリに置かず、
  非公開リポジトリ `check-publish-lists` で管理する（決定 3）
- inventory に新しい値を足すときは、その値が既に `terraform/` か `docs/` で公開されているかを確かめる。まだ公開されていない値（決定 2）は足さない

## 関連

- [Issue #347](https://github.com/kmryst/felis-ai-chatbot/issues/347)
- [docs/architecture/src/README.md](../architecture/src/README.md)
- [ADR-0018](0018-postgresql-private-access-and-vnet-integration.md) — PostgreSQL の private access
- [ADR-0027](0027-frontend-azure-deployment-and-public-surface.md) — 公開面（Easy Auth + BFF + backend internal ingress）
- [ADR-0031](0031-entra-managed-identity-auth-and-remaining-secrets.md) — Microsoft Entra 認証への移行
- [ADR-0032](0032-key-vault-references-for-container-apps-secrets.md) — Key Vault 参照
