# SLI ローカル prototype の検証記録（Issue #273）

[Issue #273](https://github.com/kmryst/felis-ai-chatbot/issues/273) の最初の区切りとして、
Playwright で実際のチャット画面から通常回答・資料なし応答を確認する環境を用意する。
Issue 全体のうち今回の対象は **1. ローカル実行環境**。
同 Issue に含まれる **2. 計測・保存と再計算**、**3. 失敗検出の検証** は後続段階であり、
この画面検証だけで Issue #273 を完了とはしない。
段階番号は今回の作業の区切りを表し、
[設計書の作業分割](../../observability/slo/sli-measurement-design.md#作業分割と完了条件)
にある Azure prototype 以降の番号とは異なる。

## 実行経路と条件

```text
Playwright / Chromium
  → Chat UI (http://127.0.0.1:13173/)
  → native fetch /api/chat → 既存 BFF
  → HTTP stub (http://127.0.0.1:18173/chat)
  → 共有 fixture の SSE → 既存 SSE consumer → 回答表示
```

- 各シナリオは新しい BrowserContext で開始し、画面の入力欄と送信ボタンを操作する。
  Playwright の route / fulfill による SSE の代理取得・置換は行わない。
- Playwright の実行設定で `execution_purpose = validation` を実行前に固定する。
- ローカル frontend は `BACKEND_ORIGIN=http://127.0.0.1:18173`、`CHAT_API_KEY` は空、
  `BFF_PRINCIPAL_CHECK_DISABLED=true` で起動する。実 LLM・Azure credential は使用しない。
  この検証では Easy Auth と BFF の principal 検証は観測対象に含まれない。
- 固定ポートの既存 server は `reuseExistingServer=false` により再利用しない。
  frontend と stub は loopback で待ち受け、Playwright が起動・終了を管理する。

## 再現手順

リポジトリのルートから実行する。

```bash
cd frontend
npm ci
npx playwright install chromium
npm run test:sli-local
```

Linux で Chromium の OS 依存パッケージが不足する場合は、
`npx playwright install --with-deps chromium` を実行する。
実行前に `13173` / `18173` 番ポートを空け、同じ checkout で起動した `next dev` を停止する。
別ポートの `next dev` も `.next/dev/lock` を共有するため、同時には起動できない。

## 入力・期待結果と実行結果

2026-09-17 にローカルで実行。対象は `273-sli-local-prototype` の
`f67fcb6` を基点とする未コミット差分。Node.js `24.18.0`、
Playwright `1.63.0`、Chromium `153.0.8010.12` を使用した。

| シナリオ | 入力 | 共有 fixture | 期待結果 | 実行結果 |
| --- | --- | --- | --- | --- |
| normal | `SLI local validation: normal` | `series-1-normal.json` | `message` の text を連結した通常回答が表示される | 成功。最終本文が完全一致 |
| notice | `SLI local validation: notice` | `series-2-guard-notice.json` | `notice` の text と一致する資料なし応答が表示される | 成功。最終本文が完全一致 |

両シナリオで HTTP 200 / `text/event-stream`、当該回答要素の可視性、fixture との text の完全一致、
送信状態の終了、チャットにエラーが表示されないことを確認した（2 tests passed）。
本文の一致は送信終了後に検査する。エラー検査はチャット内の `role=alert` を対象とし、
Next.js の route announcer と区別する。
これは最終的な画面状態の検証であり、各 SSE event の受理時刻や event ごとの描画を証明するものではない。

同じ作業差分で、frontend の `npm test`（既存 99 件）、`npm run lint`、
`npx tsc --noEmit`、`npm run build`、`npm run check:bundle-secrets` が成功した。
リポジトリルートの `npm run lint:md` と `git diff --check` も成功。
テスト終了後、検証用の両ポートに待受プロセスが残っていないことを確認した。

## 保存物

保存先は Git 管理対象外の `frontend/e2e-results/sli-local/`。
次回実行で上書きされるため、保持が必要な結果は別の場所へコピーする。

| パス（保存先からの相対パス） | 内容 |
| --- | --- |
| `results.json` | Playwright の結果と実行設定 metadata |
| `artifacts/**/chat.png` | 各シナリオの検証後の画面 |
| `artifacts/**/ui-validation.json` | 入力、fixture、期待 text / 表示 text、HTTP 応答、browser version、ローカル認証設定 |

これらは UI 検証の記録であり、
[SLI measurement record schema](../../observability/slo/sli-measurement-schema.md) に従う
measurement / receipt record は未実装。Playwright の test duration は SLI の latency に使用しない。

## 後続段階

- 同一 page の時計による fetch 直前・SSE event 受理・失敗・DOM 検証の時刻計測、
  `attempt_id` と回答要素の対応付け、raw record の保存、派生 latency の再計算。
- strict SSE verifier、切断・不正 stream・描画不一致・timeout 等の反例による失敗検出の検証、
  schema 全項目の取得可否の整理。
- Azure の実認証、保存、定期実行、baseline 収集と SLO 数値の決定は、Issue #273 後の作業。

## 実装と参照

- [Playwright 実行設定](../../../frontend/playwright.config.ts)
- [Chat UI の browser test](../../../frontend/e2e/chat.pw.mts)
- [HTTP stub](../../../frontend/e2e/support/chat-stub.mjs) / [シナリオ](../../../frontend/e2e/support/scenarios.mjs)
- [SSE 共有 contract / fixture](../../contracts/chat-sse/README.md)
- [Playwright: Web server](https://playwright.dev/docs/test-webserver): test 実行時の server 起動・終了と再利用設定
