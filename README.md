# felis-ai-chatbot

pgvector RAG チャットボット。PostgreSQL の Backup / Restore / Maintenance / Monitoring を設計・実装・検証する個人開発

このリポジトリは [idp-golden-path](https://github.com/kmryst/idp-golden-path) の
ゴールデンパステンプレート **service-baseline** から生成されました。
アプリケーションコードはまだ含まれていません。以下の運用基盤（ガードレール）が最初から有効です。

## このリポジトリに含まれるもの

| 資産 | 役割 |
| --- | --- |
| `CLAUDE.md` | AI Agent（Claude Code）向けの作業ルール入口 |
| `CONTRIBUTING.md` | Issue / Branch / Commit / PR / Label / 軽運用・厳密運用の正本 |
| `.github/labels.yml` | ラベル定義の正本（push で自動同期） |
| `.mise.toml` | ローカル開発ツールチェーン（Node.js 等）のバージョンの正本。CI pin との一致を Toolchain Version Check が検査する |
| `.github/workflows/` | PR Policy Check / Commitlint / Markdown Lint / Gitleaks Secret Scan / Sync Labels / Issue Template Check / Toolchain Version Check（実体は [idp-golden-path の reusable workflows](https://github.com/kmryst/idp-golden-path/tree/main/.github/workflows) をタグ固定 `@v1` で参照。更新は Dependabot のバージョンアップ PR で取り込む） |
| `.github/pull_request_template.md` / `ISSUE_TEMPLATE/` | PR / Issue テンプレート |
| `scripts/github/` | Issue / PR 作成・ラベル同期・ブランチ cleanup の helper |
| `docs/adr/` | Architecture Decision Record（0001 に生成経緯を記録済み） |
| `docs/operations/branch-protection.md` | main ブランチ保護の適用手順（初期状態では未適用） |
| `docs/operations/bootstrap.md` | Day 0 bootstrap の手順と検証証跡（本リポジトリ立ち上げの正本） |

## 初期セットアップ（生成後にやること）

1. ツールチェーンと依存をインストールし、ローカルで CI と同じチェックを実行できるようにする

   ```bash
   mise install   # .mise.toml の宣言どおりに Node.js 等を取得する
   npm ci
   npm run lint:md
   ```

   Terraform を導入する場合は `.mise.toml` のコメントに従って `terraform` を宣言し、
   Terraform を使う workflow の pin も同じ値に揃える。両者の一致は Toolchain Version Check が PR ごとに検査する。

2. ラベルが同期されていることを確認する（初回 push 時に Sync Labels workflow が実行される。
   手動同期は `./scripts/github/sync-labels.sh`）

3. 最初の PR をマージして CI（required checks 候補）の実行実績を作ったあと、
   [docs/operations/branch-protection.md](./docs/operations/branch-protection.md) の手順で
   main ブランチ保護を適用する

4. アプリケーションコードの技術選定は `docs/adr/` に ADR として記録してから実装を始める

## 開発フロー

Issue / PR 駆動開発を基本とします。詳細は [CONTRIBUTING.md](./CONTRIBUTING.md) を参照してください。

```bash
# Issue 作成
./scripts/github/create-issue-with-labels.sh --title "短い要約" \
  --body-file docs/issue-templates/feature_request.md \
  --type type:feature --area area:app --risk risk:low --cost cost:none

# PR 作成（draft で作成される）
./scripts/github/create-pr-with-labels.sh --title "feat: 変更の要約" \
  --body-file /path/to/filled-pr-body.md --issue <issue番号> \
  --type type:feature --area area:app --risk risk:low --cost cost:none --base main
```

## ドキュメント

- 設計判断: [docs/adr/](./docs/adr/README.md)
- Day 0 bootstrap 手順書: [docs/operations/bootstrap.md](./docs/operations/bootstrap.md)

本リポジトリは skeleton の手動コピーで立ち上げたため、Backstage TechDocs / Software Catalog 用ファイル
（`mkdocs.yml` / `catalog-info.yaml`）は含まれていません（[ADR-0001](./docs/adr/0001-bootstrap-by-manual-skeleton-copy.md)）。
