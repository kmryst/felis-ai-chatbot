# CLAUDE.md — felis-ai-chatbot Claude Code 作業ルール

このファイルは Claude Code が `felis-ai-chatbot` で作業を開始する前に読む入口です。
一般論ではなく、このリポジトリ固有のルールに従って作業してください。

## このリポジトリの目的

pgvector RAG チャットボット。PostgreSQL の Backup / Restore / Maintenance / Monitoring を設計・実装・検証する個人開発

このリポジトリは [idp-golden-path](https://github.com/kmryst/idp-golden-path) の
ゴールデンパステンプレート（service-baseline）から生成されており、
Issue / PR 駆動の開発フローと CI ガードレールが最初から有効です。

## 位置づけ

- `CLAUDE.md`: Claude Code 向けの作業入口。このファイルを Claude Code の正本とする。
- `CONTRIBUTING.md`: Issue / Branch / Commit / PR / Label / 軽運用・厳密運用の共通正本。
- `.github/labels.yml`: ラベル一覧の正本。
- `docs/adr/`: 設計判断（ADR）の正本。運用ルールは `docs/adr/README.md`。
- `docs/operations/branch-protection.md`: main ブランチ保護設定の記録。
- `docs/operations/slo/`: user-facing SLI / SLO、error budget policy、measurement / review procedure の正本。

内容が衝突する場合は、共通運用は `CONTRIBUTING.md` を優先する。

## 作業開始前に必ず読むファイル

1. `CONTRIBUTING.md`
2. `README.md`
3. 対象 Issue がある場合は `gh issue view <issue番号>`
4. 変更対象ファイル

## 開発フロー

Issue / PR 駆動開発を必ず守る。
順序: Issue 確認 → ブランチ作成 → 実装前計画提示 → 実装 → 検証 → コミット前停止 → コミット → push → PR → merge → cleanup。

Issue / PR の作成には `scripts/github/` の helper スクリプトを使う。
GitHub MCP の `create_pull_request` / `issue_write` は使わない。
helper が必須ラベル 4 種の付与とテンプレート適用を担保しているため。

### Issue 作成

Issue は起票前にプランを提示してユーザーに確認してもらう。

Issue 本文はテンプレートに沿って書く。必須見出しは `## 目的` / `## 対象` / `## 受け入れ条件`
（`##` または `###`、見出しテキストは完全一致、各セクションの中身必須）。
CLI 用テンプレートは `docs/issue-templates/feature_request.md`、Web UI 用は
`.github/ISSUE_TEMPLATE/feature_request.yml`。沿っていない Issue には
issue-template-check が `needs-template` ラベルを付ける。

```bash
./scripts/github/create-issue-with-labels.sh \
  --title "短い要約" \
  --body-file docs/issue-templates/feature_request.md \
  --type type:feature \
  --area area:app \
  --risk risk:low \
  --cost cost:none
```

### Issue 着手

新しい Issue に着手する時は、最新の `main` から作業ブランチを切る。

```bash
git switch main
git pull --ff-only origin main
git switch -c <issue番号>-<kebab-case要約>
```

未コミット変更がある場合は、勝手に stash / reset しない。変更内容を確認し、ユーザーの意図に沿って進める。

### PR 作成

PR は作成前にプランを提示してユーザーに確認してもらう。

`--body-file` には `.github/pull_request_template.md` をそのまま渡さず、テンプレートを埋めたコピーを別ファイルとして作成して渡す。

```bash
./scripts/github/create-pr-with-labels.sh \
  --title "feat: 変更の要約" \
  --body-file /path/to/filled-pr-body.md \
  --issue <issue番号> \
  --type type:feature \
  --area area:app \
  --risk risk:low \
  --cost cost:none \
  --base main
```

### マージ後 cleanup

```bash
./scripts/github/cleanup-merged-pr-branch.sh <PR番号>
```

## 設計判断の記録

トレードオフを伴う設計判断は `docs/adr/` に ADR として記録する。
書き方と運用ルールは `docs/adr/README.md` に従う。番号は ADR を追加する PR の時点で確定する。

## コミットメッセージ

`CONTRIBUTING.md` の Conventional Commits ルールに従う。
`wip`、`fix` のみ、`update files` のような曖昧なメッセージを使わない。

```bash
npx commitlint --from origin/main --to HEAD --verbose
```

## ローカル検証

CI と同じチェックをローカルで実行できる。

```bash
npm ci
npm run lint:md      # Markdown lint
npm run commitlint -- --from origin/main --to HEAD --verbose
```

## 禁止事項

以下は例外なく実行しない。ユーザーから明示的に指示された場合でも実行せず、
必要な場合はユーザー自身が実行する。

- secret / credential 値の出力
- `.env` ファイルのコミット
- `git push --force`
- `main` ブランチへの direct push
- GitHub MCP の `delete_repository`（リポジトリの削除）
- GitHub MCP の `push_files` / `create_or_update_file` / `delete_file`（ブランチと PR を経由しないリモートへの直接書き込み）

## 実行前に確認が必要な操作

以下は実行前にユーザーへ内容を提示し、確認を得てから実行する。

| 操作 | 確認のタイミング |
| --- | --- |
| Azure リソースを作成・変更・削除する CLI 操作（az の書き込み系） | 対象リソースと影響、戻し方を提示してから |
| `terraform apply` / `terraform destroy` / `terraform state rm` | plan 結果と影響範囲を提示してから |
| リポジトリ設定変更（branch protection など） | 変更内容と戻し方を提示してから |
| Issue 起票 | 本文・ラベル案とコマンドを提示してから |
| 実装着手 | 変更対象・変更内容・影響範囲を提示してから |
| コミット | コミット前サマリを提示して停止してから |
| git push | コミット確認後に明示的な許可を得てから |
| PR 作成 | タイトル・本文・ラベル・コマンド案を提示してから |
| GitHub MCP の `merge_pull_request`（PR のマージ） | マージ対象と CI の状態を提示してから |
| ブランチ削除 | cleanup コマンド案を提示してから |

## PR 必須ラベル（4種類）

| ラベル | 要件 |
| --- | --- |
| `type:*` | ちょうど 1 つ |
| `area:*` | 1 つ以上（複数可） |
| `risk:*` | ちょうど 1 つ |
| `cost:*` | ちょうど 1 つ |

PR 本文には `Closes #<issue番号>` / `Fixes #<issue番号>` / `Refs #<issue番号>` のいずれかが必須。
ただしこれは helper が `--issue` の値から `Closes #<issue番号>` を本文末尾に自動追記して満たすため、
`--body-file` には自分で書かない。書くと PR 本文に `Closes` が 2 回現れる。

## ラベル一覧

`.github/labels.yml` が正本。

| 種別 | 値 |
| --- | --- |
| type | `type:feature` / `type:bug` / `type:docs` / `type:infra` / `type:chore` / `type:refactor` / `type:test` |
| area | `area:app` / `area:api` / `area:infra` / `area:ci-cd` / `area:docs` / `area:architecture` |
| risk | `risk:low` / `risk:medium` / `risk:high` |
| cost | `cost:none` / `cost:small` / `cost:medium` / `cost:large` |
