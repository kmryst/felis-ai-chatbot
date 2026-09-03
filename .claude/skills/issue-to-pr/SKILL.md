---
name: issue-to-pr
description: felis-ai-chatbot の Issue 起票からブランチ作成・実装・検証・コミット・push・PR 作成・レビュー・マージ・cleanup までを、CLAUDE.md / CONTRIBUTING.md の作法どおりに通しで実行する。新しい作業を Issue から始める時、または既存 Issue の実装をマージまで進める時にユーザーが /issue-to-pr で明示的に呼ぶ。
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
| レビュー | レビュー結果と未解決スレッドの有無 |
| マージ | マージ対象と CI の状態 |
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

作成後に `gh pr view <PR番号> --json body --jq .body | grep -c 'Closes #'` が `1` であることと、ラベル 4 種が付いていることを確認する。

PR 本文を後から更新する場合は `gh pr edit <PR番号> --body-file <埋めた本文ファイル>`。
古い gh（2.45 系など）は廃止済みの `repository.pullRequest.projectCards` を含む GraphQL を送るため失敗するので、gh は新しいものを使う。
更新できない場合の回避策は REST の `gh api repos/kmryst/felis-ai-chatbot/pulls/<PR番号> -X PATCH -F body=@<埋めた本文ファイル>`。

### 8. レビュー

PR 作成後、マージ前に必ずレビューを通す。レビュー結果と未解決スレッドの有無を提示して停止し、確認を得てからマージへ進む（停止ポイント）。

1. 差分をレビューする。このリポジトリでは code-review skill を使い、PR 番号を引数に渡せる

   ```text
   /code-review 217
   ```

2. Amazon Q Developer の自動レビュー結果を確認する。PR 作成直後は結果がまだ出ていないことがあるため、`Amazon Q Developer` が完了しているかを確認してから判断する

   ```bash
   gh pr checks <PR番号>
   ```

   Amazon Q が check として現れず、レビュースレッドだけを投稿する場合もある。その場合は次のスレッド確認で判断する。
   自動レビューは PR 作成時の 1 回だけで、以降のコミットを push しても再実行されない（PR #217 で実測）。push 後に新しいレビューを待たない

3. レビュースレッドの解決状態を確認する。未解決（`isResolved: false`）のスレッドが 1 つでも残っていればマージへ進まない。後続コミットで指摘行が動くとスレッドは `isOutdated: true` になるが、`isResolved` とは独立であり、outdated でも未解決ならマージはブロックされる

   ```bash
   gh api graphql -f query='
   query($owner:String!, $repo:String!, $number:Int!) {
     repository(owner:$owner, name:$repo) {
       pullRequest(number:$number) {
         reviewThreads(first:50) {
           nodes {
             id
             isResolved
             path
             comments(first:1) { nodes { author { login } body } }
           }
         }
       }
     }
   }' -F owner=kmryst -F repo=felis-ai-chatbot -F number=<PR番号> \
     --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved | not)'
   ```

4. 指摘に対応する。どちらの場合も判断根拠を残す（取り込む場合はコミットメッセージまたは PR コメント、resolve する場合はスレッドへの返信）
   - 妥当な指摘: 修正して commit / push し直す（手順 5・6 に戻る）
   - 妥当でない指摘: 理由をスレッドに書いてから `resolveReviewThread` で resolve する

   ```bash
   gh api graphql -f query='
   mutation($threadId:ID!) {
     resolveReviewThread(input:{threadId:$threadId}) {
       thread { id isResolved }
     }
   }' -F threadId=<スレッドの id>
   ```

`main` は `required_conversation_resolution: true` である。未解決スレッドを残したままマージへ進むと `mergeStateStatus` が `BLOCKED` になり、`gh pr merge` が `the base branch policy prohibits the merge` で失敗する。これはマージ時ではなくこの手順で拾う（PR #217 で実際に発生した）。

### 9. マージ

マージは `CLAUDE.md` の確認必須操作である。マージ対象と CI の状態を提示して停止し、確認を得てから実行する（停止ポイント）。

まず CI が全 pass していることを確認する。

```bash
gh pr checks <PR番号>
```

`gh pr view <PR番号> --json mergeStateStatus` が `CLEAN` であることも確認してからマージする。

```bash
gh pr merge <PR番号> --squash
```

GitHub MCP の `merge_pull_request` は使わず、`gh pr merge` を使う。

### 10. マージ後 cleanup

PR がマージされたことを確認してから、cleanup コマンド案を提示して実行する（停止ポイント）。

```bash
./scripts/github/cleanup-merged-pr-branch.sh <PR番号>
```

このスクリプトは PR が `MERGED` でなければ何もせず、worktree が dirty なら拒否する。

## 落とし穴まとめ

- Issue / PR テンプレートをそのまま `--body-file` に渡さない。埋めたコピーを渡す
- PR 本文ファイルに `Closes #N` を書かない。helper が追記する
- GitHub MCP の `create_pull_request` / `issue_write` で Issue / PR を作らない。ラベルとテンプレート検査が抜ける
- `area:` の値はこのリポジトリの `.github/labels.yml` に従う。helper の usage 例にある `area:backstage` はテンプレート由来でこのリポジトリには存在しない
- commitlint は `origin/main` からの全コミットを検査する。push 前にローカルで通す
- Amazon Q Developer の未解決レビュースレッドはマージを `BLOCKED` にする。マージ前ではなく手順 8 のレビューで拾う
