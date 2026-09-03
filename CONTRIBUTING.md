# Contributing Guide

本プロジェクトへの貢献ガイドです。
このファイルを Issue / Branch / Commit / PR / Label / 軽運用・厳密運用の共通運用ルールの正本とします。

このリポジトリは [idp-golden-path](https://github.com/kmryst/idp-golden-path) の
ゴールデンパステンプレート（service-baseline）から生成されています。
運用モデルは [terraform-hannibal](https://github.com/kmryst/terraform-hannibal) /
[ticket-c2c-platform](https://github.com/kmryst/ticket-c2c-platform) で確立された
軽運用 / 厳密運用を分ける GitHub Flow を踏襲します。

## 開発フロー

Issue / PR 駆動開発を基本とします。

### 正規コマンド

Issue と PR の作成は、原則として以下のヘルパーを使います。

```bash
# Issue
./scripts/github/create-issue-with-labels.sh ...

# PR
./scripts/github/create-pr-with-labels.sh ...
```

PR マージ後のブランチ整理には次を使います。

```bash
./scripts/github/cleanup-merged-pr-branch.sh <PR番号>
```

### 1. Issue 作成

新しい機能追加、検証、ドキュメント更新は、原則として Issue から始めます。
軽運用でも Issue は必須です。ただし簡潔で構いません。

`--body-file` には `docs/issue-templates/feature_request.md` をそのまま渡さず、テンプレートを埋めたコピーを別ファイルとして作成して渡します。

```bash
./scripts/github/create-issue-with-labels.sh \
  --title "短い要約" \
  --body-file /path/to/filled-issue-body.md \
  --type type:feature \
  --area area:app \
  --risk risk:low \
  --cost cost:none
```

Issue テンプレート:

- `.github/ISSUE_TEMPLATE/feature_request.yml`: Web UI 用
- `docs/issue-templates/feature_request.md`: CLI 用 `--body-file`

Issue に必要な最小項目:

- `目的`
- `対象`
- `受け入れ条件`

Issue 必須ラベル:

- `type:*`: ちょうど 1 つ
- `area:*`: 1 つ以上、複数可
- `risk:*`: ちょうど 1 つ
- `cost:*`: ちょうど 1 つ

AI Agent を使う場合は、いきなり起票せずに先に Issue プランを提示し、人間が確認してから起票します。

### 2. ブランチ作成

Issue に基づいて、最新の `main` からブランチを作成します。

```bash
git switch main
git pull --ff-only origin main
git switch -c <issue番号>-<kebab-case要約>
```

### 3. 実装・コミット

コードやドキュメントを変更し、Conventional Commits 形式でコミットします。

```bash
git add <対象ファイル>
git commit -m "type: 変更内容の説明"
```

許可する type:

- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント修正
- `refactor`: リファクタリング
- `test`: テスト追加・修正
- `chore`: その他雑務
- `ci`: CI/CD 変更
- `infra`: インフラ変更

コミットメッセージ形式:

- `<type>: <summary>`
- `<type>(<scope>): <summary>`

`scope` は任意です。`summary` は日本語を許容します。
`wip`、`fix` のみ、`update files` のような曖昧なコミットメッセージは使いません。

### 4. Push

作業ブランチを push します。

```bash
git push -u origin <branch>
```

branch protection 適用後は `main` への direct push はできません。必ず PR を経由します。

### 5. Pull Request 作成

PR はテンプレートと helper を使って作成します。

`--body-file` には `.github/pull_request_template.md` をそのまま渡さず、テンプレートを埋めたコピーを別ファイルとして作成して渡します。

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

この helper は PR 本文へ `Closes #<issue番号>` を自動追記し、PR を作成します。

PR タイトルも Conventional Commits 形式にします。

PR 本文には、次のいずれかの Issue 参照が必要です。

- `Closes #<issue番号>`
- `Fixes #<issue番号>`
- `Refs #<issue番号>`

helper を使う場合はこの要件が上記の自動追記で満たされるため、`--body-file` には自分で書きません。
書くと PR 本文に `Closes` が 2 回現れます。

### 6. マージ後 cleanup

```bash
./scripts/github/cleanup-merged-pr-branch.sh <PR番号>
```

## 運用モード

Issue 起票前プランと PR 作成前プランで、ラベル・変更対象・変更内容から軽運用 / 厳密運用を判定します。
判断に迷う場合は厳密運用として扱います。

### 軽運用

以下のような変更のうち、厳密運用の条件に該当しないものは軽運用で進めます。

- README / docs の軽微な更新
- コメント修正・文言修正
- 影響範囲が限定的な軽微修正
- `risk:low`
- `cost:none` / `cost:small`

軽運用でも `Issue -> Branch -> PR` の流れは維持します。

### 厳密運用

以下のいずれかに該当する変更は厳密運用で進めます。

- `risk:medium` / `risk:high`
- `cost:medium` / `cost:large`
- `.github/workflows/**`
- `scripts/github/**`
- `terraform/**`
- branch protection などリポジトリ設定の変更
- Azure リソース、Entra ID RBAC、Managed Identity、OIDC (federated credential)、Key Vault、Network、Security に関わる変更
- deploy / destroy に関わる変更
- ロールバックを考える必要がある変更

厳密運用 PR では、PR 本文の `ロールバック` に実質的な内容を書きます。

## ラベル管理

ラベル定義の正本は `.github/labels.yml` です。

```bash
./scripts/github/sync-labels.sh
```

`main` への push 時は `sync-labels.yml` workflow が自動同期します。

## 設計判断の記録（ADR）

トレードオフを伴う設計判断は `docs/adr/` に ADR として記録します。
書き方と運用ルールは `docs/adr/README.md` に従います。

## チェックリスト

- [ ] 最新の `main` を取得したか
- [ ] Issue を作成または確認したか
- [ ] ブランチ名が `<issue番号>-<kebab-case要約>` 形式か
- [ ] コミットメッセージが Conventional Commits 形式か
- [ ] PR 作成時に helper へ `--issue <issue番号>` を渡したか（`Closes #XX` は helper が自動追記するため本文には書かない）
- [ ] 必須ラベル `type / area / risk / cost` を付けたか

## 関連ドキュメント

- [README.md](./README.md)
- [CLAUDE.md](./CLAUDE.md)
- [PR Template](./.github/pull_request_template.md)
- [Labels](./.github/labels.yml)
- [ADR](./docs/adr/README.md)
