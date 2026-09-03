# felis-ai-chatbot Bootstrap 手順書（Day 0）

本書は `kmryst/felis-ai-chatbot` の Day 0（bootstrap）で実行する手順の正本です。
5日間の開発（Day 1〜5）には含めず、本書完了をもって Day 1 に着手します。

本書内のファイルパス・行番号・check 名は、2026-08-17 に以下のローカルリポジトリの現物を読んで確認した実測値です。

- `/home/gatsby/dev/projects/idp-golden-path`（読み取りのみ。変更禁止）
- `/home/gatsby/dev/projects/terraform-hannibal`（参照のみ）
- `/home/gatsby/dev/projects/ticket-c2c-platform`（参照のみ）

---

## 0. サマリチェックリスト

所要時間の目安: **フェーズA 3.5h + フェーズB 0.5〜3h = Day 1 着手までに 4〜6.5 時間。** フェーズC（1.75h）は Day 3 直前に実施する。

**Day 0 の全体方針**: GitHub リポジトリを確立し、LLM の疎通だけ確保して、すぐ Day 1（ローカル開発）に入る。**Azure 上のアプリ用リソースは Day 3 まで一切作らない。** ローカルで動くものができる前に Azure を作り込むと、課金が先行するうえ、アプリの実態が固まる前にインフラを決め打ちすることになる。

**実行順は下表の「順」列に従うこと。** 「§」列は本書の章番号で、章は資料としてのまとまりで並べてあるため実行順とは一致しない。

### フェーズA: GitHub リポジトリの確立（Azure と完全に独立。先に片付ける）

| 順 | § | ステップ | 目安 | 完了 |
| --- | --- | --- | --- | --- |
| 1 | §4 | GitHub リポジトリ作成（public / main / MIT）→ `/home/gatsby/dev/projects/felis-ai-chatbot` へ clone | 15min | [x] |
| 2 | §5 | skeleton 手動コピー（除外3ファイル・置換13箇所）+ ディレクトリ骨格 | 1h | [x] |
| 3 | §6 | caller workflow 確認 / AWS 文言の Azure 化（4箇所） | 0.5h | [x] |
| 4 | §7 | `.mise.toml` 確認（Day 0 は node のみ。python / terraform は後日） | 10min | [x] |
| 5 | §8 | 初回 ADR 作成（skeleton の ADR-0001 を書き換え）+ **本書を `docs/operations/` へ移動** | 0.5h | [x] |
| 6 | §9 | 初回 push → 初回 PR → **CI green 確認（4 check）** | 1h | [x] |
| 7 | §10 | **branch protection 適用（必ず CI green の後）** | 15min | [x] |

### フェーズB: LLM 疎通の確定（Day 1 の前提。これだけは先にやる）

| 順 | § | ステップ | 目安 | 完了 |
| --- | --- | --- | --- | --- |
| 8 | §1 | Azure アカウント作成・サブスクリプションID / テナントID 確認 | 0.5〜1h | [x] |
| 9 | §2 | **Azure OpenAI 可否判定（タイムボックス2h・撤退基準あり）+ リージョン確定** | 最大 2h | [x] |
| 10 | §13 | 題材確定の期限リマインド（Day 1 終了まで） | — | [x] |

**フェーズB をここに置く理由**: Day 1「Bot 本体をローカルで動かす」には chat / embedding の呼び出し先が必要。Azure OpenAI を第一選択にした以上、ローカル開発にも Azure 上のリソースとデプロイ済みモデルが要る。撤退して OpenAI API になった場合は、フェーズB は「OpenAI アカウント作成 + キー取得」に置き換わり所要時間はさらに短くなる（Azure アカウント作成はフェーズC まで後ろ倒しできる）。

**フェーズB でやらないこと**: Azure 上のアプリ用リソース（PostgreSQL / ACR / Key Vault / Container Apps）は一切作らない。LLM の疎通だけを確定させる。ローカルの PostgreSQL は Day 2 に Docker で立てる。

---

### → ここで Day 1 / Day 2 に入る（ローカルでアプリを動かす）

Day 1: Bot 本体をローカルで動かす / Day 2: データ・RAG・PostgreSQL を整える。
**この間、Azure 上には LLM リソース以外まだ何も存在しない。** 課金対象を最小に保ったまま、アプリが成立するかを先に確かめる。

---

### フェーズC: Azure デプロイ基盤（Day 3 の直前に実施）

| 順 | § | ステップ | 目安 | 完了 |
| --- | --- | --- | --- | --- |
| 11 | §3 | グローバル一意名の空き確認（ACR / Key Vault / PostgreSQL / Storage） | 15min | [ ] |
| 12 | §11 | Entra ID アプリ登録 + federated credential + ロール割当 | 1h | [ ] |
| 13 | §12 | tfstate 用 Storage Account 手動作成 | 0.5h | [ ] |

**フェーズC を Day 3 直前まで遅らせる理由**: いずれも Terraform 実行と CI からのデプロイのための準備であり、ローカル開発には一切関与しない。先に作っても使われないまま放置されるだけで、名前の空き確認は Day 3 に近い時点で行うほうが有効期間の観点でも合理的。

**フェーズA を先にやる理由**（実行順を入れ替えないこと）:

1. Azure の判定結果はリポジトリ初期化に**一切影響しない**。フェーズA の7工程は Azure と完全に独立している。
2. **Azure OpenAI 可否判定の結果を記録する場所が必要**。判定して終わりにせず ADR として残すには、先にリポジトリが存在している必要がある。
3. **本書自身の置き場所**になる（順5で `docs/operations/` へ移す）。手順書は Day 0 の検証証跡でもある。
4. フェーズB が長引いても、フェーズA が終わっていれば「CI が green なリポジトリ」という成果が確定している。

**順序の絶対条件が2つあります。**

1. branch protection は**初回 CI green を確認した後**に適用する（順6→7。逆順は PR 恒久ブロックのリスク。根拠: `idp-golden-path/docs/adr/0006-scaffolder-service-baseline-template.md:25` および skeleton 同梱の `docs/operations/branch-protection.md` 冒頭注意書き）。
2. フェーズB に入ったら、Azure アカウント作成の**直後に最初に** Azure OpenAI 可否判定を行う（順8→9）。他の Azure 作業を先に進めない。判定が撤退に振れた場合、リージョン選定がやり直しになるため。

---

## 1. Azure アカウント作成・ID 確認（0.5〜1h）

### 手順

1. <https://azure.microsoft.com/ja-jp/free/> からアカウントを作成する（Microsoft アカウント新規作成を含む）。
2. `az login` で CLI 認証し、以下で ID を控える。
   - **WSL での注意（2026-08-21 実測）**: security defaults 有効のテナントではデバイスコード方式（`az login --use-device-code`）が `AADSTS530035` でブロックされ、トークン失効後のサイレント更新も拒否される。**ブラウザ方式（`az login --tenant <tenantId>`。`--use-device-code` なし）を使う**こと

```bash
az account show --query "{subscriptionId: id, tenantId: tenantId, name: name}" -o table
```

1. 控えた値を（コミットせず）ローカルのメモに保存する。以後 `$SUB` / `$TENANT` と表記する。

### 検証（これが通れば次へ）

- `az account show` が subscriptionId / tenantId を返す。

### 詰まりやすい箇所

- **無料試用（$200 クレジット）のままでは Azure OpenAI のクォータが付与されない・リソース作成が拒否されることがある。** ステップ2の判定でこれに当たった場合、「従量課金（Pay-As-You-Go）へのアップグレード」までをタイムボックス2時間の内側で試す。アップグレードしてもクォータ申請待ちになるなら撤退基準に該当。

---

## 2. Azure OpenAI 可否判定（タイムボックス 2h・最優先）

**目的**: LLM 提供元を Azure OpenAI Service（第一選択）にするか OpenAI API（フォールバック）にするかを、Day 0 のこの時点で確定させる。以後の設計を分岐させないため、**アカウント作成直後の最初のタスク**とする。

### 判定手順（タイマーを実際に2時間セットする）

1. Azure Portal または CLI で Azure OpenAI リソースの作成を試みる（リージョンは East US / Sweden Central 等、chat と embedding の両モデルが提供されるリージョンを選ぶ。作成前に対象リージョンのモデル提供状況を Portal のモデルカタログで確認する）。
2. 作成できたら、**chat 用モデルと embedding 用モデル `text-embedding-3-small` の両方**のデプロイを試みる。
3. 両方デプロイでき、簡単な呼び出し（Portal のプレイグラウンドで可）が通れば **Azure OpenAI 採用で確定**。

### 撤退基準（1つでも該当したら即 OpenAI API に切り替え）

- クォータ申請フォームの提出と**承認待ちが発生した**時点（待たない）。
- 選定リージョンで chat / embedding の**どちらか一方でも**デプロイできない。
- タイムボックス2時間を超過した。

### フォールバック時の手順

1. OpenAI アカウントを作成し、API キーを取得する（未作成のため新規登録が必要）。
2. キーはローカルの `.env`（gitignore 済み）にのみ置く。Day 3 以降は Key Vault に移す。

### どちらに転んでも固定する事項

- **embedding は `text-embedding-3-small`（1536次元）で統一する。** Azure OpenAI / OpenAI API のどちらでも同一。揃えないと提供元切り替え時に pgvector のカラム定義変更＋全データ再 embedding が発生する。
- LLM クライアント初期化は backend の**1モジュールに閉じ込める**（例: `backend/app/llm/client.py`）。両対応の抽象化レイヤーは作らない（5日制約下では過剰設計）。

### 検証

- 採用する提供元が1つに確定し、chat / embedding の呼び出しが1回ずつ通っている（Azure の場合）。OpenAI API の場合はキー取得まで。

### リージョン決定ルール（このステップの結果で機械的に決まる）

リージョンは事前に決められない。本ステップの判定結果から**以下のルールで機械的に決める**こと。決めたら本書のステップ12以降のリージョン表記を実際の値に更新する。

**原則: アプリ（Container Apps）と PostgreSQL は必ず同一リージョンに置く。** DB アクセスは1リクエストで複数回発生し、リージョンを跨ぐと latency が積み上がるため。Day 4 で計測する application DB latency が跨ぎで悪化すると、監視の議論が「設計ミスの話」にすり替わってしまう。

**LLM は跨いでよい。** アプリから見れば外部 API 呼び出しであり、呼び出し回数も1リクエストあたり数回に収まる。Azure OpenAI が `japaneast` で取れなくても、アプリと DB を `japaneast` に置いたまま LLM だけ別リージョンにする構成で問題ない。その場合は「なぜ跨いだか」を ADR に1行残す。

| ステップ2の結果 | アプリ + PostgreSQL | LLM | tfstate Storage |
| --- | --- | --- | --- |
| Azure OpenAI が `japaneast` で取れた | `japaneast` | `japaneast` | `japaneast` |
| Azure OpenAI が別リージョンでのみ取れた | `japaneast` | そのリージョン | `japaneast` |
| OpenAI API にフォールバック | `japaneast` | 該当なし（外部） | `japaneast` |

tfstate Storage はどのリージョンでもよく、アプリとの latency も関係しない（Terraform 実行時にしか触らない）。運用者が1箇所を覚えていれば済むよう `japaneast` に固定する。

### 判定結果（実施済み）

**Azure OpenAI 採用で確定。** リージョンは上表 1 行目（`japaneast` で取れた）に該当し、アプリ + PostgreSQL / LLM / tfstate Storage すべて `japaneast`（ステップ12以降のリージョン表記も `japaneast` のままで確定）。

- リソース: `felisaichatbot-openai-dev`（リソースグループ `rg-felisaichatbot-dev` / japaneast）
- デプロイ `chat`: gpt-4.1-mini 2025-04-14 / GlobalStandard / capacity 10
- デプロイ `embedding`: text-embedding-3-small v1 / Standard / capacity 10
- chat / embedding とも疎通実測済み（api-version `2024-10-21`。embedding は 1536 次元を実測）
- chat が GlobalStandard SKU である制約（無料試用のクォータ都合。推論データがリージョンを跨ぐ）は [ADR-0009](../adr/0009-azure-openai-as-llm-provider.md) を参照

---

## 3. グローバル一意名の空き確認（15min）

ACR / Key Vault / PostgreSQL Flexible Server / Storage Account は DNS 名になるためグローバル一意。命名規則は [ADR-0013](../adr/0013-azure-resource-naming-convention.md)（CAF 略語準拠）に従う。**Terraform 実装（Day 3）の前ではなく、この Day 0 時点で空きを確認**し、取れなければ命名を再調整してから先に進む（すべて読み取り系コマンド）。

| リソース | 予定名 | 制約 |
| --- | --- | --- |
| ACR | `felisaichatbotacrdev` | 20/50 文字・英数字のみ |
| Key Vault | `kv-felisaichatbot-dev` | 21/24 文字 |
| PostgreSQL Flexible Server | `pgsql-felisaichatbot-dev` | 小文字英数字とハイフン |
| tfstate Storage Account | `felisaichatbottfstate` | 21/24 文字・小文字英数字のみ |

```bash
# ACR（専用コマンドあり）
az acr check-name --name felisaichatbotacrdev -o table

# Storage Account（専用コマンドあり）
az storage account check-name --name felisaichatbottfstate -o table

# Key Vault（専用 CLI がないため checkNameAvailability API を直接叩く。読み取り系）
az rest --method post \
  --uri "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.KeyVault/checkNameAvailability?api-version=2023-07-01" \
  --body '{"name": "kv-felisaichatbot-dev", "type": "Microsoft.KeyVault/vaults"}'

# PostgreSQL Flexible Server（同上）
az rest --method post \
  --uri "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.DBforPostgreSQL/checkNameAvailability?api-version=2024-08-01" \
  --body '{"name": "pgsql-felisaichatbot-dev", "type": "Microsoft.DBforPostgreSQL/flexibleServers"}'
```

### 検証

- 4件すべて `nameAvailable: true`。false の名前があれば、**ランダム文字列・ハンドル名トークンは使わず**（確定事項）、`felisaichatbot` prefix を保ったまま末尾の識別子を変えて再確認する（例: `felisaichatbotacr01dev`）。変更した場合は本書のこの表を更新して正本を保つ。

### 補足

- 空き確認は予約ではない。Day 3 の apply までに他者に取られる可能性はゼロではないが、この prefix で実害が出る確率は低いと判断する。

---

## 4. GitHub リポジトリ作成（15min）

### 確定済み設定

- リポジトリ名: `kmryst/felis-ai-chatbot`
- **最初から public**（private→public は全コミット履歴が一度に公開されるため回避。public なら CodeQL / Actions 分数無料・secret scanning も有効）
- 初期ブランチ: `main`（GitHub 既定）
- LICENSE: MIT
- 単一リポジトリ（frontend / backend を分けない）

### 手順

**ローカルの置き場所**: `/home/gatsby/dev/projects/felis-ai-chatbot`

既存リポジトリ（`idp-golden-path` / `terraform-hannibal` / `ticket-c2c-platform` / `writing-playbook` 等）はすべて `/home/gatsby/dev/projects/` 直下にあるため、そこに揃える。**`mkdir` は不要**で、下記の `gh repo create --clone` がフォルダごと作る。先に空フォルダを作ってしまうと clone 先が衝突するので作らないこと。

```bash
# 親ディレクトリで実行する（clone 先はカレントディレクトリ配下に作られる）
cd /home/gatsby/dev/projects

gh repo create kmryst/felis-ai-chatbot \
  --public \
  --license mit \
  --description "pgvector RAG chatbot on Azure — PostgreSQL backup/restore/maintenance/monitoring showcase" \
  --clone

cd felis-ai-chatbot   # => /home/gatsby/dev/projects/felis-ai-chatbot
```

`--license mit` により、GitHub 側で `LICENSE` を含む初期コミットが作られ、`main` ブランチが確定した状態で clone される。

public リポジトリのため secret scanning は既定で有効。push protection が無効なら Settings > Code security で有効化する。

### 検証

- `gh repo view kmryst/felis-ai-chatbot --json visibility,defaultBranchRef,licenseInfo` が `PUBLIC` / `main` / `MIT` を返す。
- `/home/gatsby/dev/projects/felis-ai-chatbot` が存在し、`LICENSE` がある。
- `git -C /home/gatsby/dev/projects/felis-ai-chatbot remote -v` が `kmryst/felis-ai-chatbot` を指している。
- `git branch --show-current` が `main`。

---

## 5. skeleton 手動コピー（1h）

**Backstage / scaffolder は起動しない**（確定事項）。`idp-golden-path` の skeleton（33ファイル。実測: `find backstage/templates/service-baseline/skeleton -type f | wc -l` = 33）を手動コピーし、テンプレート変数を手で置換する。

### 5-1. コピー元とコピー先

```bash
SRC=/home/gatsby/dev/projects/idp-golden-path/backstage/templates/service-baseline/skeleton
DST=<felis-ai-chatbot の clone 先>

# rsync で除外つきコピー（コピー元は一切変更しない）
rsync -av \
  --exclude 'catalog-info.yaml' \
  --exclude 'mkdocs.yml' \
  --exclude 'docs/index.md' \
  "$SRC/" "$DST/"
```

### 5-2. 除外するファイル（Backstage 固有・実測で3ファイルのみ）

| ファイル | 除外理由 |
| --- | --- |
| `catalog-info.yaml` | Backstage Software Catalog 登録用 |
| `mkdocs.yml` | Backstage TechDocs 用 |
| `docs/index.md` | TechDocs のトップページ |

上記以外の30ファイルはすべてコピーする。**特に以下は削除禁止**:

- `package.json` + `package-lock.json` — reusable workflow（commitlint / markdownlint）が `npm ci` を要求する
- `.mise.toml` — 消すと `toolchain-version-check` が fail する（skeleton の caller workflow ヘッダに明記: 「`.mise.toml` が存在しないと fail する」）

### 5-3. テンプレート変数の置換（実測: 除外3ファイルを除くと **6ファイル13箇所**）

置換値:

- `${{ values.name }}` → `felis-ai-chatbot`
- `${{ values.description }}` → `pgvector RAG チャットボット。PostgreSQL の Backup / Restore / Maintenance / Monitoring を設計・実装・検証する個人開発`
- `${{ values.destination.owner }}` → `kmryst`
- `${{ values.destination.repo }}` → `felis-ai-chatbot`

| ファイル | 行 | 変数 |
| --- | --- | --- |
| `CLAUDE.md` | 1, 3, 8 | `values.name` ×2, `values.description` ×1 |
| `README.md` | 1, 3 | `values.name`, `values.description` |
| `package.json` | 2, 5 | `values.name`, `values.description` |
| `docs/adr/README.md` | 3 | `values.name` |
| `docs/adr/0001-bootstrap-from-service-baseline-template.md` | 13 | `values.name`（※ステップ8で本文ごと書き換えるため置換は書き換えに吸収してよい） |
| `docs/operations/branch-protection.md` | 37, 66 | `values.destination.owner` + `values.destination.repo` ×各2 |

一括置換の例（適用前に `grep -rn 'values\.' .` で対象を目視確認すること）:

```bash
grep -rl 'values\.' --exclude-dir=node_modules . | xargs sed -i \
  -e 's|\${{ values\.name }}|felis-ai-chatbot|g' \
  -e 's|\${{ values\.destination\.owner }}|kmryst|g' \
  -e 's|\${{ values\.destination\.repo }}|felis-ai-chatbot|g' \
  -e 's|\${{ values\.description }}|pgvector RAG チャットボット。PostgreSQL の Backup / Restore / Maintenance / Monitoring を設計・実装・検証する個人開発|g'
```

**注意**: `.github/workflows/**` と `scripts/github/**` にはテンプレート変数が入っていない（実測。`template.yaml:86-88` の `copyWithoutTemplating` 指定どおり）。workflow 内の `${{ github.* }}` を誤って置換しないよう、sed は `values\.` に限定している。

### 5-4. ディレクトリ骨格の作成（空ディレクトリのみ・実装はしない）

```bash
mkdir -p frontend backend \
  terraform/persistent terraform/ephemeral \
  docs/operations docs/verification/restore-drill
# git は空ディレクトリを追跡しないため .gitkeep を置く
find frontend backend terraform docs/verification -type d -empty -exec touch {}/.gitkeep \;
```

構成（確定案。妥当性検討結果は下記補足）:

```text
frontend/          Next.js
backend/           FastAPI
terraform/
  persistent/      PostgreSQL, Log Analytics
  ephemeral/       ACR, Container Apps, 周辺
docs/
  adr/             (skeleton 由来)
  operations/      (skeleton 由来 + Runbook 追加予定)
  verification/restore-drill/
.github/workflows/ (skeleton 由来 caller 7本)
scripts/github/    (skeleton 由来)
```

**構成の妥当性について（検討結果）**: この案のまま採用してよい。根拠:

- persistent / ephemeral の分割は「dev 環境は平常時 destroy 済みが正常」という既存運用（ticket-c2c-platform）と整合する。DB と tfstate を ephemeral から切り離すことで、Container Apps を destroy しても Day 4 の Backup / PITR 検証対象（PostgreSQL）が残る。**本プロジェクトの主役は PostgreSQL 運用なので、この分離自体が見せ場になる**。
- Log Analytics を persistent に置くのも正しい。ephemeral を destroy しても監視ログ・検証証跡が消えない。
- 上記ツリーは Day 3 実装後の姿に更新済み。Day 0 当初案からの変更点: **ACR は persistent ではなく ephemeral に置いた**（イメージは `az acr import` / CI push で作り直せる資産であり、Basic SKU の固定費 0.1666 USD/日 を毎日 destroy で消せる。[ADR-0015](../adr/0015-ephemeral-layer-acr-container-apps-design.md)）。**Key Vault は作らなかった**（secret は Container App の secret + `TF_VAR` 環境変数で足り、Day 3〜5 のスコープに Key Vault を要する要件がない）。**Log Analytics の実装は当初 ephemeral に置かれ本説明と食い違っていたが、[ADR-0016](../adr/0016-log-analytics-workspace-in-persistent-layer.md) で本説明どおり persistent に移した**。
- 唯一の改善提案: `docs/verification/` は restore-drill 以外の証跡（アラーム発火テスト等）も入るため、Day 4 で `docs/verification/alarm-drill/` 等を追加する余地を README に一言書いておくとよい（Day 0 ではディレクトリを増やさない）。

### 検証

- `git status` でコピーされた30ファイル + 骨格が見える。
- `grep -rn 'values\.' . --exclude-dir=node_modules` が 0 件。
- `catalog-info.yaml` / `mkdocs.yml` / `docs/index.md` が存在しない。

---

## 6. caller workflow の調整と AWS 文言の Azure 化（0.5h）

### 6-1. caller workflow（実測結果: **`with:` の上書きは不要**）

skeleton 同梱の caller 7本（`issue-template-check` / `markdown-lint` / `pr-commitlint` / `pr-policy-check` / `security-scan` / `sync-labels` / `toolchain-version-check`）はすべて `uses: kmryst/idp-golden-path/.github/workflows/<file>.yml@v1` 参照で、そのまま使える。idp-golden-path は public リポジトリのため参照可能。immutable タグは v1.0.0〜v1.7.1 と移動タグ v1 が実在する（`git tag` 実測。ADR-0008 の規約どおり）。

reusable 側の `workflow_call` inputs を実測した結果:

- `pr-policy-check.yml` の `strict-paths-regex` 既定値は `^(\.github/workflows/|scripts/github/|terraform/)`（`idp-golden-path/.github/workflows/pr-policy-check.yml:20-25`）。**本リポジトリの構成では `terraform/` がこの既定に含まれるため上書き不要**。Day 3 以降、厳密運用の対象を増やしたくなった場合（例: `backend/app/db/migrations/`）にのみ caller の `with: strict-paths-regex` で上書きする。
- `toolchain-version-check.yml` の `mise-config-path`（既定 `.mise.toml`）/ `workflow-paths`（既定 `.github/workflows/*.yml|yaml`）も既定のままでよい。

ただし CONTRIBUTING.md の「厳密運用の対象」定義（`CONTRIBUTING.md:175-181`）と regex が一致していることを目視確認する。regex を変えるときは必ず CONTRIBUTING.md も同じ PR で更新する。

### 6-2. AWS 文言 → Azure 置換（実測: **4ファイル4箇所**。事前調査の「2ファイル3箇所」より多い）

| ファイル:行 | 現状 | 置換後 |
| --- | --- | --- |
| `CLAUDE.md:116` | `AWS リソースを作成・変更・削除する CLI 操作` | `Azure リソースを作成・変更・削除する CLI 操作（az の書き込み系コマンド）` |
| `CONTRIBUTING.md:179` | `AWS リソース、IAM、OIDC、Secrets、Network、Security に関わる変更` | `Azure リソース、Entra ID RBAC、Managed Identity、OIDC (federated credential)、Key Vault、Network、Security に関わる変更` |
| `.github/labels.yml:51` | `インフラ関連（AWS / Terraform）` | `インフラ関連（Azure / Terraform）` |
| `.github/ISSUE_TEMPLATE/feature_request.yml:34` | `area:infra = AWS / Terraform` | `area:infra = Azure / Terraform` |

（`package-lock.json` 内の "aws" 出現は integrity hash の偶然一致であり対象外。）

reusable workflow 13本（`workflow_call` 対応は実測13本。事前調査の「14本」は誤差）には AWS 参照が**ゼロ**であることを実測確認済み。AWS 固有は `deploy.yml` / `destroy.yml` の2本に閉じており、これらは `workflow_call` 非対応かつ skeleton にも含まれないため影響なし。

### 検証

- `grep -rni aws . --exclude-dir=node_modules --exclude=package-lock.json` が 0 件。

---

## 7. `.mise.toml` の確認（10min）

skeleton の `.mise.toml` は `node = "24.18.0"` のみ宣言し、terraform は「3リポジトリ標準 1.14.8」としてコメントアウトされている（実測）。

**Day 0 では node のみのまま変更しない。** 理由: ADR-0014 の原則「実際にこのリポジトリで使うツールだけを宣言する。使っていないツールを揃えるために宣言しない」（`.mise.toml` 内コメントに明記）。Day 0 時点では Python コードも Terraform コードも存在しない。

追加のタイミング（本書では予告のみ・実行しない）:

| ツール | 追加する日 | 値 | 注意 |
| --- | --- | --- | --- |
| `python` | Day 1（FastAPI 着手時） | 3.13 系最新 | 追加する PR で CI 側に pin があれば `toolchain-version-check` と整合させる |
| `terraform` | Day 3（Terraform 着手時） | **`1.14.8`**（3リポジトリ統一。勝手に下げない — state の前方互換なし） | Terraform を使う workflow の pin も**同じ PR で**同じ値に揃える |

### 検証

- `.mise.toml` がリポジトリ直下に存在し、`node = "24.18.0"` が宣言されている。

---

## 8. 初回 ADR の作成（0.5h）

skeleton 同梱の `docs/adr/0001-bootstrap-from-service-baseline-template.md` を、確定事項「skeleton 手動コピーで開始した理由」の ADR として**本文ごと書き換える**（ファイル名は `0001-bootstrap-by-manual-skeleton-copy.md` 等にリネームしてよい。`docs/adr/README.md` の運用規約に従う）。

含めるべき論点:

- 選択肢: (a) 完全ゼロから (b) Backstage scaffolder を起動して生成 (c) skeleton 手動コピー（採択）
- (c) の根拠: テンプレート変数は実測 9ファイル25箇所（うち Backstage 固有 3ファイルを除くと 6ファイル13箇所）のみで手動置換が現実的。`.github/workflows/**` と `scripts/github/**` は `copyWithoutTemplating` 指定（`template.yaml:86-88`）で変数を含まず無加工で使える。scaffolder 起動のセットアップコストが5日制約に見合わない
- CI は `@v1` タグ参照で idp-golden-path の reusable workflow を消費し、ガードレールの正本を自リポジトリに持たない（ADR-0008 の消費側規約に従う）
- Backstage 固有 3ファイル（`catalog-info.yaml` / `mkdocs.yml` / `docs/index.md`）を除外した判断

### 本書自身をリポジトリへ移す（この工程で必ず行う）

本書は現在 scratchpad にあり、セッション終了で消える。**この時点でリポジトリ内へ移動し、以後はリポジトリ内のものを正本とする。**

```bash
cp /tmp/claude-1000/-home-gatsby/907b3087-ab36-4c88-82fd-d56b73aa898c/scratchpad/bootstrap-felis-ai-chatbot.md \
   docs/operations/bootstrap.md
```

移動後、チェックリストの `[ ]` を進捗に応じて `[x]` に更新しながら進める。**この更新履歴自体が Day 0 の検証証跡になる。**

### 検証

- ADR がフォーマット（Status / Context / Decision / Consequences 相当）を満たし、`docs/adr/README.md` からの導線が通っている。
- `docs/operations/bootstrap.md` が存在し、ここまでの工程が `[x]` になっている。

---

## 9. 初回 push → 初回 PR → CI green 確認（1h）

### 9-1. 初回コミット（main へ直接 push — branch protection 適用前の今だけ許される）

ステップ5〜8 の成果物すべてを初回コミットとして main に push する。コミットメッセージは Conventional Commits に従う（例: `chore: bootstrap from idp-golden-path service-baseline skeleton`）。

push 直後に `sync-labels` workflow が起動する（トリガー: main への push で `.github/labels.yml` 変更あり — 初回コミットは新規追加なので発火する）。これで以後の PR に必須ラベルが付けられるようになる。

**検証**: `gh label list` で `.github/labels.yml` 定義のラベル（`risk:*` / `cost:*` / `area:*` 等）が同期されている。

### 9-2. 初回 PR で CI の実行実績を作る

branch protection の required checks は「一度も実行されていない check」を required に指定すると PR が恒久ブロックされ得るため、**先に実行実績を作る**（`docs/operations/branch-protection.md` 冒頭注意・ADR-0006 に明記の実測済み落とし穴）。

1. 軽微な変更（例: README への1行追記）の Issue を作る。skeleton の `scripts/github/create-issue-with-labels.sh` を使う。
2. branch を切って PR を作る（`scripts/github/create-pr-with-labels.sh`）。**PR Policy Check は必須ラベルと Issue リンクを検査する**ため、helper に必須ラベル 4 種と `--issue <issue番号>` を渡す（Issue リンクは helper が `Closes #<issue番号>` として本文末尾へ自動追記する）。
3. 4つの required check がすべて green になることを確認する:

```bash
gh pr checks <PR番号>
```

期待する check 名（実測。caller job id / callee job name の合成名）:

- `pr-policy-check / PR Policy Check`
- `commitlint / Commitlint`
- `markdown-lint / Markdown Lint`
- `gitleaks / Gitleaks Secret Scan`

（`toolchain-version-check / Toolchain Version Check` も PR で走るが required には入れない — skeleton の `branch-protection.md` の設定表どおり。）

1. green を確認してマージする。

### 詰まりやすい箇所（すべて実測記録あり）

- **caller の concurrency group 名を callee と同一にしない。** GitHub Actions が caller/callee 間デッドロックと判定し job が1つも起動せず run がキャンセルされる（ticket-c2c-platform PR #299 で実測、idp-golden-path Issue #106）。skeleton の caller は `-caller` サフィックスで回避済みなので、**caller workflow の concurrency を編集しない**。
- **`cancel-in-progress: true` に変えない。** CANCELLED check run が commit に残り required checks 判定に混入して PR を恒久ブロックし得る（caller 内コメントに明記）。
- **Dependabot 除外条件を caller job や callee job 全体に置かない。** check が作成されず branch protection が満たせなくなる。除外は callee 内の step 単位が正（`branch-protection.md` 変更時の注意に明記）。
- 初回 PR が `.github/workflows/**` に触れる場合は厳密運用 PR となり、PR 本文の「ロールバック」欄に実質的な記載が必要（PR Policy Check が検査する）。初回 PR は README 追記など**厳密運用パス外**の軽微な変更にするのが楽。

---

## 10. branch protection 適用（15min・必ずステップ9の後）

コピー済みの `docs/operations/branch-protection.md`（ステップ5で owner/repo 置換済み）を正本として、そこに記載の `gh api -X PUT repos/kmryst/felis-ai-chatbot/branches/main/protection` コマンドを実行する。設定内容（skeleton 正本の実測値）:

- required status checks: 上記4つ（strict: false）
- `enforce_admins: true` / `required_approving_review_count: 0` / `required_conversation_resolution: true`
- force push / deletion 禁止

### 検証

- 同ドキュメント記載の確認コマンド（`gh api .../protection | jq ...`）で4 check・enforce_admins=true を確認。
- 直後に main への direct push を1回試みて**拒否されること**を確認する（negative test）。

---

## 11. Entra ID アプリ登録 + federated credential + ロール割当（1h）

GitHub Actions から Azure へ secret レスで認証する OIDC 基盤を作る。

### 11-1. アプリ登録と service principal

```bash
az ad app create --display-name "felis-ai-chatbot-github-actions"
az ad sp create --id <appId>
```

### 11-2. federated credential

**subject は immutable 形式（owner / repo の ID 入り）を使う。** 本リポジトリは 2026-08-17 作成で、GitHub が immutable subject claims を導入した 2026-07-15 より後のため、OIDC トークンの subject は自動的に次の形式になる（旧形式 `repo:kmryst/felis-ai-chatbot:...` を登録すると `azure/login` が必ず失敗する）。

- 出典: <https://docs.github.com/en/actions/reference/security/oidc#immutable-subject-claims>
- 実測値（`gh api repos/kmryst/felis-ai-chatbot --jq '{id: .id, owner_id: .owner.id, created_at: .created_at}'` で確認。2026-08-20）: owner_id `205493351` / repo_id `1336699843` / created_at `2026-08-17`

登録する credential は **main 用の 1 本のみ**（従来型の完全一致で足りる）:

1. `repo:kmryst@205493351/felis-ai-chatbot@1336699843:ref:refs/heads/main` — main への push でのデプロイ

**PR 用（`:pull_request`）は登録しない。** PR 時の `terraform plan` workflow は未実装で、いま権限を開ける理由がないため（ADR-0012）。実装する時点で、subject `repo:kmryst@205493351/felis-ai-chatbot@1336699843:pull_request` を最小権限の別 credential として追加する。

issuer `https://token.actions.githubusercontent.com`、audience `api://AzureADTokenExchange`。

```bash
az ad app federated-credential create --id <appId> --parameters '{
  "name": "github-actions-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:kmryst@205493351/felis-ai-chatbot@1336699843:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'
```

### 11-3. ロール割当（least privilege）

**Terraform 管理リソース専用の RG `rg-felisaichatbot-dev-tf` を先に手動作成し、Contributor のスコープをそこに限定する**（ADR-0012）。既存の `rg-felisaichatbot-dev` には Terraform 管理外の Azure OpenAI `felisaichatbot-openai-dev`（稼働中・作り直し不可）が同居しており、そこへ Contributor を与えると service principal がこれを変更・削除できてしまうため。既存リソースの移動はしない。

```bash
az group create --name rg-felisaichatbot-dev-tf --location japaneast
```

| ロール | スコープ | 目的 |
| --- | --- | --- |
| `Contributor` | `rg-felisaichatbot-dev-tf` | Terraform apply（リソース CRUD） |
| `Storage Blob Data Contributor` | tfstate Storage Account（ステップ12） | azurerm backend の state 読み書き |

```bash
SUB_ID=$(az account show --query id -o tsv)
az role assignment create \
  --assignee-object-id "$(az ad sp show --id <appId> --query id -o tsv)" \
  --assignee-principal-type ServicePrincipal \
  --role "Contributor" \
  --scope "/subscriptions/${SUB_ID}/resourceGroups/rg-felisaichatbot-dev-tf"
# tfstate SA への割当はステップ12で Storage Account を作成した後に行う
az role assignment create \
  --assignee-object-id "$(az ad sp show --id <appId> --query id -o tsv)" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/${SUB_ID}/resourceGroups/rg-felisaichatbot-tfstate/providers/Microsoft.Storage/storageAccounts/felisaichatbottfstate"
```

**付与しないもの（ADR-0012）**:

- サブスクリプション全体への Contributor
- `Role Based Access Control Administrator`。Privileged カテゴリのロール（roleAssignments の write / delete + 全リソースの read）で権限昇格経路になり、Day 3 の apply には不要。将来 Container Apps のマネージド ID へロール付与が必要になった時点で、condition で付与可能ロールを絞ってスコープ最小で追加する。出典: <https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/privileged>

### 検証

- `az ad app federated-credential list --id <appId>` で main 用 credential 1 本のみが見える（subject が `repo:kmryst@205493351/felis-ai-chatbot@1336699843:ref:refs/heads/main` であること）。
- `az role assignment list --assignee <appId> --all -o table` で上記2件のみが見える（余分な割当がない）。
- 実際の OIDC ログイン疎通（`azure/login` action）は Day 3 の最初の workflow で確認する。Day 0 ではここまで。

---

## 12. tfstate 用 Storage Account の手動作成（0.5h）

Terraform backend が使う Storage を Terraform で作る鶏と卵を、**この1回だけの手動作成**で解消する（terraform-hannibal が S3 state bucket で採った方式と同型）。

**順序が重要**: `az storage container create --auth-mode login` は blob の**データプレーン**操作で、サブスクリプション Owner（コントロールプレーンのロール。DataActions を含まない）だけでは実行できない。Storage Account 作成後、**実行者自身へ `Storage Blob Data Contributor` を割り当て、ロール反映を待ってから** container を作成する。出典: <https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-data-operations-cli>（"Even though you are the account owner, you need explicit permissions to perform data operations" / "Azure role assignments may take a few minutes to propagate"）

```bash
# 1. RG と Storage Account（コントロールプレーン。Owner で実行可能）
az group create --name rg-felisaichatbot-tfstate --location japaneast
az storage account create \
  --name felisaichatbottfstate \
  --resource-group rg-felisaichatbot-tfstate \
  --sku Standard_LRS \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false

# 2. 実行者自身へ blob データプレーンのロールを割り当てる（Owner でも別途必須）
SUB_ID=$(az account show --query id -o tsv)
az role assignment create \
  --assignee-object-id "$(az ad signed-in-user show --query id -o tsv)" \
  --assignee-principal-type User \
  --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/${SUB_ID}/resourceGroups/rg-felisaichatbot-tfstate/providers/Microsoft.Storage/storageAccounts/felisaichatbottfstate"

# 3. ロール反映（数分かかることがある）を待ちながら container 作成をリトライ
#    （成功したらループを抜ける。最大 10 分 = 30 秒 x 20 回）
for i in $(seq 1 20); do
  az storage container create \
    --name tfstate \
    --account-name felisaichatbottfstate \
    --auth-mode login && break
  echo "role assignment 反映待ち (${i}/20)"; sleep 30
done

# 4. state の誤削除・破損からの復旧手段（S3 の versioning 相当）
az storage account blob-service-properties update \
  --account-name felisaichatbottfstate \
  --resource-group rg-felisaichatbot-tfstate \
  --enable-versioning true
```

- state 用 RG を Terraform 管理リソース用 RG（`rg-felisaichatbot-dev-tf`）と分けるのは、dev を destroy しても state が残る persistent / ephemeral 分離の一貫。
- azurerm backend は blob lease による state lock が組み込みのため、DynamoDB 相当の追加リソースは不要。
- ステップ11-3 の `Storage Blob Data Contributor`（service principal 向け）をこの Storage Account スコープで割り当てる（§11-3 の 2 本目の `az role assignment create` は Storage Account ができたこの時点で実行する）。

### 検証

- `az storage container list --account-name felisaichatbottfstate --auth-mode login -o table` に `tfstate` が見える。
- versioning が有効（`az storage account blob-service-properties show ... --query isVersioningEnabled` が true）。

---

## 13. 題材確定の期限（Day 1 終了まで）

**Day 2 のデータ整備は題材確定が前提。** 題材（当初案: 宇宙・天体スケール比較）は変更の可能性があるため、**Day 1 終了までに確定させる**。これを Day 1 の TODO 先頭に置く。

判断基準（最大の制約）: **再利用条件が明確に確認できる公開データ源があるか。**

題材が宇宙のままの場合のデータ方針（確定済み）:

- NASA 公式かつ CC0 等、日本からの再利用条件が明確に確認できるものだけを使う。
- 権利条件が曖昧なもの・NASA ページ内の第三者著作物・出所不明の数値は取り込まない。
- provenance（source URL / source title / reuse basis / retrieved_at / note / 数値ごとの source）を保持できるスキーマにする。
- 天体によって取得可能な property が異なるため、全オブジェクトに同一カラムが存在する前提を置かない（EAV / JSONB 等は Day 2 の設計判断）。

---

## Day 0 でやらないこと（スコープクリープ防止）

- Next.js 初期化・FastAPI 実装・PostgreSQL / pgvector 構築（→ Day 1〜2）
- Terraform コードの実装・`terraform init/plan/apply`（→ Day 3。Day 0 は tfstate Storage と OIDC の器まで）
- GitHub Actions の deploy 系 workflow 追加（→ Day 3。Day 0 は skeleton の CI ガードレール 7 本のみ）
- Azure OpenAI / OpenAI API を使ったアプリ実装（Day 0 の呼び出しは可否判定の疎通1回だけ）
- dev 用 resource group 内のアプリリソース作成（PostgreSQL / ACR / Key Vault / Container Apps はすべて Day 3 の Terraform で作る。Day 0 で作るのは tfstate Storage のみ）
- Backup / Monitoring の設定（→ Day 4。ただし要件リストとして ticket-c2c-platform `docs/architecture/production-readiness.md` の M-17 / M-18 / L-32 を Day 4 着手時に読む）
- Backstage / scaffolder の起動
- `.mise.toml` への python / terraform 追加（→ Day 1 / Day 3 で CI pin と同時に）
- Dependabot の groups / ignore 設計の作り込み（skeleton 同梱の dependabot.yml をそのまま使い、必要になってから調整）

---

## Day 3 の方針（確定済み・ここで実行はしない）

Day 0 の決定ではないが、**Day 0 の順序設計と一体の判断**なのでここに記録する。

### 方針1: walking skeleton を先に通す

ローカル優先（Day 1〜2）を維持したうえで、**Day 3 の最初に最小の一本を本番経路で通す**。

1. **hello world だけのコンテナ**を ACR に push し、Container Apps にデプロイする（アプリの中身は空でよい）
2. **空の PostgreSQL Flexible Server** に接続だけする（テーブルなし・クエリは `SELECT 1` で足りる）
3. GitHub Actions からの OIDC 認証・Terraform apply・イメージ push・デプロイまでを一度通す

**狙い**: デプロイ経路の問題を、アプリの複雑さから切り離して潰す。ローカルで2日進めてから一気にデプロイすると、コンテナ化・Container Apps のネットワーク・PostgreSQL の TLS 必須設定・Managed Identity の権限不足・環境変数の渡し方が**まとめて表面化**し（ビッグバン統合）、半日規模で溶ける。その先にあるのが Day 4 = 本命の PostgreSQL 運用検証であり、**Day 3 が押すと最も見せたい成果物が最初に削られる**。

経路が通ってから本体を載せる。

### 方針2: PostgreSQL Flexible Server を Day 3 前半に作る

Day 4 の restore drill は「バックアップが溜まっていること」が前提。**サーバ作成直後は PITR の復元可能範囲が狭く、検証しにくい。** そのため PostgreSQL は Day 3 の前半（walking skeleton と同時）に作り、Day 4 までに時間を稼ぐ。

コストは Burstable B1ms 相当であれば小さく、非利用時は stop できる。

**⚠ Day 3 で必ず実測確認すること**: **停止中の Flexible Server でバックアップが取得され続けるのかどうかは未検証。** 取得されないのであれば「早く作って止めておく」は PITR 履歴の蓄積には寄与せず、restore drill の前に一定時間**起動したまま**にしておく必要がある。以下を Day 3 に確認する。

- 停止中のバックアップ取得可否
- `earliest restore time` が実際にどう動くか（Portal / `az postgres flexible-server show` で確認）
- 停止後の自動再開仕様（一定日数で自動起動する仕様の有無と日数）

確認結果は `docs/operations/backup-and-restore.md` に実測値として記録する。**この「仕様を実測で確かめて記録した」こと自体が Day 4 の成果物になる。**

---

## Dependabot 対象の追加ルール（Day 1 / Day 3）

現状の `.github/dependabot.yml` は skeleton 由来の汎用設定で、`github-actions` (/) と `npm` (/) の2つしかカバーしていない。ルートの npm は commitlint / markdownlint 用であり `dependency-type: development` の1グループのみ。**このプロジェクトの構成にはまだ即していない。**

**ルール: 依存マニフェストを追加する PR で、同じ PR に Dependabot の対象追加も入れる。**

| 追加対象 | directory | いつ | 注意 |
| --- | --- | --- | --- |
| npm | `/frontend` | Day 1（Next.js 初期化） | ルートとは別エントリ。**実行時依存が拾われるよう prod / dev でグループを分ける** |
| pip | `/backend` | Day 1（FastAPI 初期化） | uv を使う場合は ecosystem 名を確認する |
| terraform | `/terraform/persistent`, `/terraform/ephemeral` | Day 3 | provider のバージョン更新用 |
| docker | `/backend`, `/frontend` | Day 3（Dockerfile 作成時） | ベースイメージ更新用 |

マニフェストが存在しないディレクトリを先に登録すると Dependabot がエラーになるため、**先回りして追加しない。**

---

## Day 1 以降で参照する既存資産（読み取りのみ・場所のメモ）

| 参照先 | 使う場面 |
| --- | --- |
| `terraform-hannibal/docs/operations/terraform-runbook.md` | Day 4-5: Runbook の書式・構成の手本 |
| `terraform-hannibal/docs/operations/rollback-plan.md` | Day 4: restore 手順の構造（切り分け→初動→復旧の5ステップ構造）の手本 |
| `terraform-hannibal/terraform/modules/rds/main.tf:1-58` | Day 3-4: `backup_retention_period` / `backup_window` / `maintenance_window` / `deletion_protection` の環境別出し分け。Azure Flexible Server の `backup_retention_days` / `maintenance_window` / CMK 等にほぼ1:1で対応 |
| `ticket-c2c-platform/docs/runbooks/alarm-aurora.md` | Day 4: アラーム初動 Runbook の書式 |
| `ticket-c2c-platform/docs/architecture/production-readiness.md`（M-17 / M-18 / L-32） | Day 4: 「DB backup / PITR runbook 未整備」として挙げられた課題一覧＝今回の実装要件リスト |
| `ticket-c2c-platform/.github/dependabot.yml` | 必要時: terraform ecosystem を含む dependabot 設定と groups の実測ノウハウ |
