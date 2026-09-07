# SLI / SLO 文書

この文書は `felis-ai-chatbot` の user-facing SLI / SLO を記述する。

| 項目 | 値 |
| --- | --- |
| Status | Draft |
| Author | project owner（kmryst） |
| Date | 2026-09-07 |
| Reviewers | project owner |
| Approvers | project owner |
| Approval Date | 未定（Status を Published にする時に記入） |
| Revisit Date | 未定（Approval Date + 6 か月。暫定） |

本 project は個人開発であり、Author / Reviewers / Approvers はすべて project owner が兼ねる。
Workbook が 3 役を分けて記録させる理由は technical accuracy の確認と business decision の責任を分離することにあり、
本 project ではその分離は形式上のものである。この事実を隠さず役割で記載し、外部レビューを用いた場合は Reviewers 欄に追記する。

> "The authors of the SLO, the reviewers (who checked it for technical accuracy), and the approvers (who made the business decision about whether it is the right SLO)."
> 訳: SLO の author、reviewer（technical accuracy を確認した人）、approver（それが正しい SLO かという business decision をした人）。

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」§Documenting the SLO and Error Budget Policy。

Status `Draft` は Workbook の Example に無い値（Example は `Published` のみ）だが一般語であり、
数値が空欄で [error-budget-policy.md](./error-budget-policy.md) の action を発動できない状態を表す。

## 位置づけ: 最初の iteration

この文書は完成した SLI / SLO ではない。SLI specification は確定しているが SLI implementation は存在せず、
実測は 0 件である。Workbook はこの段階の姿勢を明確に書いている。

> "Your first attempt at an SLI and SLO doesn't have to be correct; the most important goal is to get something in place and measured, and to set up a feedback loop so you can improve."
> 訳: SLI と SLO の最初の試みは正しくなくてよい。最も重要なのは、何かを置いて測り始め、改善のための feedback loop を作ることである。
>
> "Especially during the first few iterations, err on the side of quicker and cheaper; doing so reduces the uncertainty in your metrics and helps you determine if you need more expensive metrics. Iterate as many times as you need to."
> 訳: とくに最初の数回の iteration では、より速く安い方に倒せ。そうすることで metric の不確実性が減り、より高価な metric が必要かどうかを判断できる。必要なだけ iterate せよ。

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」§What to Measure: Using SLIs、§Improving the Quality of Your SLO。

したがってこの改訂は、(1) the Google SRE books の大原則を明文化し、(2) そこからこの service に何が導かれるかを導出し、(3) 導出結果を
Workbook Appendix A「Example SLO Document」の形（Service Overview → SLIs and SLOs → Rationale → Error Budget →
Clarifications and Caveats）に流し込む。安い implementation（authenticated synthetic transaction）から始め、
実測後に「原則 6」の 4 つの出口で見直す。原則から導けない項目は無理に埋めず未決定のまま残す。

SLO 採用後の engineering decision は [error-budget-policy.md](./error-budget-policy.md)、
初回策定、measurement、review、revision の手順は [slo-review-runbook.md](./slo-review-runbook.md) を正本とする。

## 原則: the Google SRE books が言っていること

### 原則 1: 測定は user に近いほど良い。取れないなら proxy でよく、その限界を書く

> "Measuring error rates and latency at the Gmail client, rather than at the server, resulted in a substantial reduction in our assessment of Gmail availability, and prompted changes to both Gmail client and server code."
> 訳: Gmail の error rate と latency を server ではなく client で測定した結果、Gmail の availability の評価は大幅に下がり、client と server 双方の code の変更につながった。

出典: SRE Book Appendix B「A Collection of Best Practices for Production Services」§Define SLOs Like a User。

> "There are two ways to change your SLI implementation: either move the measurement closer to the user to improve the quality of the metric, or improve coverage so you capture a higher percentage of user interactions."
> 訳: SLI implementation を変える方法は 2 つある。測定を user に近づけて metric の品質を上げるか、coverage を広げて user interaction のより多くを捕捉するかである。

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」§Improving the Quality of Your SLO。

user の測定が取れない場合の proxy として、SRE Book は black-box monitoring job の request を SLI に含める前例を示し、
Workbook は履歴が無ければ data source を設定せよと言う。

> "Which requests are included: 'HTTP GETs from black-box monitoring jobs'"
> 訳: どの request を含めるか: 「black-box monitoring job からの HTTP GET」。

出典: SRE Book Ch.4「Service Level Objectives」§Standardize Indicators。

> "If you do not have logs, metrics, or any other source of historical performance, you need to configure a data source. For example, as a low-fidelity solution for HTTP services, you can set up a remote monitoring service that performs some kind of periodic health check on the service (a ping or an HTTP GET) and reports back the number of successful requests."
> 訳: log、metric、その他の過去の performance の source が無いなら、data source を設定する必要がある。例えば HTTP service 向けの low-fidelity な解決策として、service に対して周期的な health check（ping や HTTP GET）を行い、成功した request の数を報告する remote monitoring service を用意できる。

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」§Choosing an Appropriate Time Window。

### 原則 2: SLI specification と SLI implementation を分ける

> "SLI specification — The assessment of service outcome that you think matters to users, independent of how it is measured."
> 訳: SLI specification — user にとって重要だと考える service outcome の評価。どう測るかとは独立である。
>
> "SLI implementation — The SLI specification and a way to measure it."
> 訳: SLI implementation — SLI specification と、それを測る方法。
>
> "a single SLI specification might have multiple SLI implementations, each with its own set of pros and cons in terms of quality (how accurately they capture the experience of a customer), coverage (how well they capture the experience of all customers), and cost."
> 訳: 1 つの SLI specification には複数の SLI implementation がありえて、それぞれ quality（customer の経験をどれだけ正確に捉えるか）、coverage（すべての customer の経験をどれだけ捉えるか）、cost の点で長短がある。

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」§What to Measure: Using SLIs。

### 原則 3: SLI は少なく、単純に。request-driven なら availability と latency

> "Request-driven — The user creates some type of event and expects a response. For example, this could be an HTTP service where the user interacts with a browser or an API for a mobile application."
> 訳: request-driven — user が何らかの event を作り、response を期待する。例えば user が browser で操作する HTTP service や mobile application 向けの API。
>
> "We recommend choosing a small number (five or fewer) of SLI types that represent the most critical functionality to your customers."
> 訳: customer にとって最も重要な機能を表す、少数（5 つ以下）の SLI 種別を選ぶことを推奨する。

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」§What to Measure: Using SLIs。Table 2-1 は request-driven の SLI として
availability（成功した response の割合）と latency（threshold より速かった request の割合）を挙げる。

> "Have as few SLOs as possible — Choose just enough SLOs to provide good coverage of your system's attributes. Defend the SLOs you pick: if you can't ever win a conversation about priorities by quoting a particular SLO, it's probably not worth having that SLO."
> 訳: SLO はできるだけ少なく — system の属性を十分に覆うだけの SLO を選ぶ。選んだ SLO を擁護せよ。ある SLO を引用して優先順位の議論に勝てないなら、その SLO はおそらく持つ価値がない。
>
> "Keep it simple — Complicated aggregations in SLIs can obscure changes to system performance, and are also harder to reason about."
> 訳: 単純に保て — SLI の複雑な集計は system performance の変化を覆い隠し、推論も難しくする。

出典: SRE Book Ch.4「Service Level Objectives」§Choosing Targets。

### 原則 4: target は current performance に縛られない。完璧は待てる

> "Don't pick a target based on current performance — While understanding the merits and limits of a system is essential, adopting values without reflection may lock you into supporting a system that requires heroic efforts to meet its targets, and that cannot be improved without significant redesign."
> 訳: current performance に基づいて target を選ばない — system の長所と限界を理解することは不可欠だが、熟慮せずに値を採用すると、target を満たすために heroic な努力を要し、大幅な再設計なしには改善できない system を支え続けることに縛られかねない。
>
> "Perfection can wait — You can always refine SLO definitions and targets over time as you learn about a system's behavior. It's better to start with a loose target that you tighten than to choose an overly strict target that has to be relaxed when you discover it's unattainable."
> 訳: 完璧は待てる — system の挙動を学ぶにつれて、SLO の定義と target はいつでも洗練できる。達成不能だと分かって緩めることになる過度に厳しい target を選ぶより、緩い target から始めて締めていく方がよい。

出典: SRE Book Ch.4「Service Level Objectives」§Choosing Targets。

Workbook はこの 2 つを接続し、条件付きで current performance を starter SLO の出発点にすることを許容する。

> "your current performance can be a good place to start if you don't have any other information, and if you have a good process for iterating in place (which we'll cover later). However, don't let current performance limit you as you refine your SLO"
> 訳: 他に情報が無く、その場で iterate する良い手順があるなら、current performance は良い出発点になりうる。ただし SLO を洗練する段階で current performance に制限されてはならない。
>
> "We can round down these SLIs to manageable numbers (e.g., two significant figures of availability, or up to 50 ms of latency) to obtain our starting SLOs."
> 訳: これらの SLI を扱いやすい数（例えば availability は有効数字 2 桁、latency は 50 ms 単位）に切り下げて、starting SLO を得る。

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」§What to Measure: Using SLIs、§Using the SLIs to Calculate Starter SLOs。

### 原則 5: error budget は objective で reproducible な意思決定のためにある

> "our goal is to define an objective metric, agreed upon by both sides, that can be used to guide the negotiations in a reproducible way. The more data-based the decision can be, the better."
> 訳: 我々の目標は、双方が合意した objective な metric を定義し、それを使って交渉を reproducible な形で導くことである。決定が data に基づくほど良い。
>
> "The error budget provides a clear, objective metric that determines how unreliable the service is allowed to be within a single quarter. This metric removes the politics from negotiations"
> 訳: error budget は、service が 1 四半期にどれだけ unreliable でよいかを決める、明確で objective な metric を与える。この metric は交渉から politics を取り除く。

出典: SRE Book Ch.3「Embracing Risk」§Motivation for Error Budgets、§Forming Your Error Budget。

> "The business or the product must establish the system's availability target. Once that target is established, the error budget is one minus the availability target."
> 訳: business または product が system の availability target を定めなければならない。target が定まれば、error budget は 1 から availability target を引いたものである。

出典: SRE Book Ch.1「Introduction」§Pursuing Maximum Change Velocity Without Violating a Service's SLO。

### 原則 6: SLO は living document であり、4 つの出口で iterate する

> "Your SLIs and SLOs should change over time as realities about the service they represent change. Don't be afraid to examine and refine them over time!"
> 訳: SLI と SLO は、それが表す service の実態が変わるにつれて変わるべきである。時間をかけて検討し洗練することを恐れるな。

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」§Improving the Quality of Your SLO。同節は SLO に coverage が足りない時の出口を 4 つ挙げる。

| 出口 | 原文 | 訳 |
| --- | --- | --- |
| Change your SLO | "If your SLIs indicated a problem, but your SLOs didn't prompt anyone to notice or respond, you may need to tighten your SLO. ... Likewise, for false-positive days, consider relaxing the SLO." | SLI が問題を示したのに SLO が誰の注意も対応も促さなかったなら、SLO を締める必要があるかもしれない。同様に false positive の日については SLO を緩めることを検討する |
| Change your SLI implementation | "either move the measurement closer to the user to improve the quality of the metric, or improve coverage" | 測定を user に近づけて metric の品質を上げるか、coverage を広げる |
| Institute an aspirational SLO | "you can make the refined SLO an aspirational SLO—measured and tracked alongside your current SLO, but explicitly called out in your error budget policy as not requiring action." | 洗練した SLO を aspirational SLO にできる。current SLO と並べて測定・追跡するが、error budget policy では action を要しないものとして明示する |
| Iterate | "Pick the option that's most likely to give the highest return on investment. Especially during the first few iterations, err on the side of quicker and cheaper" | 最も高い投資対効果が見込める選択肢を選ぶ。とくに最初の数回の iteration では、より速く安い方に倒す |

review の頻度も成熟度に応じて変える。

> "When starting out, you should probably review the SLO frequently—perhaps every month. Once the appropriateness of the SLO becomes more established, you can likely reduce reviews to happen quarterly or even less frequently."
> 訳: 始めたばかりの頃はおそらく頻繁に、例えば毎月 review すべきである。SLO の妥当性が確立してくれば、review を四半期ごと、あるいはもっと少なくできるだろう。

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」§Documenting the SLO and Error Budget Policy。

## 導出: この service に何が導かれるか

この service の事実は次のとおりである。`POST /chat` を supported client から呼ぶ request-driven service。個人開発で、
intended user は project owner 1 名（Issue #208）。実トラフィックはほぼ無い。critical dependency に Azure OpenAI を持つ。
SLI specification は ADR-0028 決定 11 で確定済み（PR #241 で正本化）だが、SLI implementation は無い。

| 原則 | この service への帰結 | 決まったこと | 未決定のまま残すこと |
| --- | --- | --- | --- |
| 1 測定は user に近いほど良い | measurement point は supported client boundary。ingress log と application log は client 側の DNS、TLS、parse、render を観測できないので診断に限る | measurement point | — |
| 1 取れないなら proxy | 実利用が無いので client-side instrumentation は event を生まない。authenticated synthetic transaction（black-box monitoring の層）を proxy として primary SLI implementation に採る。限界（real user の分布を表さない、撤回の UI 挙動は検証できない）は Clarifications and Caveats に書く | SLI implementation の方式 | payload / identity / location / schedule / measurement timeout の値 |
| 2 specification と implementation を分ける | specification は確定、implementation は 0 件。この文書は implementation を「安い方」から始める最初の iteration である | 文書の位置づけ | schema / tool / version |
| 3 少なく単純に、request-driven は availability と latency | availability と latency は両方要る。ただし ADR-0028 決定 11 が両者を 1 つの比率（threshold 超過を policy として error に数える）に畳んでおり、これを 1 本の SLI とする。`done` 到達率は availability の diagnostic として別に持ち、SLO を増やさない | SLI の本数 | — |
| 4 current performance に縛られない、完璧は待てる | 他に情報が無く（requirement 無し）、iterate する手順（runbook）があるので、baseline を切り下げた starter SLO を採る。観測値をそのまま target にしない。refine の段階で current performance を上限と誤認しない | starter SLO の作り方 | threshold 1 / threshold 2 の値、SLO target |
| 5 error budget は objective な意思決定のため | 開発者と承認者が同一人物でも、event 数で計算した budget を Issue に記録して判断すれば reproducible になる。budget は request-based の単位で扱う | error budget の単位、policy の存在 | 値（Status `Draft` の間は計算しない） |
| 6 living document、4 つの出口 | compliance period は Workbook の default（four-week rolling window）を採り、review は monthly から始めて quarterly へ。aspirational SLO の枠を置く。Revisit Date は Approval + 6 か月 | compliance period、review cadence（いずれも暫定） | aspirational SLO の採否 |
| dependency（Workbook §Modeling Dependencies） | Azure Container Apps / Azure OpenAI / PostgreSQL / Entra ID が critical dependency。独立性を仮定した積（約 99.74%）が current SLO の上限の目安。dependency 起因の bad event も budget を消費する | composite 上限 | dependency 起因の miss の扱い（policy に暫定で記録） |

以下は、この導出結果を Workbook Appendix A の形に流し込んだものである。

## Service Overview

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

### User

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

- 意図したユーザー操作ではない匿名の Internet traffic
- `/livez`、`/readyz`、database observation の freshness、infrastructure metrics を単独で評価した結果。
  Workbook Ch.5 Table 5-10 の分類で **NO_SLO**（"For functionality that is completely invisible to the user"。
  訳: user から完全に見えない機能）に置く
- 回答内容の semantic quality、factual accuracy、source quality
- 独自の運用文書と既存の RTO / RPO requirement を持つ backup recovery と database durability

これらが重要でないという意味ではない。同じ user outcome を表さないため、この request-based SLI に暗黙に混在させない。

### Compliance period

SLO は **four-week rolling window** を compliance period とする（暫定。Rationale 参照）。

## SLIs and SLOs

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

threshold を超えた response を policy として error に数える扱いは SRE Book Ch.6 に前例がある。

> "The rate of requests that fail, either explicitly (e.g., HTTP 500s), implicitly (for example, an HTTP 200 success response, but coupled with the wrong content), or by policy (for example, 'If you committed to one-second response times, any request over one second is an error')."
> 訳: 失敗する request の割合。明示的な失敗（HTTP 500 など）、暗黙の失敗（HTTP 200 の成功 response だが内容が誤っている場合など）、policy による失敗（「1 秒の response time を約束したなら、1 秒を超える request はすべて error」など）を含む。

出典: SRE Book Ch.6「Monitoring Distributed Systems」§The Four Golden Signals。

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
verifier は分類コンポーネントの名前であり、測定方式の意味では使わない。

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
low-traffic の注意）が下限を決める。SRE Book Ch.6 は 99.9% 目標の web service で 1 分に 1〜2 回より頻繁な probe を
"probably unnecessarily frequent"（訳: おそらく不必要に頻繁）と言い、Workbook Ch.3 の Evernote は毎分 poll する。いずれも本 service の値ではない。

measurement timeout は未記入であり、right-censoring を決める値なので threshold 2 より長くなければならない。
supported client には時間ベースの timeout がなく（#199 で `REQUEST_TIMEOUT_MS` を廃止。打ち切りは `AbortController` の停止ボタンのみ）、
`/readyz` workflow の `curl --max-time 30` と ingress の idle timeout（既定 240 秒）は別経路と platform の設定であり、threshold の根拠にしない。

### 未記入の項目

| 項目 | 決まったこと | 空欄 | 記入先 |
| --- | --- | --- | --- |
| threshold 1 / threshold 2 | semantics（ADR-0028 決定 11） | 値 | SLIs and SLOs |
| SLO target（current） | baseline を切り下げた starter SLO | 値 | SLIs and SLOs と Rationale |
| SLO target（aspirational） | 任意。policy の action を発動しない | 値と採否 | 同上と policy |
| SLI implementation | authenticated synthetic transaction | schema / tool / version、payload / identity / location / schedule | SLI implementation |
| Measurement frequency / measurement timeout | 上下限の決め方 | 値 | 同上 |
| Alerting window と burn rate | Workbook Table 5-8 を starting point。ticket のみ | 値 | policy と alert source |

## Rationale

数値は synthetic transaction による baseline の後に、Workbook の Example と同じ文型で記入する。

> "Availability and latency SLIs were based on measurement over the period 2018-01-01 to 2018-01-28. Availability SLOs were rounded down to the nearest 1% and latency SLO timings were rounded up to the nearest 50 ms. All other numbers were picked by the author and the services were verified to be running at or above those levels."
> 訳: availability と latency の SLI は 2018-01-01 から 2018-01-28 の期間の測定に基づく。availability の SLO は 1% 単位で切り下げ、latency の SLO の時間は 50 ms 単位で切り上げた。その他の数値はすべて author が選び、service がその水準以上で動作していることを確認した。
>
> "No attempt has yet been made to verify that these numbers correlate strongly with user experience."
> 訳: これらの数値が user experience と強く相関するかは、まだ検証を試みていない。

出典: The Site Reliability Workbook Appendix A「Example SLO Document」§Rationale。

記入時の placeholder:

> threshold 1 / threshold 2 と current SLO target は、〈期間〉の synthetic transaction による baseline に基づく。割合は 1% 単位で切り下げ、
> threshold は〈単位〉で切り上げた。その他の数値は author が選んだ。これらの数値が user experience と強く相関するかは検証していない。
> intended user は project owner 1 名であり、独立した user / business requirement は存在しない。

丸め単位は service と user に依存する（Workbook の 50 ms は user が知覚しにくい変化幅を根拠にする）。LLM 応答では 500 ms や 1 秒単位が
妥当になりうるので、単位の選択理由を記入時に書く。

数値以外の Rationale は「導出」の表にある。暫定とした 3 項目の根拠を補う。

- compliance period（four-week rolling window）: rolling window は user experience に近く、週の整数倍なら週末の数が一定になる。
  Workbook は "We have found a four-week rolling window to be a good general-purpose interval."（訳: four-week rolling window は
  汎用的に良い間隔だと分かっている）とし、Example も 1 文で宣言する。default をそのまま採り、逸脱する場合に限り historical replay で理由を示す
- review cadence（monthly → quarterly）: 原則 6 の引用のとおり。安定の目安は暫定で「3 回連続で revision 不要」とする
- Revisit Date（Approval + 6 か月）: Example は約 1 年後だが、本 service は数値が空欄で最初の baseline 後に見直しが確実に要るため短くする

## Error Budget

各 objective は個別の error budget を持ち、100% から target を引いた値と定義する。直近の four-week rolling window の
eligible synthetic transaction が N 件、current SLO target が p% なら、error budget は N × (1 − p / 100) 件の bad event である。
request-based の単位で扱い、downtime minutes に変換しない。

> "Each objective has a separate error budget, defined as 100% minus (–) the goal for that objective. ... We will enact the error budget policy (see Example Error Budget Policy) when any of our objectives has exhausted its error budget."
> 訳: 各 objective は個別の error budget を持ち、100% からその objective の goal を引いた値と定義する。（中略）いずれかの objective が error budget を使い切った時、error budget policy を発動する。

出典: The Site Reliability Workbook Appendix A「Example SLO Document」§Error Budget。

current SLO の error budget が枯渇した時に [error-budget-policy.md](./error-budget-policy.md) を発動する。aspirational SLO の
budget は追跡するが policy を発動しない。effective SLO target、compliance period、validated measurement が揃うまで
effective error budget は存在せず、Status が `Draft` の間は計算しない。

low-traffic の注意: 分母が synthetic transaction の件数 N なので、N が小さいと単一の bad event が budget の大きな割合を消費する。

> "if a system receives 10 requests per hour, then a single failed request results in an hourly error rate of 10%. For a 99.9% SLO, this request constitutes a 1,000x burn rate and would page immediately, as it consumed 13.9% of the 30-day error budget."
> 訳: system が 1 時間に 10 件の request を受けるなら、1 件の失敗で時間あたりの error rate は 10% になる。99.9% の SLO ではこの 1 件が 1,000 倍の burn rate に相当し、30 日の error budget の 13.9% を消費するので直ちに page される。

出典: The Site Reliability Workbook Ch.5「Alerting on SLOs」§Low-Traffic Services and Error Budget Alerting。

したがって measurement frequency と SLO target は一緒に決める。

## Clarifications and Caveats

### synthetic transaction は proxy であり、次が見えない

- real-user traffic の分布、payload の多様性、client 環境（browser、network）の多様性
- synthesize できない request type。real user だけに影響する問題があると、成功する synthetic request がその signal を隠す
- 撤回の UI 挙動（ADR-0028 決定 6。`content_filter` 終端で表示済み partial text を画面から撤回する）。verifier は分類のみを行い、
  browser 側は parser テスト（fixture 系列 6）で担保する。実ブラウザでの再現は別途の browser automation の範囲
- synthetic transaction 自体の失敗（scheduler の欠落、identity の期限切れ、測定側の network）と service の failure の区別。
  区別できない record は unclassifiable として別に報告する

> "Even for a nontrivial service, you can synthesize only a small portion of the total number of user request types."
> 訳: 些細でない service であっても、user の request type 全体のごく一部しか synthesize できない。
>
> "if an issue affects real users but doesn't affect artificial traffic, the successful artificial requests hide the real user signal, so you aren't notified that users see errors."
> 訳: ある問題が real user に影響するが artificial traffic には影響しない場合、成功する artificial request が real user の signal を隠し、user が error を見ていることが通知されない。

出典: The Site Reliability Workbook Ch.5「Alerting on SLOs」§Generating Artificial Traffic。

### error の定義は Workbook の Example より広い

Example は "We only count HTTP 5XX status messages as error codes; everything else is counted as success."
（訳: HTTP 5XX の status message だけを error code として数え、それ以外はすべて success として数える）とする。
本 SLI は 5xx に加えて response contract 違反（`error` 終端、終端 event なし、threshold 超過、parse / render 不能）を bad とする。
SSE stream では HTTP status が 200 のまま journey が失敗しうるためである。

### Critical dependency と composite 上限

> "A dependency is critical if its unavailability means that your service is also unavailable."
> 訳: dependency が unavailable であれば自 service も unavailable になるなら、その dependency は critical である。

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」脚注 9。

| Dependency | 役割 | Azure SLA の公称値 |
| --- | --- | --- |
| Azure Container Apps（frontend / backend） | supported client、BFF、backend の実行基盤 | 99.95% |
| Azure OpenAI | LLM 応答の生成 | 99.9% |
| Azure Database for PostgreSQL Flexible Server（HA なし） | pgvector による retrieval | 99.9% |
| Microsoft Entra ID（Easy Auth） | intended user の認証。落ちれば journey は開始できない | 99.99% |

独立性を仮定した積は、Entra ID を除く 3 者で 99.75%、含めると約 99.74% である。本文書は Entra ID を含める（暫定）。
ただし独立性の仮定は成立せず、この積は上限の目安に過ぎない。current SLO の availability 成分はこの上限を上回れない。

> "Unless each of these dependencies and failure patterns is carefully enumerated and accounted for, any such calculations will be deceptive."
> 訳: これらの dependency と failure pattern の一つひとつを注意深く列挙して考慮しない限り、そのような計算はすべて欺瞞的になる。
>
> "if a single component is a critical dependency for a particularly high-value interaction, its reliability guarantee should be at least as high as the reliability guarantee of the dependent action."
> 訳: ある component が特に価値の高い interaction の critical dependency なら、その reliability guarantee は依存する action の reliability guarantee と少なくとも同じ高さでなければならない。

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」§Modeling Dependencies。

> "Once you identify any third-party dependencies, at a minimum, design for the largest failure accounted for in their advertised SLAs."
> 訳: third-party の dependency を特定したら、最低限、それらの公表 SLA が想定する最大の failure に備えて設計する。

出典: The Site Reliability Workbook Ch.13「Data Processing Pipelines」§Plan for Dependency Failure。

SLA と本 SLI の関係について 2 点を明記する。

- 現在は無料試用クレジットを利用中であり、契約上 SLA は適用されない
  （[credit-window-execution-plan.md](../credit-window-execution-plan.md)）
- Azure SLA の Downtime 定義は 5xx 系の失敗のみを数え、429 と latency を除外するため、本 SLI（contract 違反・threshold 超過を bad とする）
  と一致しない。dependency の SLA 準拠は本 SLO の達成を保証しない

> "Even when GCP SLO graphs are green (i.e., above 99.95%), Evernote's view of the same SLO might be very different"
> 訳: GCP の SLO graph が green（99.95% 超）であっても、同じ SLO に対する Evernote の見え方はまったく異なりうる。

出典: The Site Reliability Workbook Ch.3「SLO Engineering Case Studies」§Breaking Down the SLO Wall Between Customer and Cloud Provider。

dependency 起因の bad event も error budget を消費する。

> "What happens if a network outage or datacenter failure reduces the measured SLO? Such events also eat into the error budget."
> 訳: network の outage や datacenter の failure が測定された SLO を下げたらどうなるか。そうした event も error budget を消費する。

出典: SRE Book Ch.3「Embracing Risk」§Benefits。

dependency 起因の SLO miss への対応は [error-budget-policy.md](./error-budget-policy.md) の SLO Miss Policy に記録する。

### Warm / cold の series boundary

| 根拠資料 | Configuration と意味 | 比較可能性 |
| --- | --- | --- |
| 2026-08-26 に終了した Phase 1 observation | serving の `min_replicas` は `0`。external `/readyz` probe は主に、cold start が curl timeout 前に完了したかを測定していた | historical diagnostic evidence に限る。warm measurement と単一の連続 series として比較できない |
| ADR-0025 と 2026-08-30 の現在の runtime | serving の `min_replicas` / `max_replicas` と Azure runtime の `minReplicas` / `maxReplicas` は `1`。serving revision は `ca-felisaichatbot-dev--0000003` | 新しい configuration boundary。`min_replicas` は設定上の値であり、常に ready な warm replica を保証しない |

Phase 1 record には scheduled-run gap と curl timeout による right-censored failure があり、記録された success ratio は
observed probe outcome だけを表す。historical record を current semantics で書き換えない。merge commit の timestamp は
runtime で configuration が有効になった時点ではないので、各 measurement record に deployment と configuration の identity を記録する。
warm 固定は SLO を人工的に良く見せうるので、SRE Book Ch.4 "Don't overachieve"（訳: 過剰達成しない）の趣旨に照らし、
warm 条件での baseline から target を締めすぎない。

### その他の caveat

- Azure Container Apps ingress の既定 240 秒は idle（バイト間）timeout として振る舞う（#183。ADR-0028「影響」）。platform の制約であり
  threshold の根拠にしないが、idle が 240 秒に達した切断は「終端 event なし」の bad event になる
- supported client には `maxLength` がなく、backend は `message` を最大 4,000 文字に制限する（2026-09-07 時点の `frontend/app/chat.tsx` で未解消）。
  effective SLO の前に再現可能な input contract を定義し、長い intended-user input を暗黙に exclusion にしない
- diagnostic metrics（client / ingress / application / database / LLM の elapsed time、TTFT、`done` 到達率、response status、
  revision と image の identity、CPU / memory / replica、dependency の error / latency / rate limiting、telemetry coverage）は
  SLI の変化を説明するために使い、それ自体から compliance を判定しない。user outcome に基づく別の rationale なしに SLO へ昇格させない
- measurement record には critical user journey、good-event rule、measurement point、schema、query、tool、timeout、
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

> "From the user perspective, then, every service has independent uptime and data integrity requirements, even if these requirements are implicit."
> 訳: したがって user の視点では、すべての service は、たとえ暗黙であっても、独立した uptime の要件と data integrity の要件を持つ。

出典: SRE Book Ch.26「Data Integrity」§Data Integrity's Strict Requirements。

## 変更履歴

ヘッダ表の Date / Approval Date / Revisit Date と Status が SLO の version と effective boundary を表す。最初の採用時に
SLI implementation version、query または tool version、supporting evidence の link をあわせて記録する。

| 日付 | 変更内容 | 定量的 decision |
| --- | --- | --- |
| 2026-08-30 | user-facing SLI specification、現在の evidence boundary、将来の decision procedure を記録 | なし |
| 2026-09-07 | ADR-0028 決定 11 の 2 閾値 measurement semantics を正本化。response contract を SSE 契約への参照に差し替え、bad event を具体化。`REQUEST_TIMEOUT_MS` の記述を #199 の廃止に合わせて修正（PR #241） | なし |
| 2026-09-07 | the Google SRE books の大原則とこの service への導出を先頭に置き、Workbook Appendix A の形へ全面改訂。最初の iteration と位置づけ、synthetic transaction を primary SLI implementation として採用。compliance period と review cadence の暫定値、current / aspirational の 2 段、critical dependency と composite 上限、SLO の対象外の設定を記録（#242） | なし。数値は baseline 後に記入 |

## 参考資料

### 主な方法論上の根拠

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
