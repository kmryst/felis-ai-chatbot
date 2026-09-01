# LLM provider の stub → azure-openai 切替と rollback（Issue #195）

backend serving（`ca-felisaichatbot-dev`）の LLM provider を、`backend/app/config.py` の
既定 `"stub"`（ADR-0004）から実 Azure OpenAI（ADR-0009）へ切り替える手順と、stub へ戻す
rollback 手順の正本。Azure OpenAI リソース本体は Terraform 管理外（ADR-0014）で、本手順は
接続設定（env / secret）の注入だけを扱う。

> 実行前提: apply は CLAUDE.md の禁止事項に従い**ユーザーの明示承認を得てから**実行する。
> 本書は手順の正本であって実行許可ではない。

## 0. 停止条件（apply 包括許可時も有効）

apply の包括許可を得ている場合でも、次が見えたら**実行を止めてユーザーに確認する**。

- 永続データの破壊（PostgreSQL の destroy / `terraform state rm` / データを失う変更が
  plan に現れた場合）
- 見積りを大きく超える課金（本切替の想定は token 従量課金のみ。§3 の呼び出し回数目安を
  超える連続呼び出しをする前に立ち止まる）

## 1. 前提

- Azure OpenAI `felisaichatbot-openai-dev`（RG `rg-felisaichatbot-dev`）に deployment
  `chat` / `embedding` が存在する（管理外リソース台帳
  [azure-resource-inventory.md](./azure-resource-inventory.md) §B-1）
- `.env`（gitignore 済み。コミット禁止）に `AZURE_OPENAI_*` の実値がある
- 認証は API キー方式（マネージド ID 化は未実施 =
  [production-readiness.md §2](../production-readiness.md)）

## 2. 切替手順

1. `.env` に Terraform 用の変数を追記する（値は既存の `AZURE_OPENAI_*` 行の複製。
   キー値をターミナルへ表示しないよう、エディタ内で複製するか `sed` 等で機械的に行う）

   ```dotenv
   TF_VAR_llm_provider=azure-openai
   TF_VAR_azure_openai_endpoint=<AZURE_OPENAI_ENDPOINT と同値>
   TF_VAR_azure_openai_api_key=<AZURE_OPENAI_API_KEY と同値>
   TF_VAR_azure_openai_api_version=<AZURE_OPENAI_API_VERSION と同値>
   TF_VAR_azure_openai_chat_deployment=<AZURE_OPENAI_CHAT_DEPLOYMENT と同値>
   TF_VAR_azure_openai_embedding_deployment=<AZURE_OPENAI_EMBEDDING_DEPLOYMENT と同値>
   ```

2. [vnet-integration-cutover.md §0-2](./vnet-integration-cutover.md) の作法で export し、
   plan を確認する

   ```bash
   set -a; source .env; set +a
   terraform -chdir=terraform/ephemeral plan
   ```

   期待する diff は `azurerm_container_app.main` の in-place 更新 1 件のみ:
   secret `azure-openai-api-key` の追加と、env `LLM_PROVIDER` / `AZURE_OPENAI_ENDPOINT` /
   `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_API_VERSION` / `AZURE_OPENAI_CHAT_DEPLOYMENT` /
   `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` / `AZURE_OPENAI_CONFIG_CHECKSUM` の追加。
   これ以外のリソースに変更が出たら止める（§0）。

3. apply し、env の反映（= 新 revision の template に載ったこと）を確認する

   ```bash
   terraform -chdir=terraform/ephemeral apply
   az containerapp show -n ca-felisaichatbot-dev -g rg-felisaichatbot-dev-tf \
     --query "properties.template.containers[0].env[].name" -o tsv
   ```

   env の値は表示しない（`AZURE_OPENAI_API_KEY` は `secretRef` のため値は出ないが、
   確認は名前の一覧までに留める）。

## 3. 疎通確認（token 課金を伴う）

呼び出し回数の目安: `/chat` への実プロンプト 1〜2 回（embedding 各 1 回）+
chat completion の確認 1 回。数百〜千数百 token 程度で、クレジット残高に対して軽微。
これを大きく超える連続呼び出しをしない。

- DB が空の間、`/chat` は RAG ガード（ADR-0010）で `notice` 固定文言を返すが、
  **ガード判定より前の embedding 呼び出しは実 provider へ届く**（`backend/app/main.py` の
  `/chat` は最初に `embed()` を実行する）。したがって「実 Azure OpenAI が呼ばれたこと」は
  次の 2 通りで確認する
  1. `/chat` 呼び出し前後の Azure OpenAI メトリクス（呼び出し数 / processed tokens）の増分を
     `az monitor metrics list` で実測する（stub は外部呼び出しゼロのため増分が出ない）
  2. backend serving コンテナ内（注入済み env・実ネットワーク経路）で `LLMClient` の
     chat 呼び出しを 1 回実行し、応答が stub の決定的接頭辞 `[stub]`
     （`backend/app/llm/client.py`）ではない自然文であることを確認する
- RAG を成立させた上での end-to-end 確認（`/chat` が実 LLM の `message` stream を返す）は
  seed 投入・embedding backfill の後続 Issue の範囲

## 4. rollback（stub への復帰）

`.env` の `TF_VAR_llm_provider` を空にして apply する（`LLM_PROVIDER` env が template から
消え、`backend/app/config.py` の既定 `"stub"` に戻る。env は revision-scope のため必ず
新 revision が作られ、反映漏れは起きない）。

```bash
# .env で TF_VAR_llm_provider= （空）に変更してから
set -a; source .env; set +a
terraform -chdir=terraform/ephemeral plan   # diff が LLM_PROVIDER env の除去であることを確認
terraform -chdir=terraform/ephemeral apply
az containerapp show -n ca-felisaichatbot-dev -g rg-felisaichatbot-dev-tf \
  --query "properties.template.containers[0].env[?name=='LLM_PROVIDER']" -o tsv   # 空になる
```

- `AZURE_OPENAI_*` の env / secret は残しても stub は読まない（`Settings.from_env()` は
  `LLM_PROVIDER=azure-openai` のときだけ必須化する）。完全に除去したい場合は
  `TF_VAR_azure_openai_*` も空にして apply する
- key の失効を伴う緊急時は、rollback と独立に Azure 側で key を rotate できる
  （rotate 後の apply は `AZURE_OPENAI_CONFIG_CHECKSUM` の変化により必ず新 revision を作る）

## 5. key rotation の反映担保

`AZURE_OPENAI_API_KEY` は Container Apps の secret（application-scope）であり、値の更新だけ
では新 revision が作られない。`AZURE_OPENAI_CONFIG_CHECKSUM`（key の sha256 先頭 8 桁。
不可逆）を revision-scope の env として template に持たせることで、key を変えた apply が
必ず新 revision 作成を伴う（`DSN_CONFIG_CHECKSUM` / `CHAT_API_KEY_CONFIG_CHECKSUM` と同型。
ADR-0027「付随する決定」）。

## 関連

- ADR-0004（stub 既定・CI から実 LLM を呼ばない。**本切替後も CI・テストは stub のまま**）
- ADR-0009（Azure OpenAI 採用・必須変数・api-version 既定）
- ADR-0014（Azure OpenAI 本体は Terraform 管理外）
- Issue #195 / 実測記録は `docs/verification/` 配下（切替実施時に追加）
