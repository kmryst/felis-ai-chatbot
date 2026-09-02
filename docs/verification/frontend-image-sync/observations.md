# デプロイ済み image と main の同期（frontend 表示更新）の実測記録（Issue #206）

- 実施日: 2026-09-02（UTC）
- 実施 PR: #207（squash `b6d90f7`。表示文言の変更 + `check-image-drift.sh` + runbook 追記）。
  手順の正本: [vnet-integration-cutover.md §0-2 / §2](../../operations/vnet-integration-cutover.md)
- 実施者: Claude Code（build / push / apply / マージまでの包括許可は 2026-09-01〜02 に
  ユーザーから伝達済み）
- 時刻はすべて UTC

## 0. 発端（乖離の事実）

- デプロイ中の frontend image は `frontend:sha-2df47f9`（#194 時点。ACR の `frontend`
  リポジトリのタグは `sha-2df47f9` の 1 本のみ）
- main HEAD（`a0f335d`）には #196 の `frontend/app/page.tsx` 変更（副題の文言変更）が入って
  いたが、image は作り直されていなかった。結果としてブラウザの副題が
  「pgvector RAG チャットボット（Day 1: LLM はスタブ。RAG 接続は Day 2）」のまま残っていた
- `check-image-drift.sh`（#207 で追加）を `DEPLOY_SHA=2df47f9` で実行した結果（乖離の機械検出）:

```text
DRIFT: DEPLOY_SHA=2df47f9 → HEAD=b6d90f7 で image に影響する差分がある。
  backend/tests/test_app.py
  backend/tests/test_ingest.py
  frontend/app/globals.css
  frontend/app/layout.tsx
  frontend/app/page.tsx
```

`backend/` の差分は `tests/` のみで、`backend/Dockerfile` の COPY 対象（`app/` /
`migrations/` / `observability/` / `alembic.ini` / `pyproject.toml` / `uv.lock`）に含まれない。

## 1. 表示文言の変更（PR #207）

ユーザー指示により、h1 を `felis-ai-chatbot` から「気象情報チャットボット」に変更し、
副題（`<p class="subtitle">`）を丸ごと削除した。`metadata.title` / `description` も同じ方針で
更新。フッターの出典・免責表示（ADR-0008）は変更していない。

## 2. build / push（runbook §2。3 本同一 SHA = ADR-0027 決定 7）

- 作業ツリー clean・`NEW_SHA=b6d90f7`（squash マージ後の main HEAD）
- build 05:15:27 〜 05:15:56、push 完了 05:16:02（layer cache が効き約 35 秒）
- ACR 上のタグと digest:

| image | `sha-2df47f9`（旧） | `sha-b6d90f7`（新） |
| --- | --- | --- |
| `frontend` | `sha256:e606bcf8…` | `sha256:57f6a56d…` |
| `backend` | `sha256:ea571cd5…` | `sha256:29b26be5…` |
| `backend-ops` | `sha256:8342ba53…` | `sha256:59df668f…` |

- backend / backend-ops はソース上の差分が `tests/` のみだが digest は一致しなかった
  （再 build による層の再生成。digest による「内容同一」の証明はできないため、後述の
  revision Healthy と `/readyz` / `/chat` の実測を根拠にする）
- `.env` の `DEPLOY_SHA` を `b6d90f7` に書き戻し、`check-image-drift.sh` → `OK`（exit 0）

## 3. plan / apply

- apply 前の baseline plan（`DEPLOY_SHA=2df47f9` のまま）: **No changes**。
  `TF_VAR_backend_ingress_external=false` が `.env` から効いており、#195 で検出された
  「backend が external ingress に巻き戻る」差分は無い
- 新 SHA での plan: **0 to add, 7 to change, 0 to destroy**。7 件はすべて image タグの
  `sha-2df47f9 → sha-b6d90f7` のみ（`front[0]` / `main` / `ops[0]` / Job 4 本
  `migrate` / `obs_collect` / `seed` / `embed_backfill`）。image 以外の属性差分なし
- frontend 以外の 6 件が含まれるのは ADR-0027 決定 7（3 image は単一 `DEPLOY_SHA` を共有）と
  runbook §0-2 の作法による。frontend だけを `-target` で更新すると、`DEPLOY_SHA` と
  backend / ops の実 image が食い違い、次回の plan が黙って差分を提案する状態（本 Issue が
  潰そうとしている乖離そのもの）を作るため採らなかった
- `terraform apply`（plan ファイルをそのまま適用）: **Apply complete! Resources: 0 added,
  7 changed, 0 destroyed.**（05:18:02 〜 05:18:48）

## 4. 反映確認

- 3 app + Job 4 本の image 参照がすべて `sha-b6d90f7`（`az containerapp show` /
  `az containerapp job show`）
- frontend: 新 revision `ca-felisaichatbot-dev-front--0000002`（traffic 100% /
  Healthy / RunningAtMaxScale）。旧 `--0000001` は Deprovisioning を経て一覧から消えた
- backend: 新 revision `ca-felisaichatbot-dev--0000007`（traffic 100% / Healthy /
  RunningAtMaxScale。起動時の必須 env 検証を通過している）
- Easy Auth の維持: 匿名 `GET /` → **401**、ブラウザ相当（`Accept: text/html` + Mozilla UA）
  → **302** `login.microsoftonline.com/.../authorize`
- frontend `/readyz` → **200**（frontend → internal backend → DB）
- 外形監視 probe（`workflow_dispatch`）→ **success**:
  `PROBE ts=2026-09-02T05:19:29.301Z http_code=200 latency_ms=577 obs=present heartbeat_age=15
  stats_age=312 pgstattuple_age=3375 enforce=true`

### 4-1. デプロイ済み画面の表示（Easy Auth 越しの curl は 401 になるため 2 経路で確認）

1. **push 済み image をローカルで起動**（`docker run` → `curl localhost:3000/`）:
   `<h1>気象情報チャットボット</h1>` / `<title>気象情報チャットボット</title>` /
   `subtitle` 0 件 / `Day 1` 0 件
2. **デプロイ済み frontend コンテナ内から取得**（`az containerapp exec` → コンテナ内の node で
   `fetch('http://localhost:3000/')`。Easy Auth sidecar を経由しない app コンテナ直接）:

```text
DEPLOYED_H1=<h1>気象情報チャットボット</h1>
DEPLOYED_TITLE=<title>気象情報チャットボット</title>
SUBTITLE_COUNT=0
DAY1_COUNT=0
```

deployed 実機の HTML で、h1 が新表記・副題が不在であることを確認した。

### 4-2. backend 新 revision での `/chat`（接地の実例は [rag-grounding-check](../rag-grounding-check/observations.md)）

backend コンテナ内から `POST http://localhost:8000/chat`（`X-API-Key` はコンテナ env から
参照。値は出力していない）→ **200**、SSE `message` × 55 → `done`。応答本文は
rag-grounding-check の記録に転記。

## 5. 再発防止（Issue #206 の 5）

- **実施**: `scripts/deploy/check-image-drift.sh` を追加し、runbook §0-2 の手順（変数 export の
  直後・plan の前）に組み込んだ。`.env` の `DEPLOY_SHA` と HEAD の間で `backend/` /
  `frontend/` に差分があれば exit 1 で止める。既存の「`DEPLOY_SHA` は push 時にだけ更新する」
  作法（push していないタグを参照しない）の**逆方向**（main が進んだのに再 build しない）を
  検出する
- **実施しなかったこと**: main への merge で image を自動 build / push する CI。理由:
  (1) CI 用 SP は最小権限（ADR-0012）で ACR push 権限を持たず、権限追加は ADR の再検討を要する、
  (2) apply 自体が手動（ユーザー承認制）なので push だけ自動化しても「push 済みだが apply
  していない」乖離に形が変わるだけで閉じない、(3) 本リポジトリの規模では runbook 上の
  1 コマンドで足りる（過剰な作り込みを避ける）

## 6. コスト

- 常設リソースの追加なし。ACR は 3 image 分のストレージ増（Basic の included 10 GiB 内）
- revision 入れ替え中の新旧 replica 重複は frontend / backend とも 1 分未満
- Azure OpenAI: §4-2 の probe 1 回分（embedding 1 + chat completion 1）
- 日次コストの変化なし（frontend 1 replica の目安 0.0769 USD/日は
  [frontend-easy-auth-cutover §9](../frontend-easy-auth-cutover/observations.md) のまま）
