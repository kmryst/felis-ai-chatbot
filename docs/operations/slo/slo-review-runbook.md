# SLI / SLO review runbook

この runbook は、`felis-ai-chatbot` の user-facing SLI / SLO を確立、測定、評価、調査、改善、revision するための
運用手順を定める。[slo-document.md](./slo-document.md) が service scope、SLI、SLO、measurement semantics と
その Rationale の正本、[error-budget-policy.md](./error-budget-policy.md) が有効な SLO と error budget を
engineering decision にどう適用するかの正本である。規範的な定義を evidence record へ複製せず、正本を更新する。

この runbook は新しい定量値を選択しない。定量値を決定し、review する手順だけを定める。

## 位置づけ: iterate するための手順

SRE Book Ch.4 は SLI / SLO を control loop の要素として置く。

> "Monitor and measure the system's SLIs. / Compare the SLIs to the SLOs, and decide whether or not action is needed. / If action is needed, figure out what needs to happen in order to meet the target. / Take that action."
> 訳: system の SLI を監視し測定する。SLI を SLO と比較し、action が必要かを決める。必要なら、target を満たすために何が起きる必要があるかを見極める。その action を取る。

出典: SRE Book Ch.4「Service Level Objectives」§Control Measures。

Workbook Ch.2 は、最初の SLI / SLO は正しくなくてよく、置いて測って feedback loop を作ることが最重要だと言う（slo-document.md「位置づけ」）。
この runbook はその feedback loop の手順であり、slo-document.md の「原則 6」の 4 つの出口（Change your SLO / Change your SLI implementation /
Institute an aspirational SLO / Iterate）へ review を接続する。

## 現在の前提

- SLI specification は確定済み（ADR-0028 決定 11。PR #241）。SLI implementation の方式は authenticated synthetic transaction に
  決定済みで、configuration（payload / identity / location / schedule / measurement timeout）は未決定
- effective な SLO target、threshold 1 / threshold 2 の値、error budget はない。Status は `Draft`
- Status が `Draft` の間、recurring review は「measurement を検証する」までで停止し、compliance と error budget は報告しない
- `/readyz` の結果を primary `/chat` SLI として使用しない（NO_SLO）
- current configuration（timeout、replica 数、ingress の制約）を SLO の根拠にしない。historical SLI result は starter SLO の入力として使い、
  その事実を slo-document.md の Rationale に記録する

<a id="initial-sli-and-slo-establishment"></a>

## 初回の SLI / SLO 確立

出力が既に存在し、その evidence が現在も有効な場合を除き、次の手順を順番に実施する。
停止条件は「evidence が無いこと」ではなく「Workbook が要求する記録が無いこと」に置く。実測が無いこと自体は停止理由にしない。

| 手順 | 入力 | 実施内容 | 出力 | 必要な evidence | 完了条件または停止条件 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| user を特定する | repository の目的、supported client、deployment scope | service に依存する user を特定し、service user と repository の読者を区別する | 文書化された user population | client と deployment の文書、user または stakeholder の記録 | intended user と supported client を区別できなければ停止する | 完了（slo-document.md「User」） |
| critical user journey を特定する | user population と product behavior | client からの送信から client-visible outcome までを追跡する | 代表的な critical user journey | frontend / backend の code path、dependency と authentication の挙動 | user journey または完了条件が曖昧なら停止する | 完了 |
| SLI specification を定義する | critical user journey | telemetry とは独立して user-visible result を記述する。request-driven なので availability と latency を対象にする | SLI specification | response contract、意図した no-context response、既知の failure mode | 測定不能または未定義の product requirement に成功条件が依存するなら停止する | 完了（ADR-0028 決定 11） |
| eligible / good / bad / excluded event と unclassifiable record を定義する | SLI specification と service scope | intended user の識別や application 到達前の failure を含め、再現可能な event rule を記述する | event classification rule | request contract、authentication semantics、client behavior、incident の例 | telemetry の欠落や対象外 traffic が暗黙に good または exclusion になるなら停止する | 完了 |
| SLI implementation を選ぶ | SLI specification と measurement point の候補 | 候補を quality、coverage、cost で比較し、最初の iteration では安い方を選ぶ。実測が無い場合は先に data source（authenticated synthetic transaction）を設定する | measurement point と方式 | 候補の比較 | event rule を再現できない方式なら停止する | 方式は完了（synthetic transaction）。configuration は未決定 |
| SLI implementation を実装し検証する | 選んだ方式 | payload、identity、location、schedule、measurement timeout を決め、下記「SLI implementation の検証」を通す | schema、tool、version、validation evidence | prototype record と field 単位の coverage | 必須 case が誤分類されるか、暗黙に失われるなら有効化を停止する | 未着手 |
| baseline を収集する | 検証済みの implementation | four-week rolling window と同じ長さ以上の期間、raw event、execution coverage、gap、configuration boundary を保存する。この期間は compliance period ではない | 再現可能な baseline evidence | raw record、tool version、timestamp、revision、image、configuration | eligible event または measurement coverage を確認できなければ停止する | 未着手 |
| threshold 1 / threshold 2 を提案する | baseline evidence（それぞれの分布） | 観測 percentile を単位で丸めて starter 値とし、測定期間・丸め単位・「user experience との相関は未検証」を Rationale に記録する | 根拠を伴う threshold 1 / threshold 2 の案 | 分布と丸め規則 | current timeout や platform 制約（ingress idle timeout 等）だけが根拠なら停止する。baseline の観測 percentile を丸めて starter 値とすること自体は停止理由にしない | 未着手 |
| SLO target を提案する | baseline evidence と threshold の案 | baseline を切り下げて starter SLO とし、Rationale に「author が選んだ」「user experience との相関は未検証」を記録する。Workbook の 3 者合意（product / development / production）を project owner 1 名が兼ねる旨も記録する | 根拠を伴う current SLO target の案 | 切り下げ規則、dependency の composite 上限との比較 | 次のいずれかなら停止する: (a) 観測値を丸めずそのまま target にしている、(b) Rationale に上記の記載が無い、(c) refine の段階で current performance を上限として扱っている。baseline を starter SLO の入力にすること自体は停止理由にしない | 未着手 |
| compliance period を確認する | 暫定値（four-week rolling window） | rolling か calendar か、週の整数倍かを確認し、逸脱する場合に限り理由と historical replay を記録する | 確定した compliance period | default から逸脱する場合に限り historical replay または baseline analysis | window が週の整数倍でない、または rolling / calendar の選択理由が無い場合に停止する。Workbook の default を採ることは停止理由にしない | 暫定値あり |
| measurement frequency と measurement timeout を決める | implementation の試行結果、cost | frequency は cost の上限と error budget の粒度の下限の間で選ぶ。measurement timeout は threshold 2 より長くし、censoring の影響を確認する | configuration と根拠 | 試行、gap analysis、censoring analysis、cost | 設定によって SLI の意味が変わる、または報告されない censoring が生じるなら停止する | 未着手 |
| error budget と policy の適用方法を確認する | SLO と compliance period の案 | request-based error budget を導出し、policy の action（critical path 限定 freeze）が実行可能であることを scenario walkthrough で確認する | error budget の計算と適用する policy | event 単位の計算、scenario walkthrough | error budget を downtime に変換している場合、または policy の action を実行できない場合は停止する | policy は暫定で記録済み |
| SLO を承認して記録する | 完成した案、validation evidence、evidence sufficiency decision | ヘッダ表（Status / SLO Version / Author / Date / Reviewers / Approvers / Approval Date / Revisit Date）を記入し、Status を `Published` にする | 将来に向けて effective になる SLO | review record、関連 evidence、`sufficient` の判定 | 定量項目に Rationale がない、evidence が `insufficient`、または SLO Version / Approval Date が未記入なら停止する。過去へ遡って適用しない | 未着手 |
| 測定を開始する | effective な SLO と検証済みの implementation | 承認済みの収集を開始し、raw evidence の到着を確認して最初の evidence record を作成する | 収集開始を確認した evidence | 最初の record、収集状態、deployment / configuration identity | 収集または classification が承認済みの implementation と一致しなければ compliance の報告を停止する | 未着手 |

## 定量値の決定手順

一般的な方法を説明する際は Google SRE Book と The Site Reliability Workbook の terminology を使用する。
Azure の implementation と product behavior には Microsoft の terminology を使用する。

SLO の決定項目は次の表に限る。client 側の打ち切り、request timeout、retry、concurrency、capacity、RTO / RPO は
SLO の決定項目ではなく、それぞれの正本に記録する（slo-document.md「SLO の対象外の設定」）。

| 決定項目 | 意味と適用する guidance | 必要な evidence | decision と記録 |
| --- | --- | --- | --- |
| threshold 1（最初の content event まで） | good event rule の時間条件。ADR-0028 決定 11。measurement timeout とは区別する | baseline の分布、丸め単位の選択理由 | 候補を比較し `slo-document.md` に記録する。client、dependency、distribution の変更後に review する |
| threshold 2（content event 間、最後の content event → `done`） | 同上 | 同上 | 同上 |
| SLO target（current） | eligible event のうち good event を求める割合。baseline を切り下げた starter SLO から始め、Table 2-5 SLO decision matrix で tighten / loosen を判断する | baseline、failure impact、dependency の composite 上限、切り下げ規則 | `slo-document.md` と Rationale に記録し、将来に向けてのみ revision する |
| SLO target（aspirational） | current SLO より厳しく、policy の action を発動しない値 | current SLO の運用実績、client-side instrumentation の有無 | 任意。採用時は `slo-document.md` と policy に記録する |
| Compliance period | SLO compliance と error budget を評価する期間。default は four-week rolling window | default から逸脱する場合に限り historical replay | `slo-document.md` に記録する |
| Alerting window（alert look-back window） | 特定の alert が使用する data interval。compliance period とは異なる | effective な SLO、event volume、検出要件 | alert source に記録し policy から参照する |
| Measurement frequency | 測定を試行する頻度。設定された schedule と実際の coverage は同じではない | cost（Azure OpenAI 呼び出し）、error budget の粒度、scheduler の実 coverage | 設定と実 coverage を分けて `slo-document.md` と evidence に記録する |
| Measurement timeout | measurement tool が client-visible result を待つのを終了する時点。censoring を決める設定であり threshold ではない | threshold 2、dependency behavior、未完了 request の classification | SLI implementation と `slo-document.md` に記録する |
| campaign の sample size または request count | 評価に使用する eligible observation の数。普遍的な最小値はない | campaign が支える decision、想定 variance | campaign plan に記録する |
| Burn rate threshold | Workbook Table 5-8 を starting point とし 28 日 window に再計算。low-traffic のため ticket のみ | baseline への replay（precision、recall、detection time、reset time） | alert source と policy に記録する |
| Review frequency | 立ち上げ期は monthly、安定後は quarterly。Revisit Date は Approval Date + 6 か月（暫定） | review が適時で actionable か | この runbook に記録する |

## SLI implementation の検証

### repository と runtime の identity を記録する

repository root で実行する。次の command は読み取り専用で current fact を表示するものであり、将来の target ではない。

```bash
git rev-parse HEAD
git status --short --branch
rg -n "min_replicas|max_replicas|cpu|memory" terraform/ephemeral/main.tf
rg -n "LLM_PROVIDER|CHAT_DISABLED|CHAT_API_KEY" backend/app/config.py terraform/ephemeral/main.tf
```

現在 deployment されている serving app について、secret value を含めず configuration を記録する。

```bash
az containerapp show \
  --resource-group rg-felisaichatbot-dev-tf \
  --name ca-felisaichatbot-dev \
  --query '{revision:properties.latestRevisionName,readyRevision:properties.latestReadyRevisionName,runningStatus:properties.runningStatus,minReplicas:properties.template.scale.minReplicas,maxReplicas:properties.template.scale.maxReplicas,image:properties.template.containers[0].image,cpu:properties.template.containers[0].resources.cpu,memory:properties.template.containers[0].resources.memory,traffic:properties.configuration.ingress.traffic,probes:properties.template.containers[0].probes,environmentVariableNames:properties.template.containers[0].env[].name}' \
  --output json

az containerapp show \
  --resource-group rg-felisaichatbot-dev-tf \
  --name ca-felisaichatbot-dev \
  --query 'properties.template.containers[0].env[?name==`CHAT_DISABLED` || name==`LLM_PROVIDER` || name==`DSN_CONFIG_CHECKSUM`].{name:name,value:value}' \
  --output json

revision_name="$(az containerapp show \
  --resource-group rg-felisaichatbot-dev-tf \
  --name ca-felisaichatbot-dev \
  --query properties.latestRevisionName --output tsv)"
az containerapp replica list \
  --resource-group rg-felisaichatbot-dev-tf \
  --name ca-felisaichatbot-dev \
  --revision "$revision_name" \
  --query '[].{name:name,runningState:properties.runningState}' \
  --output json

container_apps_environment_id="$(az containerapp show \
  --resource-group rg-felisaichatbot-dev-tf \
  --name ca-felisaichatbot-dev \
  --query properties.managedEnvironmentId --output tsv)"
az monitor diagnostic-settings list \
  --resource "$container_apps_environment_id" \
  --output json
```

上の query が返す `probes` は、Terraform に probe の定義が無い場合、Azure が ingress 有効化時に付与した default の TCP probe である。
default による付与か明示定義かを区別して evidence に記す（後述の「Platform の確認」）。

resource name が変わった場合は、command の実行前に Terraform と Azure resource inventory から resolve する。
`DATABASE_URL`、`CHAT_API_KEY` などの secret value を出力しない。現在 checkout している commit と deployment された container image は
一致するとは限らないので、両方の identity を記録する。

この手作業を 3 回目以降も手動で行う場合は automation の Issue を起票する。

> "If you're performing a task for the first time ever, or even the second time, this work is not toil. Toil is work you do over and over."
> 訳: ある作業を初めて、あるいは 2 回目に行うなら、それは toil ではない。toil とは何度も繰り返し行う作業である。

出典: SRE Book Ch.5「Eliminating Toil」§Toil Defined。

### classification の coverage を検証する

有効化の前と SLI implementation の変更後に、管理された test event を使用して次の path をすべて検証する。
SSE の系列は ADR-0028 決定 9 の共有 contract fixture（[docs/contracts/chat-sse/README.md](../../contracts/chat-sse/README.md)）を test input に使う。

- intended user からの有効な request に対する通常の reply
- intended user からの有効な request に対する、意図した no-context response
- supported client での parsing または rendering の failure
- intended interaction に対する誤った authentication または authentication の欠落
- request が FastAPI に到達する前の failure
- application、database、LLM または provider の failure
- `error` event での終端（class 別: `timeout` / `rate_limit` / `server_error` / `bad_request` / `content_filter`）
- 終端 event（`done` / `error`）なしの切断
- 最初の content event が threshold 1 の案を超えた response
- content event 間、または最後の content event から `done` までの間隔が threshold 2 の案を超えた response
- `content_filter` 終端で表示済み partial text の撤回を伴う系列
- measurement timeout
- 不正または欠落した telemetry
- exclusion とする user 以外の traffic、または事前に宣言した test traffic
- collection の中断と再開
- deployment または measurement version の boundary

各 path について、期待する eligibility と outcome、観測した field、実際の classification、timestamp、raw record を保存する。
必須 path が失われる、誤分類される、または識別不能な場合は有効化を停止する。

### evidence が十分かを確認する

対象の decision に必要な evidence が十分かを判断する方法を、事前に宣言する。event count、representativeness、execution coverage、
gap distribution、unclassifiable record、timeout censoring、configuration change、warm / cold semantics を確認する。
普遍的に適用できる sample size は定められていない。

事前に宣言した基準を満たさない場合は、次のとおり記録し、無理に pass または fail と判定しない。

> この SLO を信頼できる形で評価するための evidence が不足している。

判定は evidence record に、対象の decision または compliance period、事前に宣言した基準、結果（`sufficient` / `insufficient`）、
coverage、gap、unclassifiable record、timeout censoring、configuration boundary、evidence への link とともに記録する。
最初の `Published` SLO には、SLI implementation validation と baseline の両方について `sufficient` の判定が必要である。
その後も、`insufficient` と判定した compliance period の SLO compliance、error budget、policy action は報告または発動しない。

## 測定と評価

1. `slo-document.md` から effective な SLO version、service scope、SLI implementation、threshold 1 / threshold 2、SLO target、
   compliance period、policy link を確認する
2. repository、deployment、configuration、client、measurement tool、dependency の identity を記録する
3. 承認済みの raw event source が、今回評価する compliance period 全体を coverage していること、および期間内に schema や
   measurement semantics が変わっていないことを確認する
4. `slo-document.md` に記録された、承認済みで version 管理された query または tool を実行する。
   現在は synthetic transaction が未実装なのでここで停止する。synthetic transaction SLI の実装がマージされ、
   `slo-document.md` に schema / tool / version が記録された時点で解除する
5. raw evidence、または再現可能で変更されない参照を保存する
6. eligible、good、bad、excluded event と unclassifiable record を数え、exclusion と unclassifiable record を説明する
7. event count から good event の割合を計算し、宣言した compliance period の effective な SLO target と比較する
8. 許容される bad event と残りの error budget を request 単位で計算する
9. 採用済みの implementation と decision rule が policy に記録されている場合にのみ、burn rate を計算する
10. SLO compliance を示す前に、evidence が十分かを確認する
11. 結果を記録し、measurement が有効な場合にのみ policy の action と調査へ進む

既存の collector（`scripts/collect-probe-records.sh`）は過去の `/readyz` workflow record を保存できるが、supporting evidence のままである。
出力を primary `/chat` SLI として使用せず、欠落した scheduled run が成功したと推定しない。

## 定期的な review と改善

SLO が effective になった後、次の順序で実施する。Status が `Draft` の間は「measurement を検証する」までで停止する。

| 手順 | 確認または実行 | 記録 | 停止条件 | 正本の更新先 |
| --- | --- | --- | --- | --- |
| current SLO を読む | effective version、scope、SLI implementation、target、compliance period、policy | version と effective boundary | effective で内部的に一貫した SLO がない | `slo-document.md` |
| measurement を検証する | schema、source coverage、query または tool、gap、timeout、deployment boundary | validation result と limitation | eligibility、outcome、coverage を確認できない | `slo-document.md` の SLI implementation、`docs/verification/` の raw evidence |
| SLI を測定する | 承認済みの raw event source と version 管理された query または tool | count、query identity、period、evidence location | measurement が承認済みの implementation と異なる | evidence record |
| SLO compliance と error budget を評価する | SLI result、target、compliance period、bad event count | 過去に遡って reclassification していない結果、残りの error budget | evidence が不足している | evidence record と関連する Issue |
| 必要な場合に burn rate を評価する | 採用済みの formula、alerting window、threshold、no-data behavior | input、result、alert behavior | burn rate の使用が採用されていない、または data が無効 | policy または alert source |
| engineering action を決定する | 有効な measurement、user impact、残りの error budget、提案する作業の risk | policy の action（freeze の発動・解除・例外）と根拠 | evidence が矛盾する | 関連する Issue または PR と evidence record |
| 調査する | 下記「調査順序」 | timeline、observation、否定した原因、evidence link | user、security、data への即時 risk を先に封じ込める必要がある | incident または evidence record |
| hypothesis を立て controlled change を行い再測定する | 下記「hypothesis と controlled change」 | hypothesis、change identity、before / after の evidence | 安全性、rollback、attribution が不十分 | code、Terraform、ADR、Issue または PR |
| SLI、SLO、policy を review する | Table 2-5 SLO decision matrix と 4 つの出口 | 維持または将来に向けた revision の decision | SLO miss だけが target を緩める根拠になっている | 該当する SLO document、policy、runbook |

review の判断は Workbook Table 2-5「SLO decision matrix」を使う。SLO の達成状況、toil、customer satisfaction の 3 軸で action を決める。

| SLO | Toil | Customer satisfaction | Action（原文） | 訳 |
| --- | --- | --- | --- | --- |
| Met | Low | High | "Choose to (a) relax release and deployment processes and increase velocity, or (b) step back from the engagement and focus engineering time on services that need more reliability." | (a) release と deployment の手順を緩めて velocity を上げるか、(b) この engagement から手を引いて、より reliability を必要とする service に engineering の時間を向ける |
| Met | Low | Low | "Tighten SLO." | SLO を締める |
| Met | High | High | "If alerting is generating false positives, reduce sensitivity. Otherwise, temporarily loosen the SLOs (or offload toil) and fix product and/or improve automated fault mitigation." | alert が false positive を出しているなら感度を下げる。そうでなければ SLO を一時的に緩め（または toil を減らし）、product を直すか自動の fault mitigation を改善する |
| Met | High | Low | "Tighten SLO." | SLO を締める |
| Missed | Low | High | "Loosen SLO." | SLO を緩める |
| Missed | Low | Low | "Increase alerting sensitivity." | alert の感度を上げる |
| Missed | High | High | "Loosen SLO." | SLO を緩める |
| Missed | High | Low | "Offload toil and fix product and/or improve automated fault mitigation." | toil を減らし、product を直すか自動の fault mitigation を改善する |

出典: The Site Reliability Workbook Ch.2「Implementing SLOs」§Decision Making Using SLOs and Error Budgets、Table 2-5。

本 project では customer satisfaction は project owner 自身の判断であり、その事実を review record に書く。
「SLO miss だけを理由に緩めない」は維持するが、Missed / Low toil / High satisfaction なら緩めてよい経路を Table 2-5 は明示している。
一時的な緩和に期限と恒久修正の計画を付ける形も、SLO revision の一形態として認める。

> "we also temporarily dialed back our SLO target, using the 75th percentile request latency."
> 訳: 我々はまた、75 パーセンタイルの request latency を使って、SLO target を一時的に引き下げた。

出典: SRE Book Ch.6「Monitoring Distributed Systems」§Bigtable SRE: A Tale of Over-Alerting。

review で coverage の不足が見つかった場合の出口は slo-document.md「原則 6」の 4 つ（Change your SLO / Change your SLI implementation /
Institute an aspirational SLO / Iterate）であり、最初の数回は "err on the side of quicker and cheaper"（訳: より速く安い方に倒す）を選ぶ。

## 調査順序

調査開始時に SLO target を変更しない。

### Measurement の妥当性

最初に次を確認する。

- collection または query の defect、event の重複または欠落、schema drift
- intended user と eligible event の classification
- client、ingress、application の measurement point における gap
- measurement timeout、right-censoring
- scheduler execution、collection gap、ingestion delay、clock behavior
- warm / cold condition、configuration または revision の boundary
- query、tool、SLI implementation の version
- synthetic transaction 自体の failure（scheduler、identity の期限切れ、測定側の network）と service の failure の区別

measurement が無効な場合は、影響した期間を保存し、結果を application に帰属させる前に measurement を修正する。

### Application の確認

- request validation、authentication、processing、response serialization
- embedding、RAG retrieval、no-context handling、provider response
- database query、connection handling、blocking I/O
- dependency の latency、error、limit、retry、cancellation、timeout behavior
- concurrency と resource occupancy
- client の parsing、rendering、cancellation、retry behavior

### Platform の確認

Microsoft Azure の terminology と current configuration に基づき、次を確認する。

- Azure Container Apps の revision、replica、ingress、startup probe、liveness probe、readiness probe、scaling、platform event
- CPU、memory、replica count、restart、saturation の evidence
- network と private database path
- Azure service と dependency の limit
- diagnostic setting、log ingestion、metric coverage

`minReplicas` は構成上の target であり、replica availability を保証しない。

Terraform には probe の定義がない。Azure Container Apps は ingress が有効な container app の main container に、probe 種別ごとの定義が
無ければ default の **TCP probe**（startup / readiness / liveness。port は ingress の target port）を自動付与する。したがって現在の runtime
には TCP の default probe があり、HTTP probe は定義されていない。`az containerapp show --query 'properties.template.containers[0].probes'`
の出力で確認し、default による付与か明示定義かを evidence に記す。

TCP probe は port が listen していることしか確認せず、application の `/readyz` も critical user journey も観測しない。
application の `/readyz` endpoint と、それを呼び出す GitHub Actions workflow は Azure Container Apps の `readiness probe` ではなく、
この SLI の implementation でもない（NO_SLO）。

### SLO の妥当性

measurement、application、platform を確認した後に限り、次を review する。

- SLI が引き続き critical user journey を表しているか
- target が引き続き user / product / business requirement を表しているか
- reliability とコストの trade-off に根拠があるか
- risk tolerance、architecture、dependency、service scope が変わったか
- incident または user impact が error budget の消費に反映されていないか
- current performance を limit と誤認しているのではなく、実在する dependency constraint（slo-document.md「Critical dependency と
  composite 上限」）のためにのみ SLO を達成できないのか

## hypothesis と controlled change

次の流れを Issue または measurement plan に記録する。

```text
observation
-> falsifiable hypothesis
-> measurable success criterion
-> controlled change and rollback
-> deployment and configuration boundary
-> comparable measurement
-> before-and-after comparison
-> accept or reject the hypothesis
```

attribution が明確になる場合は、変更を切り分ける。技術的に分離できない変更や、分離によって安全性が低下する変更は分けない。
measurement 自体の検証が目的である場合を除き、effective な SLO、query、service implementation を同じ比較の中で変更しない。

## 比較可能な条件での再測定

結果の意味を変えうる次の条件をすべて記録し、比較する。

- endpoint、critical user journey、payload、authentication、supported client
- region、measurement location、event count、concurrency、request interval
- threshold 1 / threshold 2、measurement timeout
- warm / cold state、`min_replicas`、`max_replicas`、CPU、memory
- commit、application revision、container image、measurement tool version
- dependency provider、state、limit、configuration、retry behavior
- measurement point、schema、query、aggregation、collection coverage、ingestion behavior

関連する条件に差がある場合は、予想される影響を説明する。その影響を分離できなければ、結果は直接比較できないと明記する。
boundary を隠すために、互換性のない series を統合しない。

## evidence の記録

既存の `docs/verification/<campaign>/observations.md` pattern と、利用可能な場合は machine-readable な raw record を使用する。
postmortem も同じ pattern に置く。SLO 作業だけのために新しい evidence framework を追加しない。

measurement または review の record には、該当する次の情報を含める。

- 目的、critical user journey、hypothesis、測定可能な success criterion
- period boundary と timezone
- SLO version、SLI implementation version、query または tool version
- timestamp、commit SHA、deployment revision、container image または digest、region
- current `min_replicas`、`max_replicas`、CPU、memory、関連する platform configuration（observed configuration であることを明示する）
- measurement source、location、command または tool、schema、raw evidence の path
- payload class、authentication method、event count、concurrency、request interval、threshold 1 / threshold 2、measurement timeout
- eligible、good、bad、excluded event と unclassifiable record の count、exclusion の根拠
- SLI result、measurement が有効な場合の SLO compliance、採用済みの場合に限る error budget と burn rate
- execution coverage、collection gap、ingestion delay、censoring、configuration boundary、その他の limitation
- before / after condition、comparison result、採用または却下した hypothesis
- resulting engineering decision と関連する Issue、PR、incident、ADR

historical measurement は当時の定義のまま保存する。後の SLI / SLO に合わせて evidence を書き換えず、factual error は明示的な
correction として追記する。

## SLO revision

SLO violation だけを理由に SLO を緩めない。revision には user、product、business、risk、コスト、architecture、dependency、
measurement validity の evidence（Table 2-5 の 3 軸を含む）が必要であり、次の手順に従う。

1. current document と review の契機になった result を保存する
2. SLO validity より先に measurement validity、application、platform を調査する
3. 変更された requirement または assumption を記述し、supporting evidence を参照する
4. 4 つの出口のどれを選ぶかを、投資対効果で決める
5. error budget policy、alert、query、historical comparability への影響を review する
6. old value、new value、根拠、supporting evidence、series boundary を記録し、ヘッダ表（Date / Approval Date / Revisit Date / Status）を更新する
7. revision を将来に向けて適用し、以前の SLO history を保持する
8. revision 後の implementation を検証してから SLO compliance の評価に使用する

変更が architectural decision であるか、repository の ADR criteria を満たす場合にのみ ADR を使用する。すべての SLO edit に ADR を要求しない。
historical failure を消すために、過去の target や classification を変更しない。

## review の契機

review cadence は立ち上げ期 monthly、安定後 quarterly（暫定）。cadence とは別に、次のいずれかに該当した場合は review を開始する。

- user population、supported client、service scope、critical user journey が変わった
- incident または重大な user impact を SLI が表していない。とくに SLO alert が鳴らずに手動で発見した incident
- error budget policy の Outage Policy（単一 incident が budget の 20% 超を消費）に該当した
- SLI の変化が繰り返し user impact と対応しない、または measurement から説明できない結果が出る
- measurement point、schema、query、tool、collection system、timeout、event classification が変わった
- architecture、dependency provider、revision behavior、scaling、capacity、cost constraint が変わった
- warm / cold semantics、または他の comparability condition が変わった
- user / product / business / reliability / security / compliance requirement が変わった
- error budget policy の action が繰り返し影響に比例しない、または実行できない
- burn rate alerting を採用し、noise が多い、incident を見逃す、または action に必要な event volume がない
- aspirational SLO を current SLO に昇格する条件（current SLO の運用実績と client-side instrumentation の有無）が揃った

page を発生させなかった incident ほど monitoring の gap を示すという趣旨と、その引用は
[error-budget-policy.md](./error-budget-policy.md) の §outage 時の対応 を正本とする。

## 参考資料

### 方法論の primary source

- [Introduction](https://sre.google/sre-book/introduction/)
- [Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Embracing Risk](https://sre.google/sre-book/embracing-risk/)
- [Eliminating Toil](https://sre.google/sre-book/eliminating-toil/)
- [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)
- [Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [Monitoring](https://sre.google/workbook/monitoring/)
- [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [Example SLO Document](https://sre.google/workbook/slo-document/)
- [Example Error Budget Policy](https://sre.google/workbook/error-budget-policy/)

### platform guidance と cross-check

- [Define reliability based on user-experience goals](https://docs.cloud.google.com/architecture/framework/reliability/define-reliability-based-on-user-experience-goals)
- [Architecture strategies for defining reliability targets](https://learn.microsoft.com/en-us/azure/well-architected/reliability/metrics)
- [Architecture strategies for monitoring workload reliability](https://learn.microsoft.com/en-us/azure/well-architected/reliability/monitoring)
- [Monitor Azure Container Apps metrics](https://learn.microsoft.com/en-us/azure/container-apps/metrics)
- [Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [\[O.SI.5\] Set and monitor service level objectives against performance standards](https://docs.aws.amazon.com/wellarchitected/latest/devops-guidance/o.si.5-set-and-monitor-service-level-objectives-against-performance-standards.html)
- [REL06-BP06 Regularly review monitoring scope and metrics](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_monitor_aws_resources_review_monitoring.html)

### project の根拠資料

- [ADR-0028: /chat の SSE 化と応答契約の固定](../../adr/0028-chat-sse-response-contract.md)
- [`/chat` SSE 共有 contract fixture](../../contracts/chat-sse/README.md)
- [frontend SSE 実行計画（synthetic transaction SLI の起票トリガー）](../frontend-sse-execution-plan.md)
