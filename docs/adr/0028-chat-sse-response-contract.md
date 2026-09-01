# ADR-0028: /chat の SSE 化と応答契約の固定

## ステータス

Proposed

## 日付

2026-09-01

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
SLI と食い違う。content event が 1 件しかないストリームでは、content event 間隔の条件
（後述 11 の threshold 2）は空適用となる。

### 4. `message` は非空の renderable text を要求する

`message` の `text` は**非空文字列**でなければならない。空文字列の `text` を持つ `message` は
契約違反であり、producer は送出してはならず、parser / verifier は「最初の content event」として
数えてはならない（空 event で threshold 1 だけ満たす抜け道を作らない）。

### 5. Azure OpenAI raw stream からの写像表（producer の義務）

backend は Azure OpenAI の chat completions stream（raw stream）を次の表のとおり wire contract
へ写像する。

| raw stream の chunk | wire 出力 |
| --- | --- |
| role のみの delta（content なし） | 出力しない |
| content が空文字列または null の delta | 出力しない |
| `choices` が空の chunk（annotation・usage 等のメタ chunk） | 出力しない |
| content が非空の delta | `message` |
| `finish_reason: "stop"` の終端 | `done` |
| `finish_reason: "content_filter"` の終端 | `error`（class: `content_filter`）。`done` なし |
| chunk 内の `content_filter_results` に `error` を検出 | **`finish_reason` の値に関わらず** `error`（class: `content_filter`）。`done` なし（下記 6） |
| 上記以外の未知の chunk 形状 | `error`（class: server error 系）で終端する（未知形状を握りつぶして「良い応答」に見せない fail-closed 側の選択。実 stream で正当な未知形状が観測されたら本表を追記改訂する） |

guard 経路（LLM を呼ばない）は raw stream を持たず、`notice` → `done` を直接生成する。

### 6. `content_filter_results` の `error` は fail-closed（撤回契約つき）

Azure の streaming content filtering は chunk 単位で評価されるため、**先行 chunk の text を
送出・表示した後に filter の判定・エラーが届く系列が起こり得る**（出典:
<https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-streaming> ）。
streaming ではテキストが判定より先に画面に出るため、「問題のある応答を出さない」制御では
間に合わず、**出してしまったものを撤回する契約**が必要になる。

- producer: `content_filter_results` の `error` を検出したら、`finish_reason` の値に関わらず
  `done` を出さず `error`（class: `content_filter`）で終端する（filter の判定が得られなかった
  応答を完了扱いにしない = fail-closed。外部レビューで 3 周連続で指摘され確定した論点）。
  送出済みの `message` を取り消す撤回 event は wire に導入しない
- consumer（supported client）: `error` の class が `content_filter` の場合、**表示済みの
  partial text を画面から撤回し、固定文言（「応答は提供元の content filter により打ち切られ
  ました」）に置換する**。他の class の `error` では partial text を保持し「応答は完了しません
  でした」を付す。撤回を filter 起因に限るのは、誤って有害たり得る partial text を画面に
  残さないためであり、通常障害の partial text はユーザーに残す方が有用なため

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
3. role-only delta 混在の raw stream とその wire 出力
4. 空・null content 混在の raw stream とその wire 出力
5. `content_filter` 終端（`finish_reason: "content_filter"`）
6. partial message 複数 → `content_filter_results` の `error`（撤回契約の検証用）

このほか、途中切断（終端 event なしの切断）系列と、決定 8 の byte 分断パターン試験データを
同梱する。backend のテスト・frontend parser のテスト・synthetic verifier がすべて同じ fixture を
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

### 11. SLI との関係（数値は本 ADR では決めない）

確定済みの SLI specification は次のとおり（数値決定はユーザー。実測は妥当性検証にのみ使う）。

> eligible event のうち、supported client が最初の content event を〈threshold 1〉以内に受信し、
> 以後 content event の間隔が〈threshold 2〉を超えることなく有効な終端 event を受信して
> parse / render できたものの割合

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
  「以後の間隔」を意味論に持つ確定 SLI specification が先に決まっており、応答側の契約を
  ストリーミングとして固定する必要がある
- wire format・写像表・撤回契約・retry 境界は、外部レビュー 4 周（Codex）を経て確定した。特に
  「upstream parser の byte 分断耐性」と「表示済み text の後に filter signal が届く経路」は
  レビューで発見され（3〜4 周目）、決定 6・8 に組み込まれた
- ガードをコードで担保する構造（ADR-0010）と、CI から実 LLM を呼ばない構造（ADR-0004）は
  本 ADR でも維持する。fixture（決定 9）はその両立手段である

## 検討した選択肢

### 1. SSE + 応答契約の完全固定（採択）

上記「決定内容」のとおり。

### 2. 非ストリーミングのまま維持する（却下）

SLI specification が「最初の content event」「content event の間隔」を意味論に持つ以上、
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
- 文法（順序・多重度）と写像表を先に固定することで、backend・frontend・synthetic の 3 実装が
  同一 fixture で検証でき、「実装の挙動が契約」という状態を作らない
- 撤回契約と fail-closed の写像は、streaming で必然的に生じる「表示が判定に先行する」構造への
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
  （出典: <https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview> ）。ただし
  **これが総リクエスト時間なのかアイドル時間なのかは公式文書内で記述が食い違っており、未解決**
  である。ストリーミングでは両者で意味が大きく異なる（総時間なら長い応答が必ず切れ、アイドル
  時間なら content event が届き続ける限り切れない）ため、**実 stream での実測で確定させる**。
  いずれにせよこれは **platform の制約であって SLO の値ではなく**、SLI threshold の根拠に
  流用しない
- `docs/operations/slo/slo-document.md` の改訂が**別 PR** で必要になる（response contract の
  参照先を本契約へ、bad event 列挙への「`content_filter` 終端（表示済み partial text の撤回を
  伴う場合を含む）」の具体化、supported client の入力契約）。既存分類（error event = bad）の
  具体化であり規則の変更ではない
- `frontend/app/chat.tsx` の `REQUEST_TIMEOUT_MS = 15_000` と `AbortSignal.timeout` の扱いが
  変わる。単一の全体 timeout はストリーミング応答と両立しない（正常な長い応答を途中で
  切断する）ため、client 側の打ち切りは threshold 1 / threshold 2 の決定と整合する形に
  再設計する。現行値 15,000 ms は非ストリーミング前提の現在の configuration であり、
  新しい値の根拠にしない（SLO 文書の既存の注意書きと同じ扱い）
- guard 経路（ADR-0010）の応答は `notice` event になるが、「LLM を呼ばない」構造は不変
- retry の適用範囲が狭まる（ストリーミング開始後の再試行は行わない）。ADR-0009 の
  「retry 既定値は据え置き」の対象範囲がストリーム開始前に限定される
- **未検証の前提**（実 stream の観測で確定させ、結果次第で写像表・撤回契約を追記改訂する）:
  - streaming content filtering の実挙動（partial text 送出後に `content_filter` 終端・
    `content_filter_results` の `error` が実際に届く系列の実在と到達順序）
  - 未知の chunk 形状の実在（写像表の最終行の発動実績）
  - 撤回の UI 挙動は HTTP synthetic では検証できない（verifier は分類のみ）。browser 側は
    parser テスト（fixture 6 系列目）で担保し、実ブラウザでの再現は別途の browser automation の
    範囲とする

## 関連

- [ADR-0027](./0027-frontend-azure-deployment-and-public-surface.md)— BFF・supported client・公開面の構成。本契約のストリームは BFF が中継する
- [ADR-0004](./0004-stub-llm-and-no-llm-in-ci.md) — CI から実 LLM を呼ばない。fixture（決定 9）が
  stream 契約でもこれを維持する手段
- [ADR-0009](./0009-azure-openai-as-llm-provider.md) — Azure OpenAI transport と retry 既定値。
  本 ADR は retry の適用境界のみ変更する
- [ADR-0010](./0010-rag-wiring-and-hallucination-guard.md) — guard 経路。`notice` event として
  契約に組み込む（決定 3）
- [SLI / SLO 文書](../operations/slo/slo-document.md) — 確定 SLI specification との整合
  （決定 11）。改訂は別 PR
- Issue: #107（`/chat` 保護）/ #113（公開面）/ #106（外形監視）
