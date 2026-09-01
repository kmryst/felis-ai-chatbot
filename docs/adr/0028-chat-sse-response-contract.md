# ADR-0028: /chat の SSE 化と応答契約の固定

## ステータス

Accepted

## 日付

2026-09-01

## 改訂履歴

- 2026-09-01: 初版（PR #181。ステータス Proposed）
- 2026-09-01: 実測（Issue #183 / #184）を反映した追記改訂（Issue #190）。決定 5 の表の
  error field 検査を単数形・複数形の明示列挙へ拡大し、既知の chunk 形状への未知 field 同乗の
  扱いの行を追加。決定 6・決定 9（系列 3 / 6）へ実測形状を反映。「影響」の ACA ingress
  240 秒 timeout の未解決事項をアイドル（バイト間）timeout と実測で決着。あわせてステータスを
  Proposed から Accepted へ変更した（初版が「未検証の前提」とした実測がすべて返って本文へ
  反映され、後続実装が本契約を実装対象とするため）

## 決定内容

### 1. `POST /chat` を SSE（`text/event-stream`）へ変更する

backend の `POST /chat` は、現行の単一 JSON 応答（`{"reply": "..."}`）から
**SSE（`text/event-stream`、UTF-8）** へ変更する。client（BFF 経由の supported client）は
`EventSource` を使わない。`EventSource` は GET 固定でカスタムヘッダも扱えないため
（出典: <https://html.spec.whatwg.org/multipage/server-sent-events.html> ）、
**`fetch` + `response.body.getReader()`** で byte stream を読み、本契約の parser で復元する。

### 2. wire format の完全固定

- 各 event は `event:` 行 1 本 + `data:` 行 1 本で構成する
- **`data` は必ず JSON object** とする（例: `event: message` / `data: {"text":"..."}`）。
  LLM 出力に含まれる改行は JSON 文字列内へ escape されるため、SSE の行指向 framing
  （WHATWG "the event stream format"。訳: event stream の書式）を壊さない
- event の種類・順序・多重度を**文法として固定**する:
  - 通常応答: `message`（1 回以上）→ `done`（1 回）
  - guard 応答: `notice`（1 回。`NO_CONTEXT_NOTICE` 全文）→ `done`（1 回）
  - 失敗: `message`（0 回以上）→ `error`（1 回）で終端し、`done` を出さない
  - 終端 event（`done` または `error`）はストリームに必ず 1 回・最後にのみ現れる。終端 event
    なしのストリーム終了は契約違反であり、client は失敗として扱う
- `done` の data は終端メタデータの JSON object とする（最小は `{}`）。consumer は未知の field を
  無視する（前方互換）
- `error` の data は error class のみを持ち、詳細メッセージ（プロンプト断片・upstream 応答本文）
  を含めない。class の語彙は既存の LLM エラー分類（`backend/app/llm/client.py` の
  timeout / rate limit / server error / bad request）に対応する識別子に **`content_filter`** を
  加えたものとする（識別子の表記は共有 fixture で固定する）
- ストリーム開始**前**の失敗は SSE を開始せず、現行どおりの HTTP status で返す
  （ゲートの 404 / 401、validation の 422、LLM 失敗の 502、検索失敗の 503。
  `backend/app/main.py` の現行分類を維持）
- client 切断時、backend は provider stream を打ち切る（課金と接続の垂れ流しを作らない）

### 3. content event は `message` と `notice` の 2 種

「content event」= `message` または `notice`。ハルシネーション・ガードが発火する経路
（`backend/app/main.py` の `/chat` が `backend/app/rag.py` の類似度を閾値と比較し、閾値未満なら
LLM を呼ばず `NO_CONTEXT_NOTICE` を返す。ADR-0010）も **`notice` という content event を
1 件持つ**。SLO 文書の good event 定義は「no-context notice も client が受信して render
できれば journey 完了」なので、guard 経路が「最初の content event」を持たない定義にすると
SLI と食い違う。content event が 1 件しかないストリームでは content event **間**の間隔条件は
空適用となるが、決定 11 のとおり threshold 2 は「最後の content event → 終端 event」の区間にも
適用されるため、`notice` から `done` までの時間が無制限になることはない。

### 4. `message` は非空の renderable text を要求する

`message` の `text` は**非空文字列**でなければならない。空文字列の `text` を持つ `message` は
契約違反であり、producer は送出してはならず、parser / verifier は「最初の content event」として
数えてはならない（空 event で threshold 1 だけ満たす抜け道を作らない）。

### 5. Azure OpenAI raw stream から wire contract への変換（producer の義務）

backend は Azure OpenAI の chat completions stream（raw stream）を次の表のとおり wire contract
へ変換する。

| raw stream の chunk | wire 出力 |
| --- | --- |
| role のみの delta（content なし） | 出力しない（実測では厳密な role のみの形は観測されず、常に次行との複合形で到達した。下記の改訂注記） |
| content が空文字列または null の delta | 出力しない |
| `choices` が空の chunk（prompt annotation・usage 等のメタ chunk） | 出力しない（metadata として検査のみ） |
| content を持たず choice 内に `content_filter_results`（`error` なし）を持つ annotation chunk | 出力しない（metadata として検査のみ） |
| content が非空の delta | `message` |
| `finish_reason: "stop"` の chunk | それ自体では wire 出力しない。**`done` の送出候補として記録し、raw `[DONE]` まで後続 chunk の metadata 検査を続ける**（下記） |
| `finish_reason: "content_filter"` の終端 | `error`（class: `content_filter`）。`done` なし |
| chunk 内の error field を検出: **複数形 `content_filter_results` の `error`、または単数形 `content_filter_result` の `error`**（検査対象の field 名はこの 2 つを明示列挙する。2026-09-01 追記改訂: 実測では単数形のみが届いた。下記の改訂注記） | **`finish_reason` の値・`stop` の前後に関わらず** `error`（class: `content_filter`）。`done` なし（下記 6） |
| 上記いずれかの行に当てはまる chunk に、上記の error field 以外の**未知 field** が同乗 | **未知 field は無視し、chunk 自体は該当行のとおり扱う**（未知 field の同乗を error 終端の条件にしない。2026-09-01 追記改訂。下記の改訂注記） |
| raw `[DONE]` | ここまでに `error` 条件を検出しておらず、`finish_reason: "stop"` を観測済みなら `done`。`stop` 未観測なら終端 event なしの切断として `error`（class: server error 系） |
| 上記以外の未知の chunk 形状（chunk 全体が本表のどの行にも当てはまらない） | `error`（class: server error 系）で終端する（未知形状を握りつぶして「良い応答」に見せない fail-closed 側の選択。実 stream で正当な未知形状が観測されたら本表を追記改訂する） |

**改訂注記（2026-09-01 追記。入力:
[Azure OpenAI streaming 実測記録](../verification/azure-openai-stream/observations.md)
§3〜§6）**:

- **error field の明示列挙（検査対象の拡大）**: 実測（run3-long）では、error は初版の表が指す
  複数形 `content_filter_results` ではなく**単数形 field `content_filter_result` の `error`**
  （`code: "content_filter_error"`, `message: "The contents are not filtered"`）として届き、
  同一 chunk 内の複数形は空 object `{}` のままだった。初版の表を字義どおり実装すると複数形の
  検出行が発火せず、fail-closed が成立しない。よって単数形・複数形の両 field 名を明示列挙して
  検査対象とする。この改訂は検査対象の**拡大のみ**であり、複数形の検出は維持する（複数形の
  `error` が観測できなかったことを根拠に検査対象から外さない。「影響」の観測環境と限界を参照）
- **未知 field の無視（実測された正常系を守る根拠）**: 実測では既知の chunk 形状への未知 field
  の同乗が常態だった。観測された未知 field は 4 種 — (a) 単数形 `content_filter_result` の
  `error`、(b) 全 chunk の `obfuscation`、(c) usage chunk の `latency_checkpoint` / `routing`、
  (d) `stream_options.include_usage` opt-in 時に全 chunk へ付く `usage: null`。特に run3-long
  では全 1683 chunk に単数形 error と `obfuscation` が同乗したまま `finish_reason: "stop"` で
  正常終端しており、「既知形状への未知 field 同乗」自体を error 終端の条件にすると、この実測
  された系列が丸ごと落ちる（`obfuscation` だけでも全応答が error 終端になる）。よって error を
  運ぶ field は上記の明示列挙で検査し、それ以外の未知 field は無視する。**未知の chunk 形状**
  （field ではなく chunk 全体が表のどの行にも当てはまらない場合）に対する fail-closed は維持する
- **role delta の実形状**: 「role のみの delta（content なし）」は厳密な形では一度も観測されず、
  先頭 delta は常に `role` + `content: ""` + `refusal: null` の複合形（7/7 回）で、表の 1 行目と
  2 行目の複合として到達した。どちらの行でも「出力しない」なので wire 出力は変わらないが、
  fixture（決定 9 の系列 3）はこの実測形状を使う
- **per-chunk `content_filter_results` の実形状**: 値はほぼ常に空 object `{}` で、一部 chunk で
  のみ `protected_material_code` が付いた。公式 sample にあるカテゴリ別
  （hate / sexual / violence / self_harm）の per-chunk 結果は一度も観測されなかった。実装は
  カテゴリ別の値が埋まる前提を置いてはならない（検査は error field の有無で行い、空 `{}` を
  正常として扱う）
- **終端判定を `[DONE]` まで遅延させる設計の実データ裏付け**: `stream_options.include_usage` を
  opt-in した 4 呼び出しすべてで、usage chunk（`choices: []`）が `finish_reason` の後・raw
  `[DONE]` の前に到達した。「`finish_reason` 後・`[DONE]` 前に chunk が届く」経路は Default
  mode に実在し、本表の終端遅延の実データ裏付けになる（opt-in なしの自発的な metadata chunk は
  観測できなかった。不在は主張しない）

**wire の `done` は raw `[DONE]` の受信後にのみ送出する**。公式の sample stream には
`finish_reason: "stop"` の**後**に annotation chunk が届いてから `[DONE]` になる系列がある
（出典: <https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-streaming> の
sample response stream。sample は Asynchronous Filter のものだが、Default での chunk 到達順序は
公式に保証されていない）。`stop` の時点で `done` を出すと、post-`stop` の
`content_filter_results` の `error` を fail-closed にできないため、終端判定を `[DONE]` まで
遅延させる。

guard 経路（LLM を呼ばない）は raw stream を持たず、`notice` → `done` を直接生成する。

### 6. `content_filter_results` の `error` は fail-closed（撤回契約つき）

前提を正確に記録する。Default streaming filtering（決定 7 のとおり本サービスの採用 mode）では、
content は buffer 単位で filter の検査を受けてから返却される（"Content is fully vetted
according to the guardrail policy before it's returned to the user"。訳: content は guardrail
policy に従って完全に検査されてからユーザーへ返却される。出典:
<https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-streaming> ）。
未検査 text が先行表示され、遅延した filter signal が後追いするのは **Asynchronous Filter の
性質**であり、Default を採用する本契約の根拠にはしない。それでも撤回契約が必要な理由は次の
2 つである。

- Default でも、検査を通過した先行 buffer の text が表示された**後**に、後続 buffer が block
  されて応答が `finish_reason: "content_filter"` で打ち切られる系列は起こる（buffer 単位の
  検査通過は応答全体の完了を保証しない）。表示済み partial text は「打ち切られた応答の断片」
  として画面に残る
- `content_filter_results` の `error` は「**filter が evaluation を完了できなかった**」ことを
  示す（"details about an error that prevented content filtering from completing its
  evaluation"。訳: content filtering が evaluation を完了することを妨げた error の詳細。出典:
  <https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/chat> ）。この場合、
  表示済み text が検査を通過したと主張できない。`error` と表示済み chunk の到達順序は公式に
  保証されておらず未検証のため、**到達順に依存しない防御的契約**として撤回を要求する

- producer: `content_filter_results` の `error` を検出したら、`finish_reason` の値に関わらず
  `done` を出さず `error`（class: `content_filter`）で終端する（filter の判定が得られなかった
  応答を完了扱いにしない = fail-closed。外部レビューで 3 周連続で指摘され確定した論点）。
  送出済みの `message` を取り消す撤回 event は wire に導入しない
- consumer（supported client）: `error` の class が `content_filter` の場合、**表示済みの
  partial text を画面から撤回し、固定文言（「応答が content filter を通過したことを確認
  できなかったため、表示を取り消しました」）に置換する**。この文言は「filter による打ち切り」
  （`finish_reason: "content_filter"`）と「filter の evaluation 不能」
  （`content_filter_results` の `error`）の両方を偽りなく覆う中立表現として選ぶ（後者を
  「filter により打ち切られた」と表示するのは公式の意味論と食い違うため）。他の class の
  `error` では partial text を保持し「応答は完了しませんでした」を付す。撤回を filter 起因に
  限るのは、filter を通過したと確認できない partial text を画面に残さないためであり、
  通常障害の partial text はユーザーに残す方が有用なため

**改訂注記（2026-09-01 追記）**: 実測（run3-long）で観測された単数形 `content_filter_result` の
`error`（`message: "The contents are not filtered"`）は、本決定が引用する公式意味論
（filter が evaluation を完了できなかった）に該当する実データと解される。この系列は全 1683
chunk に error が同乗したまま `finish_reason: "stop"` で正常終端しており、字義どおり
「filter の判定が得られなかったまま完了扱いで届く応答」である。決定 5 の表の改訂（単数形の
明示列挙）により、この系列は本決定の fail-closed・撤回契約の対象になる（producer は `done` を
出さず `error`（class: `content_filter`）で終端し、consumer は表示済み partial text を撤回
する）。同一プロンプトの再実行では再現しない間欠事象であることが記録されている
（[実測記録](../verification/azure-openai-stream/observations.md) §5-1・§9）。

### 7. asynchronous content filter は採用しない

Azure の asynchronous filter（annotation が本文より遅れて届く opt-in mode）は採用せず、
既定の streaming filtering のままとする。採用すると「表示後に filter signal が届く」経路が
恒常化して遡及 redaction の契約が別途必要になり、SLI の good event 判定にも遅延した合否が
混入するため。

### 8. incremental parse 要件は双方向

任意の byte 境界で分断された stream から同一の event 列を復元できることを、**両方向の parser** に
要求する。

- downstream: BFF・client・synthetic verifier が backend の SSE を読む方向
- upstream: backend の transport（`backend/app/llm/client.py`）が Azure OpenAI の SSE stream を
  読む方向（httpx が返す任意長の chunk 断片からの復元）

分断点には少なくとも、UTF-8 マルチバイト文字の途中・`data:` プレフィクスの途中・event 区切りの
空行の直前後を含める。分断パターンの試験データは共有 fixture に同梱し、無分割時と同一の結果に
なることをテストで検証する。

### 9. 共有 contract fixture

`docs/contracts/chat-sse/`（配置は実装 PR で確定。役割 = backend・frontend・synthetic の 3 者が
参照する単一正本）に、canonical wire example と系列 fixture を置く。系列には最低限次を含める。

1. 正常（`message` 複数 → `done`）
2. guard notice（`notice` → `done`）
3. role delta 混在の raw stream とその wire 出力（2026-09-01 追記改訂: 実測の先頭 delta は
   role のみではなく `role` + `content: ""` + `refusal: null` の複合形（7/7 回）。fixture は
   この実測形状を使い、role のみの形も仕様上の想定として維持する）
4. 空・null content 混在の raw stream とその wire 出力（実測では空文字列 content は先頭 delta に
   同乗する形でのみ出現。null content・本文途中の空 content は観測がなく、仕様上の想定として
   維持する）
5. `content_filter` 終端（`finish_reason: "content_filter"`）
6. partial message 複数 → error field の検出（撤回契約の検証用。2026-09-01 追記改訂:
   複数形 `content_filter_results` の `error` の系列に加えて、**実測された単数形
   `content_filter_result` の `error` が全 chunk に同乗したまま `finish_reason: "stop"` に至る
   系列（run3-long）** を含め、どちらも `done` なし・`error`（class: `content_filter`）終端・
   撤回になることを検証する）
7. `message` 複数 → `finish_reason: "stop"` → **post-`stop` の `content_filter_results` の
   `error`** → raw `[DONE]`（`stop` 観測後も `done` を抑止して `error` 終端にすることの検証用。
   決定 5 の表の「終端判定は `[DONE]` まで遅延」の裏付け）

このほか、途中切断（終端 event なしの切断）系列と、決定 8 の byte 分断パターン試験データを
同梱する。**fixture 5〜7 は、raw fixture → upstream parser → producer → client parser →
synthetic verifier の全段で「`done` なし・`error` 終端・（class `content_filter` なら）撤回・
verifier の bad 判定」になることをテストの必須条件とする**。backend のテスト・frontend parser
のテスト・synthetic verifier がすべて同じ fixture を
読むことで、3 者の契約解釈の分岐を構造的に防ぐ。CI から実 LLM を呼ばない決定（ADR-0004）は
維持され、raw stream 系列の fixture がスタブ側の入力になる。

### 10. LLM retry 境界の変更

現行の `LLMClient` は `RetryConfig`（既定 `max_attempts = 3`、`timeout_seconds = 10.0`。
`backend/app/config.py` の `LLM_MAX_ATTEMPTS` / `LLM_TIMEOUT_SECONDS` で上書き）で呼び出し全体を
`asyncio.wait_for` に包み、retryable な失敗を再試行する。この構造は**ストリーミング開始後には
適用できない**。部分出力を client へ送出した後に upstream を再試行すると、同じ内容が重複して
届く（wire 契約にも SLI にも「重複を除去する」規定はなく、作るべきでもない）。

よって **retry は「最初の content event を受信する前」に限る**という境界を決定として固定する。
最初の content 相当 delta を受信した後の upstream 失敗は、retry せず `error` event で終端する
（決定 2 の失敗系列）。1 試行あたりの timeout がストリーミングの各局面（接続確立・token 間隔）で
何を意味するかの再定義は、閾値の数値決定（下記 11 のとおり本 ADR では決めない）と一体のため、
本 ADR では境界のみを決め、値と適用局面の詳細は SLO 側の決定と実装 PR に委ねる。

### 11. SLI との関係（measurement semantics は本 ADR の prospective decision。数値は決めない）

SLO 正本（`docs/operations/slo/slo-document.md`）の現行 SLI specification は「eligible user
request のうち、SLI threshold 以内に critical user journey を完了した request の割合」であり、
**単一 threshold の journey 完了型**である。次の 2 閾値の measurement semantics は SLO 正本には
まだ存在せず、**本 ADR がストリーミング化に先行して決める prospective decision** として記録する
（SLO 正本への正本化は別 PR。「影響」参照。数値決定はユーザー。実測は妥当性検証にのみ使う）。

> eligible event のうち、supported client が最初の content event を〈threshold 1〉以内に受信し、
> 以後 content event の間隔、および最後の content event から有効な終端 event までの間隔が
> 〈threshold 2〉を超えることなく、有効な終端 event を受信して parse / render できたものの割合

- threshold 2 は content event 間だけでなく、**最後の content event から終端 event までの区間にも
  適用する**。この適用がないと、content event が 1 件のストリーム（guard 経路の
  `notice` → `done`）では間隔条件が空適用となり、最終 content から `done` までが無制限でも式を
  満たしてしまい、現行 SLI の「threshold 以内に journey を完了」と同値にならない。journey の
  完了（終端 event の受信）までを有界に保つことは、この semantics の要件である

- 本契約の「有効な終端 event」は `done` のみである。**`error` event は有効な終端 event では
  ないため、`error` で終端したストリームは bad event になる**（`content_filter` 起因で撤回を
  伴う場合を含む。SLO 文書の bad event 列挙の具体化として別 PR で追記する）
- **threshold 1 / threshold 2 の数値は本 ADR で決めない**（SLO 文書の決定手順に従いユーザーが
  決める。実装・実測が値を先取りしない）
- TTFT（time to first token）は「Azure OpenAI へのリクエストから最初の生成トークンまで」という
  標準の意味の **diagnostic metric としてのみ**使う。この service 固有の測定（client boundary の
  「最初の content event まで」）を TTFT と呼ばない。用語を上書きすると upstream 診断と
  SLI 測定の数字が同名で混ざるため

## 背景

- 現行の `/chat` は応答全文を 1 つの JSON で返す。LLM 応答の生成時間はそのまま無応答時間に
  なり、client は完了までレンダリングできない。frontend の Azure デプロイ（[ADR-0027](./0027-frontend-azure-deployment-and-public-surface.md)）で
  supported client boundary の SLI を継続測定するにあたり、「最初の content event までの時間」と
  「以後の間隔」を意味論に持つ measurement semantics を本 ADR が prospective に決める（決定 11。
  SLO 正本の現行 SLI は単一 threshold の journey 完了型であり、正本の改訂は別 PR）。応答側の
  契約をストリーミングとして固定する必要がある
- wire format・決定 5 の表・撤回契約・retry 境界は、外部レビュー 4 周（Codex）を経て確定した。特に
  「upstream parser の byte 分断耐性」と「表示済み text の後に filter signal が届く経路」は
  レビューで発見され（3〜4 周目）、決定 6・8 に組み込まれた
- ガードをコードで担保する構造（ADR-0010）と、CI から実 LLM を呼ばない構造（ADR-0004）は
  本 ADR でも維持する。fixture（決定 9）はその両立手段である

## 検討した選択肢

### 1. SSE + 応答契約の完全固定（採択）

上記「決定内容」のとおり。

### 2. 非ストリーミングのまま維持する（却下）

本 ADR の SLI measurement semantics（決定 11 の prospective decision）が「最初の content
event」「content event の間隔」を意味論に持つ以上、
単一 JSON 応答では good event の判定材料が構造的に取れない（全文到着の 1 時点しかない）。
また応答全文の生成完了まで client が何も表示できず、体感の無応答時間が LLM 生成時間と等しく
なる構造も変わらない。

### 3. WebSocket（却下）

双方向通信は不要（サーバー → client の一方向配信で足りる）。WebSocket はプロトコル
upgrade・接続管理・BFF での中継実装が SSE より重く、ACA ingress・Easy Auth・既存の
HTTP ベースの観測（アクセスログ・status 分類）との整合も個別確認になる。一方向配信なら
SSE が HTTP のまま完結する。

### 4. chunked JSON lines（NDJSON）（却下）

機能的には近いが、標準化された event 種別の枠（`event:` 行）を自前の JSON field で再発明する
ことになる。SSE は W3C / WHATWG 仕様のある標準形式で、`text/event-stream` という確立した
media type を持ち、中間層（proxy）の扱いも既知である。「業界標準の用語・形式を使う」方針から
も NDJSON を選ぶ理由がない。なお SSE の行指向 framing と LLM 出力の改行の衝突は、data を
JSON object に固定すること（決定 2）で解消済みである。

### 5. `content_filter_results` の `error` を警告として通し `done` を出す（fail-open。却下）

filter の判定が得られなかった応答を「有効な終端 = good event 候補」にすると、filter 障害時に
未判定のテキストが完了扱いで画面に残る。安全側の既定（fail-closed）に反し、SLI 上も
「filter が壊れているほど good が増える」逆向きの誘因を作る。外部レビューで 3 周連続で
指摘された論点であり、fail-closed（決定 6）で確定する。

## 採択理由

- SSE は一方向のテキストストリーミングに対する標準形式であり、HTTP のまま BFF 中継・
  Easy Auth・既存観測と両立する。`EventSource` の制約は `fetch` + reader で回避できる
- 文法（順序・多重度）と決定 5 の表を先に固定することで、backend・frontend・synthetic の 3 実装が
  同一 fixture で検証でき、「実装の挙動が契約」という状態を作らない
- 撤回契約と fail-closed の変換規則は、streaming で必然的に生じる「表示が判定に先行する」構造への
  唯一の安全側の回答である。wire に撤回 event を足さず client 責務にしたのは、producer 側は
  「`done` を出さない」ことで完了扱いを防げており、画面状態の巻き戻しは client にしか
  できないため
- retry 境界を「最初の content event 受信前」に引くことで、既存の retry 資産（分類・backoff）を
  接続確立局面で温存しつつ、重複送出の経路を契約レベルで消せる

## 影響

- 変更対象: `backend/app/main.py`（`/chat` の SSE 化）、`backend/app/llm/client.py`
  （stream 対応 transport・upstream incremental parser・retry 境界の変更）、
  `frontend/app/chat.tsx` と BFF route handler（reader ベースの parser・撤回処理・中継）、
  `docs/contracts/chat-sse/`（fixture 新設）、テスト一式
- **ACA ingress の 240 秒**: Azure Container Apps の ingress には既定 240 秒の timeout がある
  （出典: <https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview> ）。初版では
  これが総リクエスト時間なのかアイドル時間なのかが公式文書内で記述が食い違っており未解決と
  していたが、**実測（Issue #183。[一時 Container App 実測記録](../verification/easy-auth-container-app/observations.md)
  §5）で、この条件ではアイドル（バイト間）timeout として振る舞い、総リクエスト時間の上限と
  しては振る舞わないことを確認して決着した**（2026-09-01 追記改訂）。SSE で content event が
  届き続ける限り、総時間が 240 秒を超えても切断されない（event 間隔 30 秒 × 20 で総時間
  602.30 秒完走、間隔 200 秒 × 2 で総時間 401.05 秒完走。一方アイドルが約 237.5 秒・240.2 秒に
  達した 2 回はいずれもそこで切断され、2 回再現）。総時間の上限が存在しないことは主張しない
  （観測した最長は 602.30 秒）。いずれにせよこれは **platform の制約であって SLO の値では
  なく**、SLI threshold の根拠に流用しない
- `docs/operations/slo/slo-document.md` の改訂が**別 PR** で必要になる（response contract の
  参照先を本契約へ、bad event 列挙への「`content_filter` 終端（表示済み partial text の撤回を
  伴う場合を含む）」の具体化、supported client の入力契約、そして**決定 11 の 2 閾値
  measurement semantics（終端 event までの間隔適用を含む）の正本化**）。error event = bad の
  具体化は既存分類の範囲だが、SLI specification の 2 閾値化は**測定意味論の変更**であり、
  正本改訂まで本 ADR の式は prospective decision に留まる
- `frontend/app/chat.tsx` の `REQUEST_TIMEOUT_MS = 15_000` と `AbortSignal.timeout` の扱いが
  変わる。単一の全体 timeout はストリーミング応答と両立しない（正常な長い応答を途中で
  切断する）ため、client 側の打ち切りは threshold 1 / threshold 2 の決定と整合する形に
  再設計する。現行値 15,000 ms は非ストリーミング前提の現在の configuration であり、
  新しい値の根拠にしない（SLO 文書の既存の注意書きと同じ扱い）
- guard 経路（ADR-0010）の応答は `notice` event になるが、「LLM を呼ばない」構造は不変
- retry の適用範囲が狭まる（ストリーミング開始後の再試行は行わない）。ADR-0009 の
  「retry 既定値は据え置き」の対象範囲がストリーム開始前に限定される
- **初版の「未検証の前提」の実測結果**（2026-09-01 追記改訂。実測は Issue #184
  （[Azure OpenAI streaming 実測記録](../verification/azure-openai-stream/observations.md)）で
  実施し、結果を決定 5 の表・決定 6・決定 9 へ反映済み。「観測できなかった」は不在の証明では
  なく、防御的契約は維持する）:
  - streaming content filtering の実挙動: `finish_reason: "content_filter"` 終端・複数形
    `content_filter_results` の `error` は**観測できなかった**（7 呼び出しすべて
    `finish_reason: "stop"` で正常終端）。近縁の実データとして、単数形 `content_filter_result`
    の `error` が正常終端 stream の全 chunk に同乗する系列を観測し、決定 5 の表・決定 6 へ
    反映した
  - `finish_reason` の後・raw `[DONE]` の前に metadata chunk が届く系列: 自発的な（opt-in
    なしの）系列は観測できなかったが、`stream_options.include_usage` opt-in 時の usage chunk で
    **Default mode での実在を確認**した（決定 5 の改訂注記。終端遅延設計の実データ裏付け）
  - 未知の chunk 形状: chunk 全体として決定 5 の表のどの行にも当てはまらない形状は**現れ
    なかった**（表の最終行の発動実績なし）。field 単位の未知 4 種を観測し、「未知 field は
    無視する」行として表へ反映した
  - 撤回の UI 挙動は HTTP synthetic では検証できない（verifier は分類のみ）。browser 側は
    parser テスト（fixture 6 系列目）で担保し、実ブラウザでの再現は別途の browser automation の
    範囲とする（本改訂でも実測対象外のまま維持する）
- **実測の観測環境（identity）と限界**（2026-09-01 追記改訂）: 上記の stream 実測は
  Japan East / `gpt-4.1-mini-2025-04-14` / api-version `2024-10-21` / RAI policy
  `Microsoft.DefaultV2` / mode **Blocking**（Default mode。Asynchronous Filter ではない）で
  行われた。RAI policy 名と mode は実測記録の実施条件には含まれておらず、デプロイ設定の読み取り
  確認（`az`）で補った事実である。**positive control（content filter を実際に発火させた観測）は
  未取得**であり、`finish_reason: "content_filter"` 終端・複数形 `content_filter_results` の
  `error`・content を持たない独立の annotation chunk は観測できなかった（不在の証明ではない）。
  よって本改訂は検査対象を拡大する方向のみで行い、観測されなかったことを根拠に検出範囲を
  狭める変更（表からの行の削除・検査対象の縮小）は含まない
- **本改訂で閉じない論点**（2026-09-01 追記改訂）: 単数形 `content_filter_result.error` 系列
  （再実行で再現しない間欠事象）が fail-closed により `error` 終端 = bad event になることの
  発生頻度と error budget への影響の評価は、本 ADR ではなく **SLO 文書側**（bad event 列挙の
  具体化と同じ別 PR）で扱う。本 ADR が決めるのは契約（fail-closed の維持と検査対象の field 名）
  のみである。決定 5 の表の再改訂が必要になる条件（positive control が得られた場合・正当な
  未知 chunk 形状が観測された場合）は表内と本節に維持した

## 関連

- [ADR-0027](./0027-frontend-azure-deployment-and-public-surface.md)— BFF・supported client・公開面の構成。本契約のストリームは BFF が中継する
- [ADR-0004](./0004-stub-llm-and-no-llm-in-ci.md) — CI から実 LLM を呼ばない。fixture（決定 9）が
  stream 契約でもこれを維持する手段
- [ADR-0009](./0009-azure-openai-as-llm-provider.md) — Azure OpenAI transport と retry 既定値。
  本 ADR は retry の適用境界のみ変更する
- [ADR-0010](./0010-rag-wiring-and-hallucination-guard.md) — guard 経路。`notice` event として
  契約に組み込む（決定 3）
- [SLI / SLO 文書](../operations/slo/slo-document.md) — 現行の単一 threshold SLI specification
  の正本。決定 11 の 2 閾値 measurement semantics（prospective decision）の正本化は別 PR
- [Azure OpenAI streaming 実測記録](../verification/azure-openai-stream/observations.md) —
  Issue #184。2026-09-01 の追記改訂（決定 5 の表・決定 6・決定 9）の入力
- [一時 Container App 実測記録](../verification/easy-auth-container-app/observations.md) —
  Issue #183。ACA ingress 240 秒 timeout の決着（「影響」）の入力
- Issue: #107（`/chat` 保護）/ #113（公開面）/ #106（外形監視）/ #184・#183（実測）/
  #190（2026-09-01 の追記改訂）
