# SLI / SLO 文書

この文書は `felis-ai-chatbot` の user-facing SLI / SLO を記述する。

| 項目 | 値 |
| --- | --- |
| Status | Draft |
| SLO Version | 未定（Status を Published にする時に記入） |
| Author | project owner（kmryst） |
| Date | 2026-09-12 |
| Reviewers | project owner |
| Approvers | project owner |
| Approval Date | 未定（Status を Published にする時に記入） |
| Revisit Date | 未定（Approval Date + 6 か月。暫定） |

本 project は個人開発であり、Author / Reviewers / Approvers はすべて project owner が兼ねる。
Workbook が 3 役を分けて記録させる理由は technical accuracy の確認と business decision の責任を分離することにあり、
本 project ではその分離は形式上のものである。この事実を隠さず役割で記載し、外部レビューを用いた場合は Reviewers 欄に追記する。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/) の
SLO 文書における author、technical reviewer、approver の記録方法。

Status `Draft` は、数値が空欄で [error-budget-policy.md](./error-budget-policy.md) の action を発動できない状態を表す。

## 位置づけ: 最初の iteration

この文書は完成した SLI / SLO ではない。SLI specification は確定しているが SLI implementation は存在せず、
実測は 0 件である。最初は測定可能な最小の方式を置き、実測を通じて SLI / SLO を反復改善する。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/) の
SLI 選定と改善の指針。

したがってこの改訂は、(1) the Google SRE books の大原則を明文化し、(2) そこからこの service に何が導かれるかを導出し、(3) 導出結果を
Workbook Appendix A「Example SLO Document」の節構成（Service Overview → SLIs and SLOs → Rationale → Error Budget →
Clarifications and Caveats）に流し込む。見出しは既存の運用文書に合わせて日本語で置き、対応する Workbook の節名を各見出しに併記する。安い implementation（authenticated synthetic transaction）から始め、
実測後に「原則 6」の 4 つの出口で見直す。原則から導けない項目は無理に埋めず未決定のまま残す。

SLO 採用後の engineering decision は [error-budget-policy.md](./error-budget-policy.md)、
初回策定、measurement、review、revision の手順は [slo-review-runbook.md](./slo-review-runbook.md) を正本とする。

## 原則: the Google SRE books が言っていること

### 原則 1: 測定は user に近いほど良い。取れないなら proxy でよく、その限界を書く

SLI は server 内部ではなく user が受け取る結果に近い場所で測る。real-user measurement が得られない間は、black-box 的な
synthetic transaction を proxy にできるが、coverage と測れない user behavior を明記して改善対象として残す。

根拠: [SRE Book Appendix B「A Collection of Best Practices for Production Services」](https://sre.google/sre-book/service-best-practices/)、
[SRE Book Ch.4「Service Level Objectives」](https://sre.google/sre-book/service-level-objectives/)、
[The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)。

### 原則 2: SLI specification と SLI implementation を分ける

SLI specification は user にとって重要な service outcome の定義であり、SLI implementation はそれを観測する具体的な方法である。
一つの specification に複数の implementation を持てるため、quality、coverage、cost を比較して選び、必要時に入れ替える。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)。

### 原則 3: SLI は少なく、単純に。request-driven なら availability と latency

request-driven service では、critical user journey の成功率と時間条件を少数の SLI で表す。各 SLO は優先順位の判断に使える必要があり、
集計規則は変化を隠さない程度に単純に保つ。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)（Table 2-1 を含む）、
[SRE Book Ch.4「Service Level Objectives」](https://sre.google/sre-book/service-level-objectives/)。

### 原則 4: target は current performance に縛られない。完璧は待てる

current performance は制約と観測の理解に使うが、目標値を無批判に固定する根拠にはしない。requirement が不足する初回は
baseline を丸めて starter SLO にし、review を通じて厳しくも緩くも見直す。

根拠: [SRE Book Ch.4「Service Level Objectives」](https://sre.google/sre-book/service-level-objectives/)、
[The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)。

### 原則 5: error budget は objective で reproducible な意思決定のためにある

error budget は、SLO の許容失敗量を event 数で表し、reliability と変更速度のトレードオフを再現可能に判断するために使う。
target は project owner が責任を持って承認し、budget は target から導出する。

根拠: [SRE Book Ch.3「Embracing Risk」](https://sre.google/sre-book/embracing-risk/)、
[SRE Book Ch.1「Introduction」](https://sre.google/sre-book/introduction/)。

### 原則 6: SLO は living document であり、4 つの出口で iterate する

service の実態または観測の質が変われば、SLO も見直す。review の出口は次の4つである。

| 出口 | この文書での意味 |
| --- | --- |
| SLO target を変更する | SLI が示す user impact と policy の反応が合わない場合に target を調整する |
| SLI implementation を変更する | user に近い measurement point へ寄せる、または coverage を増やす |
| aspirational SLO を置く | current SLO と並行して測るが、policy action の根拠にはしない目標を置く |
| iterate する | 最初は低コストの方法を採り、evidence が増えた時に最も効果の大きい改善を選ぶ |

立ち上げ期は monthly、安定後は quarterly を暫定の review cadence とする。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)。

## 導出: この service に何が導かれるか

この service の事実は次のとおりである。`POST /chat` を supported client から呼ぶ request-driven service。個人開発で、
intended user は project owner 1 名（Issue #208）。実トラフィックはほぼ無い。critical dependency に Azure OpenAI を持つ。
SLI specification は ADR-0028 決定 11 で確定済み（PR #241 で正本化）だが、SLI implementation は無い。

| 原則 | この service への帰結 | 決まったこと | 未決定のまま残すこと |
| --- | --- | --- | --- |
| 1 測定は user に近いほど良い | measurement point は supported client boundary。ingress log と application log は client 側の DNS、TLS、parse、render を観測できないので診断に限る | measurement point | — |
| 1 取れないなら proxy | 実利用が無いので client-side instrumentation は event を生まない。authenticated synthetic transaction（black-box monitoring の層）を proxy として primary SLI implementation に採る。限界（real user の分布を表さない、撤回の UI 挙動は検証できない）は §補足と留意点に書く | SLI implementation の方式 | payload / identity / location / schedule / measurement timeout の値 |
| 2 specification と implementation を分ける | specification は確定、implementation は 0 件。この文書は implementation を「安い方」から始める最初の iteration である | 文書の位置づけ、measurement timestamp contract | timestamp 以外の schema / tool / version |
| 3 少なく単純に、request-driven は availability と latency | availability と latency は両方要る。ただし ADR-0028 決定 11 が両者を 1 つの比率（threshold 超過を policy として error に数える）に畳んでおり、これを 1 本の SLI とする。`done` 到達率は availability の diagnostic として別に持ち、SLO を増やさない | SLI の本数 | — |
| 4 current performance に縛られない、完璧は待てる | 他に情報が無く（requirement 無し）、iterate する手順（runbook）があるので、baseline を切り下げた starter SLO を採る。観測値をそのまま target にしない。refine の段階で current performance を上限と誤認しない | starter SLO の作り方 | threshold 1 / threshold 2 の値、SLO target |
| 5 error budget は objective な意思決定のため | 開発者と承認者が同一人物でも、event 数で計算した budget を Issue に記録して判断すれば reproducible になる。budget は request-based の単位で扱う | error budget の単位、policy の存在 | 値（Status `Draft` の間は計算しない） |
| 6 living document、4 つの出口 | compliance period は Workbook の default（four-week rolling window）を採り、review は monthly から始めて quarterly へ。aspirational SLO の枠を置く。Revisit Date は Approval + 6 か月 | compliance period、review cadence（いずれも暫定） | aspirational SLO の採否 |
| dependency（Workbook §Modeling Dependencies） | Azure Container Apps / Azure OpenAI / PostgreSQL / Entra ID が critical dependency。独立性を仮定した積（約 99.74%）は dependency risk を考えるための参考値であり、current SLO の上限には使わない。dependency 起因の bad event も budget を消費する | composite の参考値 | dependency 起因の miss の扱い（policy に暫定で記録） |

以下は、この導出結果を Workbook Appendix A の形に流し込んだものである。

## サービス概要（Service Overview）

対象とするサービス体験は、supported client と認証済みの `POST /chat` endpoint で構成される RAG chatbot の操作である。
`POST /chat` の response は [ADR-0028](../../adr/0028-chat-sse-response-contract.md) が定める SSE stream
（`message` / `notice` / `error` / `done` event）であり、supported client は有効な終端 event である `done` を受信するまで
応答を確定しない。以下ではこの文書を通して、`message` と `notice` をあわせて content event と呼ぶ。event の data schema と
`error` event の class 識別子は [docs/contracts/chat-sse/README.md](../../contracts/chat-sse/README.md) を正本とする。

構成は 2026-09-01〜09-02 に変わった。supported client は Azure Container Apps に deployment された frontend
（`ca-felisaichatbot-dev-front`。Easy Auth 付き）であり、client は BFF（`POST /api/chat`）だけを呼ぶ。backend は internal ingress で、
BFF 経由でのみ到達する。`LLM_PROVIDER` は `azure-openai` で、実際に Azure OpenAI を呼ぶ
（[llm-provider-cutover](../../verification/llm-provider-cutover/observations.md)）。2026-09-02 の読み取り専用確認では
backend image は `backend:sha-b6d90f7` で、deployment 済み image と `main` の一致を確認している
（[frontend-image-sync](../../verification/frontend-image-sync/observations.md)）。

release は PR のマージ（GitHub Actions による image build と deployment）であり、Terraform apply はユーザー承認後に手動で行う。

### ユーザー

現在の intended user は、Easy Auth（Entra ID）で認証し、アプリのロール `Chat.Use` を割り当てられたアカウントから chatbot を
操作する project owner である。`Chat.Use` の割当は 2026-09-02 時点で所有者 1 アカウントのみで、他のアカウントは `AADSTS50105` で
拒否される（Issue #208）。外部 customer population、SLA、独立した business requirement は repository に記録されていない。
したがって本 service は low-traffic service であり、eligible event を生む実利用が継続的に存在しない。

サービス範囲を拡張する前に、新しい user population、supported client、authentication contract、user expectation、
failure impact、risk tolerance を記録し、SLI specification を再評価する。

### Critical user journey

intended user が、認証済みの supported client から構文上有効で supported な質問を送信し、有効な終端 event（`done`）まで
response stream を受信して parse / render できる。no-context notice は application が意図した安全動作なので、
`notice` → `done`（ADR-0010 の guard 経路）を受信して render できれば journey は完了している。client が stream を parse または
render できなければ、transport response が返っただけでは完了としない。`error` event は有効な終端 event ではないため、
`error` で終端した stream は journey を完了していない。

semantic correctness は application test と、将来必要になった quality evaluation の手順で評価する。HTTP success から推定せず、
根拠のない別の SLO として追加しない。

### SLO の範囲外

この SLO は critical user journey の user-facing availability / latency を制御する control loop であり、本 service の reliability 全体を表すものではない。security、data integrity、recovery は独立した reliability objective として扱い、同じ error budget に混在させない。

reliability には availability 以外にも durability と security の保証が含まれるため、この SLO で全てを代表させない。

根拠: [Building Secure and Reliable Systems Ch.6「Design for Understandability」](https://google.github.io/building-secure-and-reliable-systems/raw/ch06.html)。

- 意図したユーザー操作ではない匿名の Internet traffic
- `/livez`、`/readyz`、database observation の freshness、infrastructure metrics を単独で評価した結果。
  user から見えない機能は **NO_SLO** として別扱いにする
- 回答内容の semantic quality、factual accuracy、source quality
- 独自の運用文書と既存の RTO / RPO requirement を持つ backup recovery と database durability

これらが重要でないという意味ではない。同じ user outcome を表さないため、この request-based SLI に暗黙に混在させない。

根拠: [The Site Reliability Workbook Ch.5「Alerting on SLOs」](https://sre.google/workbook/alerting-on-slos/)（Table 5-10）。

### Compliance period

SLO は **four-week rolling window** を compliance period とする（暫定。Rationale 参照）。

## SLI と SLO（SLIs and SLOs）

| Category | SLI | SLO（current） | SLO（aspirational） |
| --- | --- | --- | --- |
| `POST /chat`（critical user journey） | eligible event のうち、supported client が最初の content event を threshold 1 以内に受信し、以後の content event の間隔、および最後の content event から有効な終端 event までの間隔が threshold 2 を超えることなく、有効な終端 event `done` を受信して parse / render できたものの割合。authenticated synthetic transaction が supported client boundary で測る | 未記入（baseline 後に starter SLO として記入） | 未記入（任意。client-side instrumentation の実装後に測る、current SLO より厳しい値。policy の action を発動しない） |

```text
count of eligible "chat" synthetic transactions which
  received the first content event within threshold 1
  and every subsequent gap (content -> content, last content -> done)
      was within threshold 2
  and terminated with a `done` event
  and were parsed and rendered by the supported client
divided by
count of all eligible "chat" synthetic transactions
```

この measurement semantics は ADR-0028 決定 11 を正本化したものである（PR #241）。threshold 2 は content event 間だけでなく、
最後の content event から終端 event までの区間にも適用する。content event が 1 件の stream（guard 経路の `notice` → `done`）で
間隔条件が空適用にならず、journey の完了までを有界に保つためである。

threshold を超えた response を policy 上の bad event に数える。HTTP status が成功でも、response contract 違反や遅延は
user journey の失敗になり得る。

根拠: [SRE Book Ch.6「Monitoring Distributed Systems」](https://sre.google/sre-book/monitoring-distributed-systems/)。

TTFT（time to first token）は Azure OpenAI への request から最初の生成 token までを指す diagnostic metric であり、
threshold 1 が測る「最初の content event まで」とは別の量である。両者を同じ名前で呼ばない（ADR-0028 決定 11）。

### Eligible event

次の条件をすべて満たす event を eligible event とする。

- supported client から `POST /chat` へ送られた intended-user submission、または intended user を模擬する
  authenticated synthetic transaction である
- 文書化された request shape を使用し、message が client-visible input contract を満たす
- 文書化された authentication mechanism の対象である。authentication の失敗または欠落を理由に ineligible としない
- 文書化された service scope と SLO version が有効な期間に発生している

### Good event

eligible event のうち、次の 4 条件をすべて満たすものだけを good event とする。

- 最初の content event を threshold 1 以内に受信した
- 以後の content event の間隔、および最後の content event から終端 event までの間隔が threshold 2 を超えなかった
- 有効な終端 event である `done` で終端した
- supported client が stream を parse して render できた

normal reply（`message` 列 → `done`）と意図した no-context notice（`notice` → `done`）は、どちらもこの条件を満たせば good event である。

### Bad event

測定できた eligible event のうち good event でないものは、すべて bad event とする。次を含む。

- DNS、TLS、network、ingress、transport、authentication、routing、configuration の failure
- server error、dependency failure、malformed response
- `error` event で終端した stream。class は問わない（`timeout` / `rate_limit` / `server_error` / `bad_request` / `content_filter`）。
  `content_filter` 終端で表示済み partial text の撤回を伴うもの（ADR-0028 決定 6）も bad event である
- 終端 event（`done` / `error`）なしに終了した stream（ADR-0028 決定 2。Azure Container Apps ingress の idle timeout による切断を含む）
- threshold 1 または threshold 2 を超えたもの
- qualifying response を観測する前に発生した measurement timeout
- supported client が parse または render できない stream

intended user の request は、application code へ到達する前に失敗したことを理由に ineligible にしない。
単数形 `content_filter_result` の `error` による間欠的な `content_filter` 終端（ADR-0028「本改訂で閉じない論点」）は
fail-closed の結果として bad event に分類し、発生頻度は最初の baseline の review 項目とする。

### Exclusion

次の event は、文書化された scope data から再現可能に分類できる場合に限り除外できる。

- intended user population 以外の actor による traffic
- service processing 開始前に文書化された input contract を満たさない request
- 実行前に test または drill と識別し、intended-user population と分離した event
- effective SLO version または明示された service scope の外で発生した event

telemetry loss、collection failure、不都合な結果、planned maintenance、原因不明の failure は自動的な exclusion ではない。
eligible population または outcome を再構築できない場合は、SLO を確実に評価するだけの evidence がないと記録する。

### SLI implementation

primary SLI implementation は **authenticated synthetic transaction** とする（導出の原則 1）。intended user を模擬する
identity（synthetic 用 service principal。[entra-easy-auth-setup.md](../entra-easy-auth-setup.md)）で supported client と同じ経路
（BFF 経由）の `POST /chat` を周期的に実行し、ADR-0028 決定 9 の共有 fixture で検証した verifier が SSE stream を good / bad に分類する。

| Data source | 観測できるもの | この SLI に対する limitation | 状態 |
| --- | --- | --- | --- |
| Authenticated synthetic transaction | 模擬した critical user journey。parse / render まで含めて分類できる | real-user traffic の分布を表さない。撤回の UI 挙動は HTTP synthetic では検証できない | **採用**。configuration は未記入 |
| Supported-client instrumentation | intended request と client-visible outcome | 実利用がなければ event を生まない | 未実装。aspirational SLO 用 |
| `ContainerAppHTTPLogs` | ingress の path、status、`RequestDuration`、revision、replica | client の parse / render を観測しない | diagnostic setting がなく利用不可（2026-08-30 確認） |
| Application access log | FastAPI に到達した request の path、status、server duration | application 到達前の failure と client-visible completion を観測しない | SLO query 未実装。診断用 |
| `/readyz` GitHub Actions probe | 外部からの到達性、database reachability | `/chat` も frontend も実行しない | NO_SLO |

評価は event count から行う。

```text
SLI = count of good eligible events / count of all eligible events
```

結果には eligible、good、bad、unclassifiable record、collection gap の各 count を残し、request-based ratio を downtime に変換しない。
unclassifiable record と telemetry gap は good とせず、暗黙にも除外せず、別に報告する。承認済みの schema、query、tool version、
validation evidence をこの文書に記録するまで SLO を有効にしない。

measurement frequency は未記入である。Azure OpenAI の呼び出し cost が上限を、error budget の粒度（下記 Error Budget の
low-traffic の注意）が下限を決める。他 service の probe 間隔は参考にとどめ、本 service の値は baseline と cost から決める。

measurement timeout は未記入であり、right-censoring を決める値なので threshold 2 より長くなければならない。
supported client には時間ベースの timeout がなく（#199 で `REQUEST_TIMEOUT_MS` を廃止。打ち切りは `AbortController` の停止ボタンのみ）、
`/readyz` workflow の `curl --max-time 30` と ingress の idle timeout（既定 240 秒）は別経路と platform の設定であり、threshold の根拠にしない。

#### Measurement timestamp contract

本節は authenticated synthetic transaction の時刻 field、取得位置、rolling window への帰属、および latency 計測用 clock の
contract だけを定める。欠損処理、event classification、schedule / frequency / timeout の値、synthetic transaction の実装、
threshold 1 / threshold 2、SLO target はここでは決定しない。

すべての timestamp は wall clock から取得し、UTC の RFC 3339 形式、millisecond precision、末尾 `Z`
（例: `2026-09-12T10:15:30.123Z`）で記録する。

| Field | 取得位置と意味 | 用途 |
| --- | --- | --- |
| `scheduled_for` | scheduler が事前に割り当てた名目上の実行時刻。実行が遅れても書き換えず、実行開始時刻で代用しない | schedule の coverage と遅延の診断に使う。実行済み transaction の期間帰属や latency には使わない |
| `attempt_started_at` | request body と authentication material の準備後、synthetic client が public frontend の `POST /api/chat` を HTTP stack へ渡す直前。DNS / TLS / ingress / BFF はこの後の経路に含む | SLI の唯一の event time。baseline、compliance period、SLO / configuration version の期間帰属に使う |
| `completed_at` | client-side verifier が response または failure と parse / render adapter の結果を確定した直後、record の serialize / upload より前 | attempt の lifecycle と collection の診断に使う。期間帰属や latency には使わない |
| `ingested_at` | durable evidence sink が raw measurement record を受理して永続化した時刻。sink 側で取得し、producer の log 出力時刻で代用しない | ingestion delay と evidence 到着の診断に使う。期間帰属や latency には使わない |

four-week rolling window は UTC の連続 672 時間とし、実行済み transaction は `attempt_started_at` で半開区間
`[window_start, window_end)` に割り当てる。

```text
window_start <= attempt_started_at < window_end
window_start = window_end - 672 hours
```

したがって `window_start` と同時刻の attempt は含み、`window_end` と同時刻の attempt はその評価 window に含めない。window 内で開始して
window 外で完了した attempt は含み、window 外で開始して window 内で完了した attempt は含めない。scheduler の遅延、late ingestion、
再送または再集計によって、保存済み event の期間帰属を書き換えない。

latency は wall clock timestamp の差では測らない。`attempt_started_at` の取得と同じ論理境界で同一 process の monotonic clock を開始し、
public frontend への request 開始までに非同期処理を挟まない。完全な SSE event を framing / UTF-8 / JSON / schema の検証後に consumer が
受理した時点と、verifier が処理を完了した時点で monotonic elapsed time を取得する。最初の content event まで、隣接する content event 間、
最後の content event から `done` までの区間は、この未丸めの elapsed time から導出する。表示用に丸めた値で threshold と比較しない。

monotonic clock の絶対値は process 間で比較または永続化せず、経過時間だけを milliseconds で保存する。event の順序は stream の
観測順を正本とし、wall clock timestamp で並べ替えない。wall clock の補正や host 間の clock 差が latency を変えないようにし、
`completed_at - attempt_started_at` を SLI latency として使用しない。

### 未記入の項目

| 項目 | 決まったこと | 空欄 | 記入先 |
| --- | --- | --- | --- |
| threshold 1 / threshold 2 | semantics（ADR-0028 決定 11） | 値 | §SLI と SLO |
| SLO target（current） | baseline を切り下げた starter SLO | 値 | §SLI と SLO と §根拠 |
| SLO target（aspirational） | 任意。policy の action を発動しない | 値と採否 | 同上と policy |
| SLI implementation | authenticated synthetic transaction、measurement timestamp contract | timestamp 以外の schema / tool / version、payload / identity / location / schedule | SLI implementation |
| Measurement frequency / measurement timeout | 上下限の決め方 | 値 | 同上 |
| Alerting window と burn rate | Workbook Table 5-8 を starting point。ticket のみ | 値 | policy と alert source |

## 根拠（Rationale）

数値は synthetic transaction による baseline の後に、Workbook の Example と同じ文型で記入する。

baseline の測定期間、availability の切り下げ単位、latency の切り上げ単位、author が選んだ値、user experience との相関が未検証なら
その事実を Rationale に残す。

根拠: [The Site Reliability Workbook Appendix A「Example SLO Document」](https://sre.google/workbook/slo-document/)。

記入時には、baseline の期間、availability の切り下げ単位、threshold の切り上げ単位、author が選んだ値、
user experience との相関の検証状況を Rationale に記録する。intended user は project owner 1 名であり、独立した
user / business requirement は存在しないことも記録する。

丸め単位は service と user に依存する（Workbook の 50 ms は user が知覚しにくい変化幅を根拠にする）。LLM 応答では 500 ms や 1 秒単位が
妥当になりうるので、単位の選択理由を記入時に書く。

数値以外の Rationale は「導出」の表にある。暫定とした 3 項目の根拠を補う。

- compliance period（four-week rolling window）: rolling window は user experience に近く、週の整数倍なら週末の数が一定になる。
  Workbook の汎用的な出発点を採り、逸脱する場合に限り historical replay で理由を示す
- review cadence（monthly → quarterly）: 立ち上げ期は頻繁に確認し、安定後に頻度を落とす。安定の目安は暫定で「3 回連続で revision 不要」とする
- Revisit Date（Approval + 6 か月）: Example は約 1 年後だが、本 service は数値が空欄で最初の baseline 後に見直しが確実に要るため短くする

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)、
[The Site Reliability Workbook Appendix A「Example SLO Document」](https://sre.google/workbook/slo-document/)。

## error budget（Error Budget）

各 objective は個別の error budget を持ち、100% から target を引いた値と定義する。直近の four-week rolling window の
eligible synthetic transaction が N 件、current SLO target が p% の場合、error budget は request-based の event 数として
次のように計算する。downtime minutes に変換しない。

```text
許容する bad event の割合 = 1 − (SLO target / 100)

許容する bad event 数 = eligible event 数 × 許容する bad event の割合

残りの error budget = 許容する bad event 数 − 観測した bad event 数
```

objective ごとに error budget を分け、current SLO の budget が枯渇した時だけ policy を発動する。

根拠: [The Site Reliability Workbook Appendix A「Example SLO Document」](https://sre.google/workbook/slo-document/)。

### 有効化の条件

current SLO とその error budget は、次のすべてを満たした `Published` SLO Version についてだけ有効になる。

- ヘッダ表に SLO Version と Approval Date が記入されている
- current SLO target と compliance period が記入されている
- SLI implementation、schema、query または tool の version、validation evidence への link が記録されている

SLO Version は、承認した SLI specification、current SLO target、compliance period の組合せを識別する。これらを変更する時は
新しい SLO Version を記録する。effective boundary は Approval Date から開始し、過去の event には遡及しない。

各 compliance period の評価では、[slo-review-runbook.md](./slo-review-runbook.md) の「evidence が十分かを確認する」で
`sufficient` と記録された evidence だけを使用する。`Draft`、または evidence が `insufficient` の期間については、
SLO compliance、残りの error budget、[error-budget-policy.md](./error-budget-policy.md) の action を計算または発動しない。

current SLO の error budget が枯渇した時に [error-budget-policy.md](./error-budget-policy.md) を発動する。aspirational SLO の
budget は追跡するが policy を発動しない。

low-traffic の注意: 分母が synthetic transaction の件数 N なので、N が小さいと単一の bad event が budget の大きな割合を消費する。

low-traffic では単発 failure で burn rate が過大になり得るため、measurement frequency と SLO target を一緒に決め、
paging ではなく ticket を採用する。

根拠: [The Site Reliability Workbook Ch.5「Alerting on SLOs」](https://sre.google/workbook/alerting-on-slos/)。

したがって measurement frequency と SLO target は一緒に決める。

## 補足と留意点（Clarifications and Caveats）

### synthetic transaction は proxy であり、次が見えない

- real-user traffic の分布、payload の多様性、client 環境（browser、network）の多様性
- synthesize できない request type。real user だけに影響する問題があると、成功する synthetic request がその signal を隠す
- 撤回の UI 挙動（ADR-0028 決定 6。`content_filter` 終端で表示済み partial text を画面から撤回する）。verifier は分類のみを行い、
  browser 側は parser テスト（fixture 系列 6）で担保する。実ブラウザでの再現は別途の browser automation の範囲
- synthetic transaction 自体の失敗（scheduler の欠落、identity の期限切れ、測定側の network）と service の failure の区別。
  区別できない record は unclassifiable として別に報告する

synthetic transaction は user request の一部しか表せず、artificial traffic に現れない real-user failure を見逃し得る。

根拠: [The Site Reliability Workbook Ch.5「Alerting on SLOs」](https://sre.google/workbook/alerting-on-slos/)。

### error の定義は Workbook の Example より広い

Workbook の単純な HTTP status ベースの例より、本 SLI は error を広く定義する。5xx に加えて response contract 違反
（`error` 終端、終端 event なし、threshold 超過、parse / render 不能）を bad とする。
SSE stream では HTTP status が 200 のまま journey が失敗しうるためである。

根拠: [The Site Reliability Workbook Appendix A「Example SLO Document」](https://sre.google/workbook/slo-document/)。

### Critical dependency と composite の参考値

critical dependency は、その利用不能が critical user journey を利用不能にする dependency と定義する。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)（脚注 9）。

| Dependency | 役割 | Azure SLA の公称値 |
| --- | --- | --- |
| Azure Container Apps（frontend / backend） | supported client、BFF、backend の実行基盤 | 99.95% |
| Azure OpenAI | LLM 応答の生成 | 99.9% |
| Azure Database for PostgreSQL Flexible Server（HA なし） | pgvector による retrieval | 99.9% |
| Microsoft Entra ID（Easy Auth） | intended user の認証。落ちれば journey は開始できない | 99.99% |

独立性を仮定した積は、Entra ID を除く 3 者で 99.75%、含めると約 99.74% である。本文書は Entra ID を含める（暫定）。
この値は dependency risk を考えるための参考値であり、SLO target の硬い上限には使わない。依存関係の独立性、SLA の適用、
SLA の測定規則が本 SLI と一致することを確認できないためである。target は user outcome、baseline、risk tolerance を根拠に決め、
dependency failure には別経路、graceful degradation、retry 境界などを検討する。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)、
[The Site Reliability Workbook Ch.13「Data Processing Pipelines」](https://sre.google/workbook/data-processing/)。

SLA と本 SLI の関係について 2 点を明記する。

- 現在は無料試用クレジットを利用中であり、契約上 SLA は適用されない
  （[credit-window-execution-plan.md](../credit-window-execution-plan.md)）
- Azure SLA の Downtime 定義は 5xx 系の失敗のみを数え、429 と latency を除外するため、本 SLI（contract 違反・threshold 超過を bad とする）
  と一致しない。dependency の SLA 準拠は本 SLO の達成を保証しない

provider の SLO と user-facing SLI は測定境界と失敗定義が異なり得るため、provider の表示だけで user outcome を判定しない。

根拠: [The Site Reliability Workbook Ch.3「SLO Engineering Case Studies」](https://sre.google/workbook/slo-engineering-case-studies/)。

dependency 起因の bad event も error budget を消費する。

根拠: [SRE Book Ch.3「Embracing Risk」](https://sre.google/sre-book/embracing-risk/)。

dependency 起因の SLO miss への対応は [error-budget-policy.md](./error-budget-policy.md) の §SLO miss 時の対応に記録する。

### Warm / cold の series boundary

| 根拠資料 | Configuration と意味 | 比較可能性 |
| --- | --- | --- |
| 2026-08-26 に終了した Phase 1 observation | serving の `min_replicas` は `0`。external `/readyz` probe は主に、cold start が curl timeout 前に完了したかを測定していた | historical diagnostic evidence に限る。warm measurement と単一の連続 series として比較できない |
| ADR-0025 と 2026-08-30 の現在の runtime | serving の `min_replicas` / `max_replicas` と Azure runtime の `minReplicas` / `maxReplicas` は `1`。serving revision は `ca-felisaichatbot-dev--0000003` | 新しい configuration boundary。`min_replicas` は設定上の値であり、常に ready な warm replica を保証しない |

Phase 1 record には scheduled-run gap と curl timeout による right-censored failure があり、記録された success ratio は
observed probe outcome だけを表す。historical record を current semantics で書き換えない。merge commit の timestamp は
runtime で configuration が有効になった時点ではないので、各 measurement record に deployment と configuration の identity を記録する。
warm 固定は SLO を人工的に良く見せうるので、warm 条件での baseline から target を締めすぎない。

根拠: [SRE Book Ch.4「Service Level Objectives」](https://sre.google/sre-book/service-level-objectives/)。

### その他の caveat

- Azure Container Apps ingress の既定 240 秒は idle（バイト間）timeout として振る舞う（#183。ADR-0028「影響」）。platform の制約であり
  threshold の根拠にしないが、idle が 240 秒に達した切断は「終端 event なし」の bad event になる
- supported client には `maxLength` がなく、backend は `message` を最大 4,000 文字に制限する（2026-09-07 時点の `frontend/app/chat.tsx` で未解消）。
  effective SLO の前に再現可能な input contract を定義し、長い intended-user input を暗黙に exclusion にしない
- diagnostic metrics（client / ingress / application / database / LLM の elapsed time、TTFT、`done` 到達率、response status、
  revision と image の identity、CPU / memory / replica、dependency の error / latency / rate limiting、telemetry coverage）は
  SLI の変化を説明するために使い、それ自体から compliance を判定しない。user outcome に基づく別の rationale なしに SLO へ昇格させない
- measurement record には critical user journey、good-event rule、measurement point、本節の timestamp contract、clock source、schema、query、tool、timeout、
  authentication、payload、location、warm / cold condition、commit、revision、image、dependency mode の identity を含める。
  relevant condition が変わった場合は旧 series を閉じ、before / after を直接比較できるかを説明する。新しい target や semantics が
  過去にも有効だったかのように historical event を再計算しない

## SLO の対象外の設定

SLO の体裁を整えるためだけに決定項目を増やさない（原則 3）。次は SLO の決定項目ではなく、それぞれの正本に記録する。

| 設定 | 正本 | SLO との関係 |
| --- | --- | --- |
| client 側の打ち切り（`AbortController`） | `frontend/app/chat.tsx`、実装 PR | threshold 1 / threshold 2 の決定後に組み込む。SLI の threshold ではない |
| request timeout（server / ingress / dependency） | backend 設定、Terraform、ADR-0028「影響」 | platform 制約。threshold の根拠にしない |
| retry count / timing | ADR-0009、ADR-0028 決定 10（retry は最初の content event 前に限る） | bad event の発生率に影響するが SLO の値ではない |
| concurrency / request interval / campaign の request count | synthetic transaction の campaign plan（`docs/verification/`） | measurement の条件。SLI の意味を変えないことを検証する |
| CPU / memory / replica / scaling | Terraform、ADR-0025 | diagnostic metric（saturation） |
| RTO / RPO | [restore-drill-recovery-objectives.md](../restore-drill-recovery-objectives.md)、PITR ドリル証跡（#231 / #234 / #236） | 独立した recovery objective |

uptime と data integrity は別の user requirement であり、同じ error budget には混在させない。

根拠: [SRE Book Ch.26「Data Integrity」](https://sre.google/sre-book/data-integrity/)、
[Building Secure and Reliable Systems Ch.6「Design for Understandability」](https://google.github.io/building-secure-and-reliable-systems/raw/ch06.html)。

## 変更履歴

ヘッダ表の SLO Version、Approval Date、Revisit Date と Status が SLO の version と effective boundary を表す。最初の採用時に
SLI implementation version、query または tool version、supporting evidence の link をあわせて記録する。

| 日付 | 変更内容 | 定量的 decision |
| --- | --- | --- |
| 2026-08-30 | user-facing SLI specification、現在の evidence boundary、将来の decision procedure を記録 | なし |
| 2026-09-07 | ADR-0028 決定 11 の 2 閾値 measurement semantics を正本化。response contract を SSE 契約への参照に差し替え、bad event を具体化。`REQUEST_TIMEOUT_MS` の記述を #199 の廃止に合わせて修正（PR #241） | なし |
| 2026-09-07 | the Google SRE books の大原則とこの service への導出を先頭に置き、Workbook Appendix A の形へ全面改訂。最初の iteration と位置づけ、synthetic transaction を primary SLI implementation として採用。compliance period と review cadence の暫定値、current / aspirational の 2 段、critical dependency と composite の参考値、SLO の対象外の設定を記録（#242） | なし。数値は baseline 後に記入 |
| 2026-09-12 | synthetic transaction の4つの timestamp、`attempt_started_at` による rolling window への帰属、latency 用 monotonic clock の境界を定義（#253） | なし |

## 参考資料

### 主な方法論上の根拠

- [the Google SRE books（公式書籍一覧）](https://sre.google/books/)
- [Introduction](https://sre.google/sre-book/introduction/)
- [Embracing Risk](https://sre.google/sre-book/embracing-risk/)
- [Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)
- [A Collection of Best Practices for Production Services](https://sre.google/sre-book/service-best-practices/)
- [Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [SLO Engineering Case Studies](https://sre.google/workbook/slo-engineering-case-studies/)
- [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [Example SLO Document](https://sre.google/workbook/slo-document/)
- [Example Error Budget Policy](https://sre.google/workbook/error-budget-policy/)

### Platform implementation と cross-check

- [Define reliability based on user-experience goals](https://docs.cloud.google.com/architecture/framework/reliability/define-reliability-based-on-user-experience-goals)
- [Concepts in service monitoring](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring)
- [Service level indicators in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/service-level-indicators-create)
- [Monitor logs in Azure Container Apps with Log Analytics](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [Monitor Azure Container Apps metrics](https://learn.microsoft.com/en-us/azure/container-apps/metrics)
- [Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [Service Level Agreements (SLA) for Online Services](https://www.microsoft.com/licensing/docs/view/Service-Level-Agreements-SLA-for-Online-Services)
- [Service level objectives (SLOs)](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-ServiceLevelObjectives.html)

### Project の根拠資料

- [ADR-0028: /chat の SSE 化と応答契約の固定](../../adr/0028-chat-sse-response-contract.md)
- [ADR-0027: frontend の Azure デプロイと公開面の構成（Easy Auth + BFF + backend internal ingress）](../../adr/0027-frontend-azure-deployment-and-public-surface.md)
- [ADR-0025: serving を min_replicas 1 へ変更し cold start による可用性 SLI の汚染を排除する](../../adr/0025-serving-min-replicas-1-for-sli-integrity.md)
- [`/chat` SSE 共有 contract fixture](../../contracts/chat-sse/README.md)
- [Azure OpenAI streaming の実測記録](../../verification/azure-openai-stream/observations.md)
- [Easy Auth 付き Container App の実測記録](../../verification/easy-auth-container-app/observations.md)
- [フェーズ 1（低負荷ベースライン 72h）の実測記録](../../verification/observation-phase1/observations.md)
- [Issue #115: 外形監視の SLI 限定とコールドスタートコストの実測](https://github.com/kmryst/felis-ai-chatbot/issues/115)
- [Supported-client request handling](../../../frontend/app/chat.tsx)
