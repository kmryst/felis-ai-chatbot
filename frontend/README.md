# frontend

Next.js（TypeScript / App Router）のチャット UI。
起動手順・環境変数はリポジトリ直下の [README.md](../README.md) を参照。

## ローカルのチャット画面検証（Issue #273）

Playwright / Chromium で通常回答と資料なし応答を各 1 回確認する。
既存の Chat UI → `/api/chat` の BFF → 共有 fixture を返す HTTP stub を通す。

```bash
cd frontend
npm ci
npx playwright install chromium
npm run test:sli-local
```

Linux で Chromium の OS 依存パッケージが不足する場合は、
`npx playwright install --with-deps chromium` でインストールする。
同じ checkout で動いている `next dev` は事前に停止する（`.next/dev/lock` を共有するため）。
frontend の `127.0.0.1:13173` と stub の `127.0.0.1:18173` は検証専用の固定ポートで、
既存 server は再利用しない。起動・終了は Playwright が管理する。

結果は Git 管理対象外の `e2e-results/sli-local/` に保存する。次回実行で上書きされるため、
保持する結果は実行前に別の場所へコピーする。
これは画面操作の検証用で、SLI の時刻計測・再計算・失敗検出の検証は後続段階。
認証設定、保存物、確認範囲は
[検証記録](../docs/verification/sli-local-prototype/observations.md) を参照。
