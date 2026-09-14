# SLI / SLO review runbook

この runbook は、`felis-ai-chatbot` の user-facing SLI / SLO を確立、測定、評価、調査、改善、revision するための
運用手順を定める。[slo-document.md](./slo-document.md) が service scope、SLI specification、SLI implementation、SLO と
その Rationale の正本、[error-budget-policy.md](./error-budget-policy.md) が有効な SLO と error budget を
engineering decision にどう適用するかの正本である。規範的な定義を measurement report や review record へ複製せず、正本を更新する。

この runbook は新しい定量値を選択しない。定量値を決定し、review する手順だけを定める。

## 位置づけ: iterate するための手順

SLI を測定し、SLO と比較して必要な対応を決め、実施結果を次の review へ戻す。この control loop を SLO 運用の基本とする。

根拠: [SRE Book Ch.4「Service Level Objectives」](https://sre.google/sre-book/service-level-objectives/)。

Workbook Ch.2 は、最初の SLI / SLO は正しくなくてよく、置いて測って feedback loop を作ることが最重要だと言う（slo-document.md「位置づけ」）。
この runbook はその feedback loop の手順であり、slo-document.md の「原則 6」で Workbook が示す 4 つの選択肢（SLO target の変更 /
SLI implementation の変更 / aspirational SLO の設定 / 反復改善）へ review を接続する。

## 現在の前提

- SLI specification は確定済み（ADR-0028 決定 11。PR #241）。SLI implementation の方式は authenticated synthetic transaction に
  決定済み。timestamp fields、event time、monotonic clock は確定済みで、その他の configuration
  （payload / service principal / credential / location / schedule / measurement timeout）は未決定
- effective な SLO target、2 つの latency threshold の値、error budget はない。`slo-document.md` と
  `error-budget-policy.md` の Status はともに `Draft`
- いずれかの Status が `Draft` の間、recurring review は「measurement を検証する」までで停止し、compliance と error budget は報告しない
- change freeze の実現方式は未決定。production deployment pipeline の設計時に選定・検証し、policy の `Published` 前に記録する
- `/readyz` の結果を primary `/chat` SLI として使用しない（NO_SLO）
- current configuration（timeout、replica 数、ingress の制約）を SLO の根拠にしない。historical SLI result は starter SLO の入力として使い、
  その事実を slo-document.md の Rationale に記録する

<a id="initial-sli-and-slo-establishment"></a>

## 初回の SLI / SLO 確立

出力が既に存在し、その evidence が現在も有効な場合を除き、次の手順を順番に実施する。
停止条件は「evidence が無いこと」ではなく「Workbook が要求する記録が無いこと」に置く。実測が無いこと自体は停止理由にしない。

baseline 収集に使用した configuration と、SLO compliance measurement に使用する承認対象の SLI implementation configuration を区別する。
baseline 後に決めた threshold、target、frequency または timeout が classification、coverage、right-censoring、または観測分布を変える場合は、
承認対象の configuration で SLI implementation を再検証し、比較可能な baseline を再収集する。

| 手順 | 入力 | 実施内容 | 出力 | 必要な evidence | 完了条件または停止条件 | 状態 |
| --- | --- | --- | --- | --- | --- | --- |
| user を特定する | repository の目的、supported client、deployment scope | service に依存する user を特定し、service user と repository の読者を区別する | 文書化された user population | client と deployment の文書、user または stakeholder の記録 | intended user と supported client を区別できなければ停止する | 完了（slo-document.md「User」） |
| critical user journey を特定する | user population と product behavior | client からの送信から client-visible outcome までを追跡する | 代表的な critical user journey | frontend / backend の code path、dependency と authentication の挙動 | user journey または完了条件が曖昧なら停止する | 完了 |
| SLI specification を定義する | critical user journey | telemetry とは独立して user-visible result を記述する。request-driven なので availability と latency を対象にする | SLI specification | response contract、意図した no-context response、既知の failure mode | 測定不能または未定義の product requirement に成功条件が依存するなら停止する | 完了（ADR-0028 決定 11） |
| eligible / good / bad event、total events から除外する event、outcome を判定できない measurement result の扱いを定義する | SLI specification と service scope | intended user の識別や application 到達前の failure を含め、再現可能な event classification rule を記述する | event classification rule | request contract、authentication behavior、client behavior、incident の例 | missing telemetry data や対象外 traffic が暗黙に good または total events からの除外になるなら停止する | 完了 |
| SLI implementation を選ぶ | SLI specification と measurement point の候補 | 候補を quality、coverage、cost で比較し、最初の iteration では安い方を選ぶ。実測が無い場合は先に data source（authenticated synthetic transaction）を設定する | measurement point と方式 | 候補の比較 | event rule を再現できない方式なら停止する | 方式は完了（synthetic transaction）。configuration は未決定 |
| SLI implementation の timestamp fields、event time、monotonic clock を定義する | critical user journey、measurement point、compliance period | wall clock の timestamp fields、SLI の event time、window boundary、latency 計測用 monotonic clock の取得位置を定義する | version 管理された timestamp fields、event time、monotonic clock の定義 | supported client の request path、clock と window boundary の test case | event の期間帰属または latency を同じ raw record から再現できなければ停止する | 完了（slo-document.md「Timestamp fields」以下 3 小節） |
| baseline 収集用の SLI implementation configuration を実装し検証する | 選んだ方式と timestamp fields / event time / monotonic clock の定義 | payload、service principal、credential、location、schedule、measurement frequency、measurement timeout を記録し、下記「SLI implementation の検証」を通す | version 管理された SLI implementation configuration と validation results | prototype record、configuration、field 単位の coverage | 必須 case が誤分類される、暗黙に失われる、または right-censoring を評価できなければ停止する | 未着手 |
| baseline を収集する | 検証済みの baseline 収集用 configuration | four-week rolling window と同じ長さ以上の期間、raw event、scheduled runs の attempted / completed / missed counts、configuration version と変更時刻を保存する。この期間は compliance period ではない | 再現可能な baseline report | raw record、tool version、timestamp、deployment revision、image digest、使用した全 configuration | eligible event または measurement coverage を確認できなければ停止する | 未着手 |
| 2 つの latency threshold を提案する | baseline report（それぞれの分布） | 観測 percentile を単位で丸めて starter 値とし、測定期間・丸め単位・「user experience との相関は未検証」を Rationale に記録する | 根拠を伴う 2 つの latency threshold の案 | 分布と丸め規則 | current timeout や platform 制約（ingress idle timeout 等）だけが根拠なら停止する。baseline の観測 percentile を丸めて starter 値とすること自体は停止理由にしない | 未着手 |
| current SLO target の候補を作る | baseline report と threshold の案 | baseline を切り下げた値を starter SLO の候補とし、Rationale に「author が選んだ」「user experience との相関は未検証」を記録する。Workbook の 3 者合意（product / development / production）を project owner 1 名が兼ねる旨も記録する | 根拠を伴う current SLO target の候補 | 切り下げ規則、dependency risk の評価 | 次のいずれかなら停止する: (a) 観測値を丸めずそのまま target にしている、(b) Rationale に上記の記載が無い、(c) refine の段階で current performance を上限として扱っている。baseline を starter SLO の入力にすること自体は停止理由にしない | 未着手 |
| compliance period を確認する | 暫定値（four-week rolling window） | rolling か calendar か、週の整数倍かを確認し、逸脱する場合に限り理由と historical replay を記録する | 確定した compliance period | default から逸脱する場合に限り historical replay または baseline analysis | window が週の整数倍でない、または rolling / calendar の選択理由が無い場合に停止する。Workbook の default を採ることは停止理由にしない | 暫定値あり |
| current SLO target と SLO compliance measurement 用 configuration を確定し、再検証する | baseline report、threshold と target の候補、compliance period、cost | target と measurement frequency を一緒に決める。measurement timeout は latency threshold と区別して right-censoring を評価する。payload、service principal、credential、location、schedule を含む承認対象 configuration を version 管理し、「SLI implementation の検証」を再実行する | current SLO target と、承認対象の SLI implementation configuration の案および validation results | 切り下げ規則、event volume、cost、gap analysis、right-censoring analysis、raw test record | validation 対象と承認対象 configuration が異なる場合は停止する。baseline 収集用 configuration との差が classification、coverage、right-censoring、または観測分布を変える場合は baseline を再収集し、threshold と target の候補作成から繰り返す | 未着手 |
| error budget と policy の適用方法を確認する | SLO と compliance period の案 | request-based error budget を導出する。remaining error budget が正、0、負の場合、external dependency のみ、service 側を含む原因、原因不明、measurement が無効、既存の change freeze の各 scenario で policy の手順を確認する | error budget の計算と適用可能な policy | event 単位の計算、scenario walkthrough | `remaining error budget < 0` 以外を新たな発動条件にする、error budget を downtime に変換する、または一意に対応を決められない場合は停止する | policy は暫定で記録済み |
| change freeze の実現方式を決定し検証する | 承認候補の policy、production deployment pipeline と実際の production 変更経路 | production への反映を制御する point、freeze 状態の入力、実行 owner、例外と解除の経路、判断の記録先を決める。通常変更が停止し、policy の例外に該当する変更だけが通過することを scenario test で確認する | version 管理された実現方式と validation results | production 変更経路の一覧、通常変更・例外・解除の test record | 特定の PR、label、CI または deployment 製品を根拠なく選ぶ、production へ到達する経路が制御を迂回できる、または例外と解除を再現できない場合は停止する | 未着手（deployment pipeline 設計時） |
| SLO と error budget policy を承認して記録する | 完成した SLO 案、承認対象 configuration の SLI implementation validation results、baseline report、policy の scenario walkthrough、change freeze の実現方式と validation results | `slo-document.md` の SLO Version と、両文書の Status / Author / Date / Reviewers / Approvers / Approval Date / Revisit Date を記入し、同じ review record から両文書へ link する。effective date/time を RFC 3339 の UTC timestamp で記録し、両方の Status を同じ承認作業で `Published` にする | effective な SLO と適用可能な error budget policy | review record、関連する measurement data、data quality / coverage の確認結果、scenario walkthrough、change freeze の validation results | 定量項目に Rationale がない、data quality / coverage が SLO compliance の評価に不十分、change freeze の実現方式を検証できない、SLO Version / Approval Date / effective date/time が未記入、またはいずれか一方が `Draft` のままなら停止する。過去へ遡って適用しない | 未着手 |
| 測定を開始する | 両文書が `Published` の SLO と policy、承認済み SLI implementation configuration | 承認済みの収集を開始し、raw measurement result の到着を確認して最初の measurement report を作成する | 収集開始を確認した measurement report | 最初の raw measurement result、収集状態、commit SHA、deployment revision、image digest、configuration version | 収集または classification が承認済みの implementation と一致しなければ compliance の報告を停止する | 未着手 |

## 定量値の決定手順

一般的な方法を説明する際は Google SRE Book と The Site Reliability Workbook の terminology を使用する。
Azure の implementation と product behavior には Microsoft の terminology を使用する。

SLO の決定項目は次の表に限る。client 側の打ち切り、request timeout、retry、concurrency、capacity、RTO / RPO は
SLO の決定項目ではなく、それぞれの正本に記録する（slo-document.md「SLO の対象外の設定」）。

| 決定項目 | 意味と適用する guidance | 必要な evidence | decision と記録 |
| --- | --- | --- | --- |
| 最初の content event までの latency threshold | good event の時間条件。ADR-0028 決定 11。measurement timeout とは区別する | baseline の分布、丸め単位の選択理由 | 候補を比較し `slo-document.md` に記録する。client、dependency、distribution の変更後に review する |
| 隣接する content event 間、および最後の content event から `done` までの latency threshold | good event の時間条件。ADR-0028 決定 11。measurement timeout とは区別する | baseline の分布、丸め単位の選択理由 | 候補を比較し `slo-document.md` に記録する。client、dependency、distribution の変更後に review する |
| SLO target（current） | eligible event のうち good event を求める割合。baseline を切り下げた starter SLO から始め、Table 2-5 の decision matrix で厳格化 / 緩和を判断する | baseline、failure impact、dependency risk、切り下げ規則 | `slo-document.md` と Rationale に記録し、将来に向けてのみ revision する |
| SLO target（aspirational） | current SLO より厳しく、error budget policy に定めた対応を開始しない値 | current SLO の運用実績、client-side instrumentation の有無 | 任意。採用時は `slo-document.md` と policy に記録する |
| Compliance period | SLO compliance と error budget を評価する期間。default は four-week rolling window | default から逸脱する場合に限り historical replay | `slo-document.md` に記録する |
| Alerting window | 特定の alert が使用する data interval。compliance period とは異なる | effective な SLO、event volume、検出要件 | alerting rule に記録し policy から参照する |
| Measurement frequency | 測定を試行する頻度。設定された schedule と実際の coverage は同じではない | cost（Azure OpenAI 呼び出し）、error budget の粒度、scheduler の実 coverage | 設定と実 coverage を分けて `slo-document.md` と evidence に記録する |
| Measurement timeout | measurement tool が client-visible result を待つのを終了する時点。right-censoring を決める設定であり latency threshold ではない | 隣接する content event 間、および最後の content event から `done` までの duration に適用する latency threshold、dependency behavior、未完了 request の classification | SLI implementation と `slo-document.md` に記録する |
| campaign の sample size または request count | 評価に使用する eligible observation の数。普遍的な最小値はない | campaign が支える decision、想定 variance | campaign plan に記録する |
| Burn rate threshold | Workbook Table 5-8 を starting point とし 28 日 window に再計算。low-traffic のため ticket のみ | baseline への replay（precision、recall、detection time、reset time） | alerting rule と policy に記録する |
| Review frequency | 立ち上げ期は monthly、安定後は quarterly。Revisit Date は次の scheduled review date であり、最初の `Published` 化では Approval Date の 1 か月後とする | review が適時で actionable か | scheduled または triggered review のたびに、次回日を両文書へ記録する |

## SLI implementation の検証

### Timestamp fields、event time、monotonic clock を検証する

最初の実装と、これらの定義を変更する時には、`slo-document.md` の定義を複製せず、prototype raw record と制御可能な test clock で
次を検証する。

- `scheduled_for`、`attempt_started_at`、`completed_at`、`ingested_at` が RFC 3339 date-time format、UTC を表す time-offset `Z`、
  3 桁の fractional seconds である
- public frontend の `POST /api/chat` を開始する直前に `attempt_started_at` と monotonic clock の開始時刻を取得する
- `window_start` と同時刻の attempt を含み、`window_end` と同時刻の attempt を除外する
- window をまたいで完了した attempt、遅延実行、late ingestion でも、`attempt_started_at` による期間帰属が変わらない
- wall clock を前後へ補正しても monotonic clock で測定した duration が負にならず、各 latency 区間を raw duration から再計算できる
- SSE の byte 分割や同一 chunk 内の複数 event に左右されず、完全に検証された event の受理時点を取得する
- `done` の受理後に行う reader cleanup の時間が、最後の content event から `done` までの区間へ混入しない
- threshold との比較に表示用の丸め値を使わず、stream の観測順を wall clock で並べ替えない

### commit SHA と runtime configuration を記録する

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
一致するとは限らないので、commit SHA、deployment revision、image digest をそれぞれ記録する。

この手作業を 3 回目以降も手動で行う場合は automation の Issue を起票する。

同じ手作業が繰り返し必要になる場合は toil として扱い、automation を検討する。

根拠: [SRE Book Ch.5「Eliminating Toil」](https://sre.google/sre-book/eliminating-toil/)。

### Good / bad event の分類を検証する

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
- 最初の content event までの latency が、その threshold の案を超えた response
- content event 間、または最後の content event から `done` までの latency が、それらの duration に適用する threshold の案を超えた response
- `content_filter` 終端で表示済み partial text の撤回を伴う系列
- measurement timeout
- 不正または欠落した telemetry data
- exclusion とする user 以外の traffic、または事前に宣言した test traffic
- collection の中断と再開
- deployment revision または SLI implementation version の変更前後

各 path について、期待する eligibility と outcome、観測した field、実際の classification、`slo-document.md` の timestamp fields の
定義に従う時刻、monotonic clock で測定した duration、raw record を保存する。
必須 path が失われる、誤分類される、または識別不能な場合は有効化を停止する。

### Data quality と coverage を確認する

対象の decision に必要な data quality と coverage の判定基準を事前に宣言する。event count、representativeness、scheduled runs の
attempted / completed / missed counts、gap distribution、outcome を判定できない measurement result、measurement timeout による
right-censoring、configuration version と変更時刻、warm-start / cold-start conditions を確認する。
普遍的に適用できる sample size は定められていない。

事前に宣言した基準を満たさない場合は、SLO compliance を評価できない理由を記録し、無理に pass または fail と判定しない。

確認結果は、用途に応じて SLI implementation validation result、baseline report、SLO compliance report、review record のいずれかに記録する。
対象の decision または compliance period、事前に宣言した基準、data quality / coverage の確認結果、gap、outcome を判定できない
measurement result、measurement timeout による right-censoring、configuration version と変更時刻、参照した data への link を含める。
最初の `Published` SLO には、SLI implementation validation と baseline の両方が事前の基準を満たすことが必要である。
その後も、data quality または coverage が基準を満たさない compliance period については、SLO compliance と error budget を報告せず、
SLO compliance または error budget の計算結果を trigger とする [error-budget-policy.md](./error-budget-policy.md) の対応を開始しない。
この停止条件は、実際の user impact、security、data integrity、recoverability に対する incident response、または
error budget と独立した postmortem trigger には適用しない。

## 測定と評価

1. `slo-document.md` と `error-budget-policy.md` の Status がともに `Published` で、両文書に Approval Date と Revisit Date があり、
   同じ承認作業の review record を参照していることを確認する。満たさなければ compliance と error budget を評価しない
2. `slo-document.md` から `attempt_started_at` の時点で有効な SLO Version、service scope、SLI implementation、
   2 つの latency threshold、SLO target、compliance period、policy link を確認する
3. commit SHA、deployment revision、image digest、configuration version、client version、measurement tool version、
   dependency provider / deployment / model を記録する
4. 承認済みの raw event source が、今回評価する compliance period 全体を coverage していること、および期間内に schema や
   SLI implementation が変わっていないことを確認する
5. `slo-document.md` に記録された、承認済みで version 管理された query または tool を実行する。
   現在は synthetic transaction が未実装なのでここで停止する。synthetic transaction SLI の実装がマージされ、
   `slo-document.md` に schema / tool / version が記録された時点で解除する
6. raw measurement data、または再現可能で変更されない参照を保存する
7. eligible、good、bad の各 event、total events から除外した event、outcome を判定できない measurement result を数え、除外と判定不能の理由を説明する
8. event count から good event の割合を計算し、宣言した compliance period の SLO target と比較する
9. 許容される bad event と `remaining error budget` を request 単位で計算する
10. 採用済みの implementation と decision rule が policy に記録されている場合にのみ、burn rate を計算する
11. SLO compliance を示す前に、data quality と coverage が事前の基準を満たすか確認する
12. 結果を記録する。measurement が有効で `remaining error budget < 0` の場合だけ policy の発動判定へ進む

既存の collector（`scripts/collect-probe-records.sh`）は workflow が収集した過去の `/readyz` probe records を保存できるが、
supporting evidence のままである。
出力を primary `/chat` SLI として使用せず、欠落した scheduled run が成功したと推定しない。

## 定期的な review と改善

SLO と error budget policy がともに `Published` になった後、次の順序で実施する。いずれかが `Draft` の間は
「measurement を検証する」までで停止する。

| 手順 | 確認または実行 | 記録 | 停止条件 | 正本の更新先 |
| --- | --- | --- | --- | --- |
| current SLO と policy を読む | `attempt_started_at` の時点で有効な SLO Version、scope、SLI implementation、target、compliance period、両文書の Status と Approval Date | SLO Version、effective date、policy revision | 両文書が `Published` でない、または内部的に一貫した SLO と policy がない | `slo-document.md`、`error-budget-policy.md` |
| measurement を検証する | schema、source coverage、query または tool、gap、timeout、commit SHA、deployment revision、image digest | validation result と limitation | eligibility、outcome、coverage を確認できない | `slo-document.md` の SLI implementation、`docs/verification/` の raw measurement data |
| SLI を測定する | 承認済みの raw event source と version 管理された query または tool | count、query / tool version、period、data location | measurement が承認済みの implementation と異なる | measurement report |
| SLO compliance と error budget を評価する | SLI result、target、compliance period、bad event count | 過去に遡って reclassification していない結果、`remaining error budget` | data quality または coverage が不足している | SLO compliance report と関連する Issue |
| 必要な場合に burn rate を評価する | 採用済みの formula、alerting window、threshold、no-data behavior | input、result、alert behavior | burn rate の使用が採用されていない、または data が無効 | policy または alerting rule |
| engineering の対応を決定する | 有効な measurement、user impact、`remaining error budget`、原因、提案する作業の production への潜在的影響 | policy の順序に従った change freeze の発動・非発動・解除・例外と根拠 | evidence が矛盾する、または原因と変更の影響を判定できない | change freeze の実現方式で選定した記録先 |
| 調査する | 下記「調査順序」 | timeline、observation、否定した原因、data への link | user、security、data への即時 risk を先に封じ込める必要がある | incident、postmortem、review record |
| hypothesis を立て controlled change を行い再測定する | 下記「hypothesis と controlled change」 | hypothesis、commit SHA、deployment revision、image digest、configuration version、before / after の data | 安全性、rollback、attribution が不十分 | code、Terraform、ADR、Issue または PR |
| SLI、SLO、policy を review する | Table 2-5 の decision matrix と Workbook が示す 4 つの選択肢 | 維持または将来に向けた revision の decision | SLO miss だけが target を緩める根拠になっている | 該当する SLO document、policy、runbook |

review の判断は Workbook Table 2-5 の三軸（SLO の達成状況、toil、customer satisfaction）を使う。

| SLO | Toil | Customer satisfaction | 本 project で検討する対応 |
| --- | --- | --- | --- |
| 達成 | 低い | 高い | release / deployment の手順を見直して変更速度を上げる、または他の reliability 課題へ時間を振り向ける |
| 達成 | 低い | 低い | SLO target を締める |
| 達成 | 高い | 高い | false positive を減らす。必要なら一時的に SLO を緩めるか toil を減らし、product または自動 mitigation を改善する |
| 達成 | 高い | 低い | SLO target を締める |
| 未達 | 低い | 高い | SLO target を緩める |
| 未達 | 低い | 低い | alerting の感度を上げる |
| 未達 | 高い | 高い | SLO target を緩める |
| 未達 | 高い | 低い | toil を減らし、product または自動 mitigation を改善する |

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)（Table 2-5）。

本 project では customer satisfaction は project owner 自身の判断であり、その事実を review record に書く。
「SLO miss だけを理由に緩めない」は維持するが、SLO 未達・toil が低い・customer satisfaction が高い場合に
緩める経路を Table 2-5 は示している。
一時的な緩和に期限と恒久修正の計画を付ける形も、SLO revision の一形態として認める。

一時的に target を緩める場合も、baseline、期限、恒久修正の計画を record に残す。

根拠: [SRE Book Ch.6「Monitoring Distributed Systems」](https://sre.google/sre-book/monitoring-distributed-systems/)。

review で coverage の不足が見つかった場合は、slo-document.md「原則 6」で Workbook が示す 4 つの選択肢（SLO target の変更 /
SLI implementation の変更 / aspirational SLO の設定 / 反復改善）から対応を選ぶ。最初の数回は低コストで早く検証できる改善を優先する。

## 調査順序

調査開始時に SLO target を変更しない。

### Measurement の妥当性

最初に次を確認する。

- collection または query の defect、event の重複または欠落、schema drift
- intended user と eligible event の classification
- client、ingress、application の measurement point における gap
- measurement timeout、right-censoring
- scheduled runs の attempted / completed / missed counts、欠落した measurement result、ingestion delay、clock behavior
- warm-start / cold-start condition、configuration version と変更時刻、deployment revision、image digest
- query、tool、SLI implementation の version
- synthetic transaction 自体の failure（scheduler、authentication credential の期限切れ、測定側の network）と service の failure の区別

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

- Azure Container Apps の revision、replica、ingress、startup probe、liveness probe、readiness probe、scaling、system logs
- CPU、memory、replica count、restart、saturation の evidence
- PostgreSQL private access の VNet、delegated subnet、private DNS zone
- Azure service と dependency の limit
- diagnostic settings、log ingestion、metric coverage

`minReplicas` は構成上の target であり、replica availability を保証しない。

Terraform には probe の定義がない。Azure Container Apps は ingress が有効な container app の main app container に、probe 種別ごとの定義が
無ければ default の **TCP probe**（startup / readiness / liveness。port は ingress の target port）を自動付与する。したがって現在の runtime
には TCP の default probe があり、HTTP probe は定義されていない。`az containerapp show --query 'properties.template.containers[0].probes'`
の出力で確認し、default による付与か明示定義かを evidence に記す。

TCP probe は TCP connection が確立できることだけを確認し、application の `/readyz` も critical user journey も観測しない。
application の `/readyz` endpoint と、それを呼び出す GitHub Actions workflow は Azure Container Apps の `readiness probe` ではなく、
この SLI の implementation でもない（NO_SLO）。

### SLO の妥当性

measurement、application、platform を確認した後に限り、次を review する。

- SLI が引き続き critical user journey を表しているか
- target が引き続き user / product / business requirement を表しているか
- reliability とコストの trade-off に根拠があるか
- risk tolerance、architecture、dependency、service scope が変わったか
- incident または user impact が error budget の消費に反映されていないか
- current performance や、dependency の障害が独立していると仮定して公称 SLA を乗算した値を SLO target の上限と誤認していないか。
  SLO 未達の原因に実在する dependency constraint がある場合は、その evidence と対策を記録しているか

## hypothesis と controlled change

次の流れを Issue または measurement plan に記録する。

```text
observation
-> falsifiable hypothesis
-> measurable success criterion
-> controlled change and rollback
-> record deployment revision, image digest, configuration version, and change time
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
- 2 つの latency threshold、measurement timeout
- warm-start / cold-start condition、`min_replicas`、`max_replicas`、CPU、memory
- commit SHA、deployment revision、image digest、measurement tool version
- dependency provider、state、limit、configuration、retry behavior
- measurement point、event time、clock source、schema、query、aggregation、collection coverage、ingestion behavior

関連する条件に差がある場合は、予想される影響を説明する。その影響を分離できなければ、結果は直接比較できないと明記する。
異なる SLI implementation または configuration version の time series を統合しない。

## evidence の記録

既存の `docs/verification/<campaign>/observations.md` の形式と、利用可能な場合は machine-readable な raw record を使用する。
postmortem も同じ形式で記録する。SLO 作業だけのために別の記録体系を追加しない。

measurement または review の record には、該当する次の情報を含める。

- 目的、critical user journey、hypothesis、測定可能な success criterion
- UTC の半開区間 `[window_start, window_end)` と、期間帰属に使用した `attempt_started_at`
- SLO version、SLI implementation version、query または tool version
- timestamp fields の定義に従う `scheduled_for`、`attempt_started_at`、`completed_at`、`ingested_at`、clock source、commit SHA、
  deployment revision、container image または digest、region
- current `min_replicas`、`max_replicas`、CPU、memory、関連する platform configuration（observed configuration であることを明示する）
- measurement source、location、command または tool、schema、raw evidence の path
- payload class、authentication method、event count、concurrency、request interval、2 つの latency threshold、measurement timeout
- eligible、good、bad の各 event、total events から除外した event、outcome を判定できない measurement result の count、
  除外と判定不能の理由
- SLI result、measurement が有効な場合の SLO compliance、採用済みの場合に限る error budget と burn rate
- scheduled runs の attempted / completed / missed counts、欠落した measurement result、ingestion delay、measurement timeout による
  right-censoring、configuration version と変更時刻、その他の limitation
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
4. Workbook が示す 4 つの選択肢のどれを選ぶかを、投資対効果で決める
5. error budget policy、alert、query、historical comparability への影響を review する
6. 変更の種類に応じて version を更新する
   - SLI specification、current SLO target、compliance period のいずれかを変更する場合は、新しい SLO Version を割り当てる
   - schema、query、tool、measurement configuration のいずれかを変更する場合は、新しい SLI implementation version を記録する
   - 両方を変更する場合は両方の version を更新する
7. old value、new value、理由、supporting evidence、decision date、Approval Date、effective date を記録し、
   ヘッダ表（Date / Approval Date / Revisit Date / Status）を更新する
8. error budget policy が新しい SLO Version と整合するか review し、必要な policy revision を将来に向けて有効にする
9. revision は effective date 以後の event にだけ適用し、`attempt_started_at` で適用する SLO Version を決める。以前の SLO history を保持する
10. revision 後の SLI implementation を検証してから SLO compliance の評価に使用する

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
- warm-start / cold-start conditions、または比較可能性に影響する他の条件が変わった
- user / product / business / reliability / security / compliance requirement が変わった
- error budget policy に定めた対応が繰り返し影響に比例しない、または実行できない
- burn rate alert を採用し、noise が多い、incident を見逃す、または対応に必要な event volume がない
- aspirational SLO を current SLO に昇格する条件（current SLO の運用実績と client-side instrumentation の有無）が揃った

page を発生させなかった incident ほど monitoring の gap を示すという趣旨と、その引用は
[error-budget-policy.md](./error-budget-policy.md) の §outage 時の対応 を正本とする。

## 参考資料

### 方法論の primary source

- [the Google SRE books（公式書籍一覧）](https://sre.google/books/)
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

### 時刻と event time の仕様

- [RFC 3339: Date and Time on the Internet: Timestamps](https://www.rfc-editor.org/rfc/rfc3339)
- [W3C High Resolution Time](https://www.w3.org/TR/hr-time-3/)
- [Apache Flink: Event Time](https://nightlies.apache.org/flink/flink-docs-stable/docs/concepts/time/)

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
