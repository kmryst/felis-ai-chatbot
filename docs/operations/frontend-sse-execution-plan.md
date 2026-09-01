# frontend デプロイ〜SSE 化の execution plan（#182）

[ADR-0027](../adr/0027-frontend-azure-deployment-and-public-surface.md)（公開面の構成）と
[ADR-0028](../adr/0028-chat-sse-response-contract.md)（SSE 応答契約）で固定した決定を実行に
移すための、作業順と起票判定の正本。外部レビュー 4 周を経た作業分解のうち、リポジトリに
正本化すべき「依存順」「未検証の前提の対応表」「起票トリガー」「production-readiness.md の
同時更新ルール」だけを本書が持つ。

> 実行前提: apply / destroy / az 書き込みは CLAUDE.md の禁止事項に従い**ユーザーの明示承認を
> 得てから**実行する。本書は計画の正本であって実行許可ではない。

## 役割分担

| 正本 | 持つもの |
| --- | --- |
| [ADR-0027](../adr/0027-frontend-azure-deployment-and-public-surface.md) / [ADR-0028](../adr/0028-chat-sse-response-contract.md) | 決定（公開面の構成・SSE 応答契約・撤回契約・retry 境界）。作業単位の内容はすべて ADR を参照する |
| [production-readiness.md](../production-readiness.md) | gap の存在と追跡先（横断の状態一覧） |
| 本書 | 作業順（依存順）と起票判定（どの実測・マージが揃ったらどの作業単位を起票するか） |

本書に書かないもの（同じ事実を 2 箇所に書くと必ず片方が腐る =
production-readiness.md 冒頭と同じ論点）:

- 実装 Issue の本文下書き（タイトル・受け入れ条件・ラベル・起票コマンド）。起票した瞬間に
  正本が Issue 側へ移り二重管理になる
- 作業単位ごとのスコープ説明文。ADR の決定の言い換えになる（作業単位は名前と一行の識別のみ）
- 数値（閾値・SLO target・compliance period）。決定はユーザーが SLO 文書の決定手順に従って行う

## 完了後の扱い

- 本書のすべての作業単位が完了し、最終段の SLO 正本改訂（実測記録の反映）がマージされた
  時点で本書は役目を終え、記録として残す（archive）
- 作業分解を再編する場合は後継文書を作成し、本書冒頭に supersede される旨と後継文書への参照を
  追記する（[day3-5-execution-plan.md](./day3-5-execution-plan.md) を
  [credit-window-execution-plan.md](./credit-window-execution-plan.md) が置き換えたのと
  同じ作法）

## 1. 依存順

作業単位は名前と一行の識別のみを書く。内容・受け入れの根拠は ADR-0027 / ADR-0028 を参照する
（ADR に記載のない作業単位は、その旨と識別に必要な事実だけを一行に書く）。

1. **ADR の固定（完了済み）** — ADR-0027 / ADR-0028（PR #181。マージ済み）
2. **実測 2 件**（相互に独立・並行可。Azure への書き込みはユーザー承認後）
   - **Issue #183** — 一時 Container App での Easy Auth principal header・revision 切替時間・
     ingress timeout の実測
   - **Issue #184** — Azure OpenAI streaming の content filtering 実挙動（chunk 到達順序）の実測
   - 実測結果を §2 の対応表で ADR の前提と突き合わせ、食い違いがあれば ADR 追記を先行させた
     上で、以降の作業単位を起票する（§3）
3. **並行波**（相互に独立。deploy を伴わない）
   - **backend `/chat` の SSE 化** — ADR-0028 の producer 側（wire format・raw stream から
     wire contract への変換（決定 5）・upstream incremental parser・retry 境界・共有 fixture）
   - **frontend の BFF・SSE parser・`/readyz` proxy** — ADR-0027 決定 2 / 3 / 8 / 10 と
     ADR-0028 の consumer 側（撤回処理を含む）
   - **`/chat` のレート制限（認証後段）** — ADR-0027 決定 1 の route dependency
   - **ingest CLI の embedding backfill 単独実行 mode** — destructive な seed diff-sync と
     再実行安全な backfill の CLI 分離（ADR に記載なし。backfill 単独再実行という回復経路の
     前提になる backend 変更）
   - **SLO 文書の SLI specification 改訂** — ADR-0028 決定 11 の 2 閾値 measurement semantics の
     正本化（測定意味論の変更。数値は決めない）
4. **apply セッション**（ユーザーの明示承認後。実行順は当該 PR の手順に固定する）
   - **seed Job / backfill Job の Terraform 化** — destructive な seed 投入 Job と再実行安全な
     backfill Job の分離（migrate Job と同型の Manual Job）
   - **`LLM_PROVIDER` の stub → azure-openai 切替** — backend への `LLM_PROVIDER` /
     `AZURE_OPENAI_*` 設定の導入。現状 `terraform/` と `.github/` に両者の設定は 0 件
     （2026-09-01 grep 実測）で、`backend/app/config.py` の既定 `"stub"` のまま Azure 上で
     動いている。ADR-0027 / ADR-0028 のどちらにも記載がなく、この作業単位を落とすと
     「frontend は繋がったが応答は stub のまま」で終わる
   - **実 embedding での backfill 実行** — 現行の stub provider の embedding は決定的なダミーで
     あり、実 provider での backfill を経るまでベクトル検索は実データに対して成立しない
   - **frontend Container App + Easy Auth（authConfigs）の作成** — ADR-0027 決定 6 の
     fail-closed bootstrap 順序（`chat_disabled = true` で開始し検証合格後にのみ有効化）で apply
5. **cutover** — backend の internal ingress への切替と `READYZ_URL` / `BACKEND_ORIGIN` の
   付け替え（ADR-0027 決定 1 / 3 / 8。Easy Auth 経由の疎通が実測で成立した後）
6. **synthetic transaction SLI** — supported client boundary での SLI 測定（共有 fixture による
   verifier 検証を含む）
7. **SLO 正本改訂（実測記録の反映）** — 実測で確定した limitation・rehearsal 記録・
   supported client 範囲の反映

## 2. 未検証の前提 → 実測 Issue → 失敗時の分岐

ADR-0027「影響」・ADR-0028「影響」の「未検証の前提」の列挙と 1 対 1 に対応させる
（ADR-0028 の ingress timeout は「影響」本文が「実測で確定させる」と明記した未解決事項で、
同じ扱いで本表に含める）。

| 未検証の前提（出典） | 潰す実測 Issue | 失敗時（前提と食い違った場合）の分岐 |
| --- | --- | --- |
| Easy Auth sidecar 稼働時の `X-MS-CLIENT-PRINCIPAL-*` header の上書き・除去挙動（ADR-0027 決定 10） | #183 (a) — 実測済み（[記録](../verification/easy-auth-container-app/observations.md) §3。無認証は除去・認証済みは実 principal に置換で、前提と一致し失敗分岐に入らない） | 除去されない場合はその事実を記録し、決定 10（深層防御）の位置づけを ADR-0027 追記で確定する |
| revision 切替の実時間と rotation 混在窓の実時間幅（ADR-0027） | #183 (b) — 実測済み（[記録](../verification/easy-auth-container-app/observations.md) §4。一時アプリ構成での 4 回実測。本番構成での値は未実測のまま） | 実測値でのみ主張する。rotation 運用（計画的 rotation・緊急時は `CHAT_DISABLED`）の limitation として SLO 正本改訂（§1 の 7）の入力にする |
| frontend の cold start 特性（ADR-0027 決定 9） | 実測 Issue なし（ADR-0027 が「予防採用であり実測しない」と決定済み） | 分岐なし（`min_replicas = 1` の予防採用のまま） |
| streaming content filtering の実挙動（partial text 送出後に `content_filter` 終端・`content_filter_results` の `error` が届く系列の実在と到達順序）（ADR-0028 決定 5 / 6） | #184 | 観測できた系列は fixture の実データ裏付けに使い、食い違いは決定 5 の表・撤回契約を ADR-0028 追記で改訂する。観測できない場合は不在を主張せず、防御的契約を維持する |
| Default mode で `finish_reason` の後・raw `[DONE]` の前に metadata chunk が届く系列の実在（ADR-0028 決定 5） | #184 | 同上（終端判定の `[DONE]` までの遅延は到達順に依存しない設計であり、観測結果は裏付けまたは決定 5 の表の改訂の入力） |
| 未知の chunk 形状の実在（ADR-0028 決定 5 の表の最終行） | #184 | 正当な未知形状が観測されたら決定 5 の表を ADR-0028 追記で改訂する |
| 撤回の UI 挙動は HTTP synthetic では検証できない（ADR-0028 決定 6） | 実測 Issue なし（parser テスト = fixture 系列 6 で担保。実ブラウザでの再現は別途の browser automation の範囲） | 分岐なし（verifier は分類のみという責務分担を維持） |
| ingress 既定 240 秒 timeout が総リクエスト時間かアイドル時間か（ADR-0028「影響」。公式文書内で記述が食い違い未解決） | #183 (c) — 実測済み（[記録](../verification/easy-auth-container-app/observations.md) §5。アイドル（バイト間）timeout として振る舞い、総リクエスト時間の分岐に入らない） | 総リクエスト時間なら長時間ストリームの扱いを ADR-0028 追記で改訂する。判別できない場合は観測事実のまま記録し断定しない。いずれも platform 制約であり SLI threshold の根拠に流用しない |

## 3. 起票トリガー

実装 Issue はいま一括起票しない。未検証の前提の実測が返るまで実装 Issue の受け入れ条件は
確定できないため、実測 → 計画へのレビュー → 起票の順とする。起票は CLAUDE.md のとおり
プラン提示とユーザー確認を経る。

| 作業単位（§1） | 起票トリガー |
| --- | --- |
| 実測 2 件 | 起票済み（#183 / #184） |
| backend SSE 化 / frontend BFF / レート制限 / SLI specification 改訂 | #183 / #184 の実測記録が揃い、§2 の対応表での突き合わせ（食い違いがあれば ADR 追記を先行）が完了した後 |
| ingest CLI の backfill 単独実行 mode | 実測に依存しない（応答契約・公開面に触れない）ため実測完了を待たずに起票できる。時期はユーザー判断 |
| seed / backfill Job の Terraform 化・`LLM_PROVIDER` 切替・実 embedding backfill・frontend + Easy Auth | 並行波の全 PR のマージ後（frontend image は BFF 実装込み、ops image は backfill 単独実行 mode 込みであることが前提） |
| cutover | frontend + Easy Auth の疎通（非管理者テストユーザーの成功試験。ADR-0027 決定 5）が実測で成立した後 |
| synthetic transaction SLI | SLI specification 改訂のマージ後、かつ frontend + Easy Auth の実測成立後（cutover 後が望ましい） |
| SLO 正本改訂（実測記録の反映） | apply セッション〜synthetic の実測記録が揃った後 |

## 4. production-readiness.md の同時更新ルール

本作業系列の各 PR は、解消・変更した gap に対応する
[production-readiness.md](../production-readiness.md) の該当行を**同じ PR で更新する**
（同文書の更新ルール「差分を解消した・新しく作った場合は、同じ PR で本書の該当行を更新する」を
本作業系列に適用する）。対象は少なくとも §1「`/chat` の公開面」（Easy Auth + BFF +
internal ingress の実装・cutover 時）と §7「フロントエンドの配信」（frontend デプロイ時）、
および §4「外形監視の観測密度」「監視・アラート」（synthetic transaction の実装で事実が
変わる時）の各行である。
