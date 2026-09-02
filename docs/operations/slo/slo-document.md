# SLI / SLO 文書

## 目的

この文書は、`felis-ai-chatbot` で測定する user-facing reliability の正本である。
SLI specification と特定の SLI implementation を分離し、SLO を採用する前に必要な
evidence と、未決定の項目を記録する。

現時点で有効な定量的 SLO はない。SLI threshold、SLO target、
compliance period、measurement frequency、measurement timeout、client timeout、
request timeout は未決定である。この文書に記載する現在の configuration と
過去の observation は evidence であり、将来の target ではない。

SLO 採用後の engineering decision は
[error-budget-policy.md](./error-budget-policy.md)、初回策定、measurement、review、
revision の手順は [slo-review-runbook.md](./slo-review-runbook.md) を正本とする。

## サービス範囲

対象とするサービス体験は、supported client と認証済みの `POST /chat` endpoint で
構成される RAG chatbot の操作である。

構成は 2026-09-01〜09-02 に変わった。supported client は Azure Container Apps に
deployment された frontend（`ca-felisaichatbot-dev-front`。Easy Auth 付き）であり、
client は BFF（`POST /api/chat`）だけを呼ぶ。backend は internal ingress で、
BFF 経由でのみ到達する。`LLM_PROVIDER` は `azure-openai` で、実際に Azure OpenAI を
呼ぶ（[llm-provider-cutover](../../verification/llm-provider-cutover/observations.md)）。
2026-09-02 の読み取り専用確認では backend image は `backend:sha-b6d90f7` で、
deployment 済み image と `main` の一致を確認している
（[frontend-image-sync](../../verification/frontend-image-sync/observations.md)）。
この構成変更は**事実の更新であり、下記の SLI / SLO の未決定事項を解消しない**。

後の decision でサービス定義を変更しない限り、次はこの SLO の範囲外とする。

- 意図したユーザー操作ではない匿名の Internet traffic
- `/livez`、`/readyz`、database observation の freshness、infrastructure metrics を
  単独で評価した結果
- 回答内容の semantic quality、factual accuracy、source quality
- 独自の運用文書と既存の RTO / RPO requirement を持つ backup recovery と
  database durability

これらの signal や requirement が重要でないという意味ではない。同じ user outcome を
表さないため、この request-based SLI に暗黙に混在させないという境界である。

## ユーザー

現在の intended user は、Easy Auth（Entra ID）で認証し、アプリのロール `Chat.Use` を
割り当てられたアカウントから chatbot を操作する project owner である。`Chat.Use` の
割当は 2026-09-02 時点で所有者 1 アカウントのみで、他のアカウントは `AADSTS50105` で
拒否される（Issue #208）。外部 customer population、SLA、独立した business requirement は
repository に記録されていない。

サービス範囲を拡張する前に、新しい user population、supported client、authentication
contract、user expectation、failure impact、risk tolerance を記録する。現在の定義が
新しいユーザーも表すと仮定せず、SLI specification を再評価する。

## Critical user journey

intended user が、認証済みの supported client から構文上有効で supported な質問を送信し、
client が render できる response を受け取る。no-context notice は application が意図した安全動作
なので、client が受信して render できれば journey は完了している。client が response を
parse または render できなければ、transport response が返っただけでは完了としない。

Semantic correctness は application test と、将来必要になった quality evaluation の
手順で評価する。HTTP success から semantic correctness を推定せず、根拠のない別の
SLO として追加しない。

## SLI specification

primary SLI specification は、eligible user request のうち、SLI threshold 以内に
critical user journey を完了した request の割合である。SLI threshold は未決定なので、
現時点ではこの比率から SLO compliance を判定できない。

### Eligible event

次の条件をすべて満たす event を eligible event とする。

- supported client から `POST /chat` へ送られた intended-user submission である
- 文書化された request shape を使用している
- 文書化された authentication mechanism の対象である。authentication の失敗または欠落を
  理由に ineligible としない
- message が client-visible input contract を満たす
- 文書化された service scope と SLO version が有効な期間に発生している

SLI implementation は、HTTP status code だけでなく intended-user event を識別できなければ
ならない。そうしないと、意図しない Internet traffic が denominator を変えたり、
intended user の authentication failure や routing failure が exclusion と誤認されたりする。

### Good event

eligible event のうち、supported client が文書化された response contract に合う response を
SLI threshold 以内に受信し、parse して render できたものだけを good event とする。
normal chatbot reply と意図した no-context notice は、どちらもこの条件を満たせば
good event である。

### Bad event

測定できた eligible event のうち good event でないものは、すべて bad event とする。
intended interaction に影響する次の failure を含む。

- DNS、TLS、network、ingress、transport の failure
- authentication、routing、configuration の failure
- server error または dependency failure
- malformed response または response data の欠落
- SLI threshold を超えて到着した response
- qualifying response を観測する前に発生した client timeout または measurement timeout
- supported client が parse または render できない response

intended user の request は、application code へ到達する前に失敗したことを理由に
ineligible にしない。

### Exclusion

次の event は、文書化された scope data から再現可能に分類できる場合に限り除外できる。

- intended user population 以外の actor による traffic
- service processing 開始前に文書化された input contract を満たさない request
- 実行前に test または drill と識別し、intended-user population と分離した event
- effective SLO version または明示された service scope の外で発生した event

telemetry loss、collection failure、不都合な結果、planned maintenance、原因不明の failure は
自動的な exclusion ではない。eligible population または outcome を再構築できない場合は、
SLO を確実に評価するだけの evidence がないと記録する。

## SLI implementation

### Measurement point

SLI には application 到達前の failure と response の parse / render が含まれるため、
SLI implementation は supported client boundary を観測する必要がある。client-side
instrumentation と authenticated synthetic transaction が候補だが、採用する方式は
未決定である。

Azure ingress または application の measurement は coverage の cross-check と診断に
利用できるが、それだけでは client 側の DNS、TLS、network、client timeout、parse、
render を観測できない。synthetic transaction は user action を模擬するものであり、
real-user traffic の evidence ではない。

### 候補となる data source

repository と現在の runtime から、次の候補を確認した。

| Data source | 観測できるもの | この SLI に対する limitation | 現在の状態 |
| --- | --- | --- | --- |
| Supported-client instrumentation | intended request と client-visible outcome | 実装と intended user の識別方法が必要 | 未実装 |
| Authenticated synthetic transaction | 再現可能に模擬した critical user journey | real-user traffic の分布や文脈を表さない | 設計未決定 |
| `ContainerAppHTTPLogs` | Azure Container Apps ingress の path、status、`RequestDuration`、revision、replica | `RequestDuration` は最後の response byte 送信までで、client の parse / render は観測しない | 2026-08-30 の読み取り専用確認では Container Apps environment に diagnostic setting がなく、table は利用不可 |
| Application access log | FastAPI に到達した request の path、status、server duration | application 到達前の failure、authentication の妥当性、client-visible completion は観測しない | application が stdout へ出力しているが、SLO query は未実装 |
| `/readyz` GitHub Actions probe | 外部からの到達性、database reachability を含む application-level response、response に含まれる observation freshness | `/chat`、RAG retrieval、response parsing、frontend を実行せず、Azure Container Apps の `readiness probe` でもない | supporting operational signal としてのみ存在 |

Azure Container Apps の built-in metric `Requests` と `Average Response Time (Preview)`
（Metric ID は `ResponseTime`）は、診断と request count の突合に利用できる。ただし、
path ごとの complete client-visible good-event classification を提供せず、この primary SLI を
単独では実装できない。

### 評価方法

明示した compliance period について、次を event count から計算する。

```text
SLI = count of good eligible events / count of all eligible events
```

各 eligible event を response contract と SLI threshold に照らしてから集計する。結果には
eligible、good、bad、unclassifiable record、collection gap の各 count を残す。
request-based ratio を downtime に変換しない。

query が数値を返しただけでは有効な評価ではない。intended-user population を
識別できること、required field が揃うこと、measurement point が specification に合うこと、
collection gap を説明できること、評価対象の途中で measurement semantics が変わって
いないことを review で確認する。

### Query と計算

client-visible telemetry も synthetic transaction も未実装なので、承認済み query はない。
SLI implementation は次の分類を再現できなければならない。

1. effective SLO version と supported service scope の event を選ぶ
2. intended-user field と request-contract field から eligible event を特定する
3. client-visible outcome と elapsed time が採用済みの条件を満たす場合だけ good event にする
4. その他の測定済み eligible event は bad event にする
5. unclassifiable record と telemetry gap は good とせず、暗黙にも除外せず、別に報告する
6. event count から ratio を計算し、根拠となる evidence を保持する

承認済みの schema、query、tool version、validation evidence をこの文書に記録するまで、
SLO を有効にしない。

### Measurement frequency

measurement frequency は未決定である。想定する event volume、対応が必要な user-impact
duration、collection reliability、operational response capability、cost、候補方式の試行で
判明した gap を evidence として決定する。scheduler の nominal configuration は、実際に
execution が発生した evidence ではない。

採用した値、rationale、evidence、effective boundary はこの文書に記録する。候補 frequency を
検証する baseline collection period は、SLO の compliance period とは限らない。

### Timeout

SLI measurement に用いる measurement timeout、client timeout、request timeout は
未決定であり、それぞれ SLI threshold とは意味が異なる。

現在の configuration であり、target または recommendation ではない事実として、local
frontend は `REQUEST_TIMEOUT_MS` を `15_000 ms` に設定している。別経路の `/readyz` workflow は
`curl --max-time 30`（30 秒）を使用する。backend には `/chat` 全体を終了させる request timeout は
なく、database と LLM の個別 timeout および retry configuration はさらに別の layer にある。
これらの値と経路から、将来の `/chat` SLI threshold または measurement timeout を正当化
してはならない。

候補となる timeout は、censoring、resource use、dependency behavior、supported-client
contract との整合を試験してから選ぶ。

### 既知の measurement limitation

- deployment された frontend はあるが、real-user telemetry がない。intended user は
  2026-09-02 時点で所有者 1 アカウントのみで（Issue #208）、eligible event を生む
  実利用が継続的に存在しない
- authenticated `/chat` transaction と client-visible result の継続的な collection がない
- application log は FastAPI 到達前の request と client-visible completion を観測できない
- `ContainerAppHTTPLogs` は確認した Container Apps environment で有効になっていない
- `/readyz` の既存 series には scheduler coverage gap があり、現在の record は curl exit
  status を保持しない。この series は primary SLI の implementation ではなく、現在の
  Azure Container Apps に設定された `readiness probe` でもない
- frontend は trim 後の nonempty input を送信できる一方、`maxLength` がなく、backend は
  `message` を最大 4,000 文字に制限する。effective SLO の前に、supported client と backend
  で再現可能な input contract を定義し、長い intended-user input を暗黙に exclusion に
  しないようにする必要がある
- quantitative target を正当化できる独立した user、business、reliability requirement がない

## SLO

採用済みの SLO target はなく、定量的 SLO は有効ではない。次の項目は未決定である。
具体値を決めるときは [slo-review-runbook.md](./slo-review-runbook.md) の手順で required
evidence、trade-off、decision criteria を確認し、prospective に記録する。

| 決定項目 | 現在の状態 | 採用時の記録先 |
| --- | --- | --- |
| SLI threshold | 未決定 | 値、rationale、measurement semantics、effective boundary をこの文書に記録する |
| SLO target | 未決定 | requirement、または baseline evidence を入力にした根拠、owner、review evidence をこの文書に記録する |
| Compliance period | 未決定 | baseline / validation period と区別し、値と rationale をこの文書に記録する |
| SLI implementation | 未決定 | measurement point、schema、query または tool、version、limitation をこの文書に記録する |
| Measurement frequency | 未決定 | scheduler configuration と achieved coverage を分けてこの文書と evidence に記録する |
| Measurement timeout | 未決定 | SLI threshold、client timeout、request timeout と区別してこの文書に記録する |
| Client timeout | 現在の frontend の値はあるが、将来の decision は未決定 | client configuration とこの文書に記録する |
| Request timeout | `/chat` 全体の現在の設定はなく、将来の decision は未決定 | 実装する各 layer に記録し、この文書から参照する |
| Synthetic transaction configuration | 採用の要否を含め未決定 | 採用する場合は payload、identity、location、outcome、schema、tool、exclusion、limitation をこの文書に記録する |
| Evaluation period / alert look-back window | applicable な evaluation または alert の採用時に決定 | product と用途ごとの意味を query または alert source に記録し、compliance period と同じ期間を指す場合も関係を明示する |
| Burn rate alerting | 採用の要否を含め未決定 | decision rule は policy、実装値は alert source に記録する |
| Review frequency | 未決定 | runbook に記録し、measurement frequency と区別する |

最初の SLO target に用いる evidence には、次の経路がある。

- 独立した user、business、reliability requirement がある場合は、それを target proposal の
  根拠とし、measurement で feasibility を検証して iteration する
- defensible target がない場合は、declared semantics で baseline を収集し、starter SLO の
  入力に限って使用する。その根拠を記録し、user impact、risk、cost の evidence で
  iteration する

どちらの場合も現在の performance 自体を requirement にしない。過去の observation
campaign を採用済みの compliance period とみなさない。

retry configuration、campaign の sample size / request count、concurrency / request interval、
capacity-related configuration、RTO / RPO は、この service で必要になった場合に限り runbook の
decision procedure を使う。SLO の体裁を整えるためだけに decision を追加せず、application、
Terraform、recovery documentation など、その decision を実装する正本に記録する。

## Error budget

effective SLO target、compliance period、validated eligible-event measurement が揃うまで、
effective error budget は存在しない。request-based error budget は event count と同じ単位で
扱い、downtime minutes に変換しない。計算規則と engineering decision は
[error-budget-policy.md](./error-budget-policy.md) を正本とする。

## Diagnostic metrics

diagnostic metrics は SLI の変化を説明するために使い、それ自体から compliance を判定しない。
investigation の hypothesis に必要なものだけを選び、必要に応じて次を保持する。

- client、ingress、application、database、LLM の elapsed time
- response status、response-contract failure、client cancellation、timeout
- application revision、container image、replica、configuration identity
- CPU、memory、replica count、restart、scaling activity、ingress behavior
- database reachability と query behavior
- external dependency の error、latency、retry behavior、rate limiting
- telemetry coverage、ingestion delay、collection failure
- 条件を明示した latency distribution と event count

percentile または resource metric を、user outcome に基づく別の rationale なしに SLO へ
昇格させない。

## Warm / cold の区別

過去の事実と現在の事実を分けて記録する。

| 根拠資料 | Configuration と意味 | 比較可能性 |
| --- | --- | --- |
| 2026-08-26 に終了した Phase 1 observation | serving の `min_replicas` は `0`。external `/readyz` probe は主に、cold start が既存の curl timeout 前に完了したかを測定していた | historical diagnostic evidence に限る。primary `/chat` SLI ではなく、warm measurement と単一の連続 series として比較できない |
| ADR-0025 と 2026-08-30 の現在の runtime | Terraform の serving `min_replicas` / `max_replicas` と Azure runtime の `minReplicas` / `maxReplicas` は `1`。現在の serving revision は `ca-felisaichatbot-dev--0000003` | 新しい configuration boundary である。`min_replicas` / `minReplicas` は設定上の値であり、常に ready な warm replica があることや将来の target を保証しない |

Phase 1 record には scheduled-run gap と、curl timeout による right-censored failure がある。
記録された success ratio は observed probe outcome だけを表し、continuous service
availability ではない。historical record と configuration identity を保持し、current semantics
で書き換えない。

merge commit の timestamp は Azure runtime で configuration が有効になった時点ではない。
正確な runtime boundary を commit や PR から推定せず、各 measurement record に deployment
と configuration の identity を記録する。

## 有効日と version

quantitative SLO が approved ではないため、effective date と SLO version はない。最初の採用時に
decision date、effective date、owner、reviewer、SLI implementation version、query または
tool version、service scope、supporting evidence の link を記録する。新しい target や
semantics が過去にも有効だったかのように、historical event を再計算しない。

## 過去の evidence の比較可能性

measurement record には、次の変更を検出できる identity を含める。

- critical user journey、eligible population、good-event rule
- measurement point、schema、query、tool、timeout、collection method
- authentication、payload、location、event count、concurrency、request interval
- warm / cold condition、`min_replicas`、`max_replicas`、CPU、memory
- commit、application revision、container image、region、dependency mode

relevant condition が変わった場合は、変更時点で旧 series を閉じ、before / after を直接比較
できるかを説明する。event count を増やすためだけに異なる semantics の measurement を
統合しない。

## 既知の limitation

この文書が定めるのは定性的な SLI specification と decision boundary であり、
effective な定量的 SLO ではない。現在の measurement から critical user journey の
compliance を確実に判定することはできない。必要な SLI implementation と未決定の
定量的 decision は、runbook に従う今後の作業である。

## 変更履歴

| 日付 | 変更内容 | 定量的 decision |
| --- | --- | --- |
| 2026-08-30 | user-facing SLI specification、現在の evidence boundary、将来の decision procedure を記録。日本語化と正本間の責任分担を整理 | なし。新しい定量値はすべて未決定 |

## 参考資料

### 主な方法論上の根拠

- [Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [Example SLO Document](https://sre.google/workbook/slo-document/)

### Platform implementation と cross-check

- [Define reliability based on user-experience goals](https://docs.cloud.google.com/architecture/framework/reliability/define-reliability-based-on-user-experience-goals)
- [Concepts in service monitoring](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring)
- [Service level indicators in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/service-level-indicators-create)
- [Monitor logs in Azure Container Apps with Log Analytics](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [Monitor Azure Container Apps metrics](https://learn.microsoft.com/en-us/azure/container-apps/metrics)
- [Service level objectives (SLOs)](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-ServiceLevelObjectives.html)

### Project の根拠資料

- [ADR-0025: serving を min_replicas 1 へ変更し cold start による可用性 SLI の汚染を排除する](../../adr/0025-serving-min-replicas-1-for-sli-integrity.md)
- [フェーズ 1（低負荷ベースライン 72h）の実測記録](../../verification/observation-phase1/observations.md)
- [Issue #115: 外形監視の SLI 限定とコールドスタートコストの実測](https://github.com/kmryst/felis-ai-chatbot/issues/115)
- [Terraform serving configuration](../../../terraform/ephemeral/main.tf)
- [FastAPI request handling](../../../backend/app/main.py)
- [Application access logging](../../../backend/app/middleware.py)
- [Supported-client request handling](../../../frontend/app/chat.tsx)
