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
- `.claude/skills/issue-to-pr/SKILL.md`: Issue → PR の手順と落とし穴をまとめた skill。規約の正本は `CONTRIBUTING.md` と `CLAUDE.md` であり、食い違う場合は正本を優先して skill を直す。

内容が衝突する場合は、共通運用は `CONTRIBUTING.md` を優先する。

## 作業開始前に必ず読むファイル

1. `CONTRIBUTING.md`
2. `README.md`
3. 対象 Issue がある場合は `gh issue view <issue番号>`
4. 変更対象ファイル

## 開発フロー

Issue / PR 駆動開発を必ず守る。
順序: Issue 確認 → ブランチ作成 → 実装前計画提示 → 実装 → 検証 → コミット前停止 → コミット → push → PR → review → merge → cleanup。

Issue / PR の作成には `scripts/github/` の helper スクリプトを使う。
GitHub MCP の `create_pull_request` / `issue_write` は使わない。
helper が必須ラベル 4 種の付与と、Issue 本文のテンプレート検査（`create-issue-with-labels.sh` のみ）を担保しているため。
コマンド例は `CONTRIBUTING.md`、オプションの正本は各 helper の `--help`。

この一連の手順は `.claude/skills/issue-to-pr/SKILL.md` にまとめてあり、`/issue-to-pr` で呼べる。

### Issue 作成

Issue は起票前にプランを提示してユーザーに確認してもらう。

`--body-file` には `docs/issue-templates/feature_request.md` をそのまま渡さず、テンプレートを埋めたコピーを別ファイルとして作成して渡す。
必須見出しは `## 目的` / `## 対象` / `## 受け入れ条件`。検査条件の詳細は `CONTRIBUTING.md` の `### 1. Issue 作成`。

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
`--body-file` に `Closes #<issue番号>` を書かない。helper が `--issue` から本文末尾に自動追記する。
必須ラベル 4 種と Issue 参照の要件は `pr-policy-check` が検査する。詳細は `CONTRIBUTING.md` の `### 5. Pull Request 作成`。

### マージ後 cleanup

```bash
./scripts/github/cleanup-merged-pr-branch.sh <PR番号>
```

## 設計判断の記録

トレードオフを伴う設計判断は `docs/adr/` に ADR として記録する。
書き方と運用ルールは `docs/adr/README.md` に従う。番号は ADR を追加する PR の時点で確定する。

## コミットメッセージとローカル検証

コミットメッセージは `CONTRIBUTING.md` の Conventional Commits ルールに従う。
push 前に CI と同じ markdownlint / commitlint をローカルで通す。コマンドは `CONTRIBUTING.md` の `## ローカル検証`。

## 禁止事項

以下は例外なく実行しない。ユーザーから明示的に指示された場合でも実行せず、
必要な場合はユーザー自身が実行する。

- secret / credential 値の出力
- `.env` ファイルのコミット
- `git push --force`
- `main` ブランチへの direct push
- GitHub MCP の `delete_repository`（リポジトリの削除）
- GitHub MCP の `push_files` / `create_or_update_file` / `delete_file`（ブランチと PR を経由しないリモートへの直接書き込み）
- GitHub MCP の `merge_pull_request`（PR のマージ。`gh pr merge --squash` を使う）

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
| レビュー | レビュー結果と未解決スレッドの有無を提示してから |
| PR のマージ（`gh pr merge --squash`） | マージ対象と CI の状態を提示してから |
| ブランチ削除 | cleanup コマンド案を提示してから |

## ラベル

必須ラベル 4 種（`type` / `area` / `risk` / `cost`）の値は `.github/labels.yml` が正本。
要件は `pr-policy-check` が検査する。詳細は `CONTRIBUTING.md`。
