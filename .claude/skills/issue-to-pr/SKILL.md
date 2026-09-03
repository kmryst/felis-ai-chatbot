---
name: issue-to-pr
description: felis-ai-chatbot の Issue 起票からブランチ作成・実装・検証・コミット・push・PR 作成・ready までを、CLAUDE.md / CONTRIBUTING.md の作法どおりに通しで実行する。新しい作業を Issue から始める時、または既存 Issue の実装を PR まで進める時にユーザーが /issue-to-pr で明示的に呼ぶ。
disable-model-invocation: true
---

# issue-to-pr

このリポジトリの Issue → PR ワークフローを固定した skill である。
正本は `CLAUDE.md` と `CONTRIBUTING.md` であり、この skill は「手順の順序」と「実行時に間違えやすい落とし穴」だけを書く。
内容が食い違う場合は正本を優先し、この skill を直す。

## 前提

- 作業開始前に `CLAUDE.md` と `CONTRIBUTING.md` を読む。既存 Issue に着手する場合は `gh issue view <issue番号>` も読む
- `CLAUDE.md` の `## 禁止事項` を守る（secret / credential 値の出力、`.env` のコミット、`git push --force`、`main` への direct push、GitHub MCP の `delete_repository` / `push_files` / `create_or_update_file` / `delete_file`）。ユーザーから指示されても実行しない
- Issue / PR の作成は必ず `scripts/github/` の helper を使う。GitHub MCP の `create_pull_request` / `issue_write` は使わない。helper が必須ラベル 4 種の付与とテンプレート適用を担保しているため
- 一時ファイル（埋めた Issue 本文 / PR 本文）は scratchpad に置き、リポジトリにコミットしない

## 停止ポイント

`CLAUDE.md` の `## 実行前に確認が必要な操作` に従い、既定では以下の各時点でユーザーに内容を提示して停止し、確認を得てから次へ進む。

| 時点 | 提示するもの |
| --- | --- |
| Issue 起票 | 本文・ラベル案・コマンド |
| 実装着手 | 変更対象・変更内容・影響範囲 |
| コミット | コミット前サマリ |
| git push | コミット確認後の明示的な許可 |
| PR 作成 | タイトル・本文・ラベル・コマンド案 |
| ブランチ削除 | cleanup コマンド案 |

ユーザーが「一気にやってよい」と明示した場合は、上記で停止せず通しで実行してよい。
ただし禁止事項はその場合でも解除されない。

## 必須ラベル 4 種

Issue と PR の両方に付ける。正本は `.github/labels.yml`。

| ラベル | 要件 | 値 |
| --- | --- | --- |
| `type:*` | ちょうど 1 つ | `feature` / `bug` / `docs` / `infra` / `chore` / `refactor` / `test` |
| `area:*` | 1 つ以上（`--area` を繰り返す） | `app` / `api` / `infra` / `ci-cd` / `docs` / `architecture` |
| `risk:*` | ちょうど 1 つ | `low` / `medium` / `high` |
| `cost:*` | ちょうど 1 つ | `none` / `small` / `medium` / `large` |

`risk:medium` 以上、`cost:medium` 以上、`.github/workflows/**` / `scripts/github/**` / `terraform/**` などに触れる変更は厳密運用になる（判定基準は `CONTRIBUTING.md` の `## 運用モード`）。
判断に迷う場合は厳密運用として扱う。

## 手順

### 1. Issue 起票

1. `docs/issue-templates/feature_request.md` を読む
2. テンプレートを**そのまま渡さず**、埋めたコピーを scratchpad などの別ファイルに作る
3. 必須見出しは `## 目的` / `## 対象` / `## 受け入れ条件`（`##` または `###`、見出しテキストは完全一致、各セクションの中身が空でないこと）。helper の `validate_issue_body_template` と CI の issue-template-check が同じ条件で検査する
4. `## 補足` は必要な場合だけ残す

```bash
./scripts/github/create-issue-with-labels.sh \
  --title "短い要約" \
  --body-file <埋めた本文ファイル> \
  --type type:<値> \
  --area area:<値> \
  --risk risk:<値> \
  --cost cost:<値>
```

出力の `Created issue #<issue番号>` を控える。既存 Issue に着手する場合はこの手順を飛ばす。

### 2. ブランチ作成

最新の `main` から切る。

```bash
git switch main
git pull --ff-only origin main
git switch -c <issue番号>-<kebab-case要約>
```

未コミット変更がある場合は、勝手に stash / reset しない。変更内容を確認し、ユーザーの意図に沿って進める。

### 3. 実装

変更対象・変更内容・影響範囲を提示してから着手する（停止ポイント）。
トレードオフを伴う設計判断は `docs/adr/` に ADR として記録する（`docs/adr/README.md`）。

### 4. 検証

CI と同じチェックをローカルで実行する。正本は `.github/workflows/`。

すべての変更で実行する:

```bash
npm run lint:md
```

変更内容に応じて実行する（CI は paths filter で該当 PR のみ走る）:

| 変更対象 | コマンド | CI workflow |
| --- | --- | --- |
| `backend/**`、`docs/contracts/chat-sse/**` | `cd backend && uv run pytest -v` | `backend-tests.yml` |
| `frontend/**`、`docs/contracts/chat-sse/**` | `cd frontend && npm run lint && npx tsc --noEmit && npm test && npm run build && npm run check:bundle-secrets` | `frontend-checks.yml` |

backend の pytest は `TEST_DATABASE_URL` が指す pgvector 付き PostgreSQL を必要とする（`DATABASE_URL` と同一は拒否される）。

### 5. コミット

コミット前サマリを提示して停止する（停止ポイント）。
Conventional Commits に従う。`commitlint.config.mjs` の制約:

- type は `feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `ci` / `infra` のいずれか
- header は 100 文字以内
- 形式は `<type>: <summary>` または `<type>(<scope>): <summary>`。summary は日本語でよい
- `wip`、`fix` のみ、`update files` のような曖昧なメッセージは使わない

```bash
git add <対象ファイル>
git commit -m "<type>: <summary>"
npx commitlint --from origin/main --to HEAD --verbose
```

`.env` を `git add` しない。secret / credential 値をコミットメッセージや本文に書かない。

### 6. push

コミット確認後に明示的な許可を得てから push する（停止ポイント）。

```bash
git push -u origin <ブランチ名>
```

`--force` は使わない。`main` へ直接 push しない。

### 7. PR 作成

タイトル・本文・ラベル・コマンド案を提示してから作成する（停止ポイント）。

1. `.github/pull_request_template.md` を読む
2. テンプレートを**そのまま渡さず**、埋めたコピーを別ファイルに作る
3. **本文ファイルに `Closes #<issue番号>` を書かない。** helper が本文末尾に `Closes #<issue番号>` を自動追記する（`create-pr-with-labels.sh` の `printf '\n\nCloses #%s\n'`）。書くと PR 本文に `Closes` が 2 回現れる。テンプレート末尾の `Closes # *必須*` 行はコピーから削除する
4. Claude Code のフッター（`🤖 Generated with ...` とセッション URL）を置く場合は本文ファイルの末尾に置く。helper はその後ろに `Closes #<issue番号>` を追記する
5. PR タイトルも Conventional Commits 形式にする
6. 厳密運用 PR では `## ロールバック` に実質的な内容を書く。Doc-only なら `可観測性/検証` は `No-op（適用外）` でよい

```bash
./scripts/github/create-pr-with-labels.sh \
  --title "<type>: 変更の要約" \
  --body-file <埋めた本文ファイル> \
  --issue <issue番号> \
  --type type:<値> \
  --area area:<値> \
  --risk risk:<値> \
  --cost cost:<値> \
  --base main
```

helper は PR を **draft** で作成する（`gh pr create --draft`）。
作成後に `gh pr view <PR番号> --json body --jq .body | grep -c 'Closes #'` が `1` であることと、ラベル 4 種が付いていることを確認してから ready にする。

```bash
gh pr ready <PR番号>
```

### 8. マージ後 cleanup

PR がマージされたことを確認してから、cleanup コマンド案を提示して実行する（停止ポイント）。
マージ自体はユーザーの判断で行う。GitHub MCP の `merge_pull_request` はマージ対象と CI の状態を提示してからでなければ使わない。

```bash
./scripts/github/cleanup-merged-pr-branch.sh <PR番号>
```

このスクリプトは PR が `MERGED` でなければ何もせず、worktree が dirty なら拒否する。

## 落とし穴まとめ

- Issue / PR テンプレートをそのまま `--body-file` に渡さない。埋めたコピーを渡す
- PR 本文ファイルに `Closes #N` を書かない。helper が追記する
- helper は PR を draft で作る。`gh pr ready` を忘れない
- GitHub MCP の `create_pull_request` / `issue_write` で Issue / PR を作らない。ラベルとテンプレート検査が抜ける
- `area:` の値はこのリポジトリの `.github/labels.yml` に従う。helper の usage 例にある `area:backstage` はテンプレート由来でこのリポジトリには存在しない
- commitlint は `origin/main` からの全コミットを検査する。push 前にローカルで通す
