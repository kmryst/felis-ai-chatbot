# SLI / SLO review runbook

## 目的

この runbook は、`felis-ai-chatbot` の user-facing SLI / SLO を確立、測定、評価、
調査、改善、revision するための運用手順を定める。

[slo-document.md](./slo-document.md) は service scope、SLI、SLO、measurement semantics の
正本である。[error-budget-policy.md](./error-budget-policy.md) は、有効な SLO と
error budget を engineering decision にどう適用するかを定める。規範的な定義を evidence
record へ複製せず、正本を更新する。

この runbook では新しい定量値を選択しない。定量値を後日決定し、review する手順だけを
定める。

## 現在の前提

repository には定性的な SLI specification があるが、effective な SLO target、
SLI threshold、compliance period、承認済みの SLI implementation、error budget はない。
したがって、次のとおり扱う。

- 下記の初回確立手順を使用する。
- 現在の SLO compliance や残りの error budget を報告しない。
- `/readyz` の結果を primary `/chat` SLI として使用しない。
- current configuration や historical result から将来の値を推定しない。
- recurring review で前提が欠けている場合はそこで停止し、必要な evidence を記録する。

<a id="initial-sli-and-slo-establishment"></a>

## 初回の SLI / SLO 確立

出力が既に存在し、その evidence が現在も有効な場合を除き、次の手順を順番に実施する。
evidence が不足したまま値を作らないよう、各手順に明示的な停止条件を設ける。

| 手順 | 入力 | 実施内容 | 出力 | 必要な evidence | 完了条件または停止条件 |
| --- | --- | --- | --- | --- | --- |
| user を特定する | repository の目的、supported client、deployment scope | service に依存する user を特定し、service user と repository の読者を区別する | 文書化された user population | client と deployment の文書、user または stakeholder の記録 | intended user と supported client を区別できなければ停止する |
| critical user journey を特定する | user population と product behavior | client からの送信から client-visible outcome までを追跡する | 代表的な critical user journey | frontend / backend の code path、dependency と authentication の挙動 | user journey または完了条件が曖昧なら停止する |
| service の成功条件を定義する | critical user journey | telemetry とは独立して user-visible result を記述する | SLI specification の候補 | response contract、意図した no-context response、既知の failure mode | 測定不能または未定義の product requirement に成功条件が依存するなら停止する |
| primary SLI を選択する | user outcome の候補と利用可能な signal | user journey を表す最小限の user-facing indicator を選び、health signal と resource signal は diagnostic metric として扱う | primary SLI specification と根拠 | user impact との対応、signal の limitation | 測定しやすいという理由だけで、利用可能な signal が user journey を再定義してしまうなら停止する |
| eligible / good / bad / excluded event と unclassifiable record を定義する | primary SLI specification と service scope | intended user の識別や application 到達前の failure を含め、再現可能な event rule を記述する | event classification rule | request contract、authentication semantics、client behavior、incident の例 | telemetry の欠落や対象外 traffic が暗黙に good または exclusion になるなら停止する |
| SLI implementation を定義する | SLI specification と measurement point の候補 | client instrumentation、synthetic transaction、ingress log、application telemetry を coverage、bias、reliability、安全性、コストで比較する | measurement point、schema、query または tool、limitation の案 | prototype record と field 単位の coverage | event rule を再現できなければ停止する |
| 独立した requirement を特定する | user、critical user journey、failure impact | user expectation、business / product requirement、risk tolerance、dependency constraint、cost constraint、既存の SLA があれば収集する | requirement の記録 | 出典、owner、日付、scope、failure の影響 | 説明可能な requirement があれば requirement に基づく案へ進み、なければ baseline を収集する |
| 必要に応じて baseline 測定を計画する | 有効な SLI implementation 候補と明示した条件 | 測定期間を compliance period とみなさず、measurement campaign、比較条件、integrity check、evidence の保存先を定義する | 承認済みの baseline 計画 | measurement hypothesis、configuration identity、data quality check、rollback または安全対策 | SLI implementation が有効でない場合、または campaign に安全でないコストや mutation が伴う場合は停止する |
| 必要に応じて baseline evidence を収集する | 承認済みの baseline 計画 | 選択した implementation を実行し、raw event、execution coverage、gap、configuration boundary を保存する | 再現可能な baseline evidence | raw record、command または tool version、timestamp、revision、image、configuration、limitation | eligible event または measurement coverage を確認できなければ、値を提案せず停止する |
| SLI threshold を提案する | requirement または baseline evidence | 候補の境界を user expectation、client behavior、dependency behavior、censoring、コストに関連付け、trade-off を比較する | 根拠を伴う SLI threshold の案 | 候補の評価結果と user impact に基づく説明 | current timeout、観測 percentile、扱いやすい端数だけが根拠なら停止する |
| SLO target を提案する | requirement と検証済みの SLI evidence | requirement があればそれに基づき、なければ baseline evidence を starter SLO の入力としてのみ使用して、その根拠を明記する | 根拠を伴う SLO target の案 | failure の影響、risk tolerance、実現可能性、コスト、dependency constraint、user または stakeholder の review | 独立した根拠なしに current performance を required performance と読み替えている場合は停止する |
| compliance period を提案する | decision の用途と event の挙動 | user impact の現れ方、event volume、seasonality、decision cadence、operational response で候補を比較する | 根拠を伴う compliance period の案 | historical replay または baseline analysis、decision の用途 | validation campaign、product default、vendor example だけが根拠なら停止する |
| 測定と評価の設定を決定する | SLO と SLI implementation の案 | 次節の手順を用い、measurement frequency、各 timeout、evidence が十分か判断する基準、synthetic transaction の設定を決定する | implementation configuration と根拠 | 候補の試行、gap analysis、censoring analysis、コスト、安全性、operational response の evidence | 設定によって SLI の意味が変わる場合、または報告されない censoring が生じる場合は停止する |
| error budget と policy の適用方法を定義する | SLO と compliance period の案 | SLO から request-based error budget を導出し、policy の action が影響に比例し実行可能であることを確認する | error budget の計算と適用する policy | event 単位の計算、owner の review、scenario walkthrough | error budget を downtime に変換している場合、またはこの project で action を実行できない場合は停止する |
| 測定全体を検証する | `slo-document.md` と SLI implementation の案 | good / bad / excluded event、unclassifiable record、application 到達前の failure、timeout、不正な response、telemetry loss、configuration boundary の各 case を test する | validation evidence と既知の limitation | raw test record、期待する classification と実際の classification、query または tool の identity | 必須 case が誤分類されるか、暗黙に失われる場合は停止する |
| SLO を承認して記録する | 完成した案と validation evidence | owner、reviewer、decision date、effective date、version、根拠、SLI implementation、policy link を記録する | 将来に向けて effective になる SLO | review record と関連 evidence | 定量項目に decision rationale がなければ停止し、過去へ遡って適用しない |
| 測定を開始する | effective な SLO と検証済みの SLI implementation | 承認済みの収集を開始し、raw evidence の到着を確認して最初の evidence record を作成する | 収集開始を確認した evidence | 最初の record、収集状態、deployment / configuration identity | 収集または classification が承認済みの implementation と一致しなければ compliance の報告を停止する |

## 将来の定量値を決定する手順

一般的な方法を説明する際は Google SRE Book と The Site Reliability Workbook の
terminology を使用する。Azure の implementation と product behavior には Microsoft の
terminology を使用する。Google Cloud と AWS の product behavior は cross-check に利用できるが、
project の default として自動的に採用しない。

次の各項目は、記載した evidence が揃うまで値を選択せず、候補を比較する。最終的な decision の
説明に必要な場合は、却下した候補と trade-off も記録する。

| 決定項目 | 意味と適用する official guidance | project requirement と必要な evidence | measurement と trade-off | decision、記録、後日の review 手順 |
| --- | --- | --- | --- | --- |
| SLI threshold | good event rule に含める client-visible elapsed time の条件。Google SRE は SLI を user experience と結び付けるよう説明しており、measurement timeout とは区別する。 | supported client に対する期待、遅延の影響、response contract、dependency behavior、user impact の evidence | censoring のない client-visible distribution に候補の境界を適用し、誤って good または bad と分類する outcome、コスト、dependency constraint を調べる | 候補を比較し、根拠を文書化して将来に向けて承認し、`slo-document.md` に記録する。user journey、client、dependency、distribution の変更後に review する |
| SLO target | eligible event のうち good event であることを求める割合。Google SRE は current performance を機械的に採用しないよう説明しており、他の evidence がない場合は starter SLO の入力として current performance を利用できるとしている。 | user / product / business requirement、failure impact、risk tolerance、コスト、実現可能性、dependency constraint | requirement に基づく候補と baseline を参考にした候補を比較し、engineering decision に役立つか、例外的な作業を繰り返さず説明可能かを評価する | 採用した target、根拠、owner、review、effective date を `slo-document.md` に記録する。revision 手順を用い、将来に向けてのみ revision する |
| Compliance period | SLO compliance と error budget を評価する期間。baseline campaign、validation period、alert look-back window とは異なる。 | 必要な decision cadence、user impact の現れ方、event volume、seasonality、operational response model | 候補期間へ historical data を適用し、変動、把握の遅れ、適時の decision に役立つかを調べる | 採用した期間と根拠を `slo-document.md` に記録する。利用状況、risk、seasonality、decision cadence の変更時に review する |
| Evaluation period または alert look-back window | 特定の評価または alert が使用する data interval。compliance period と同じ期間を指すかは product と用途によって異なるため一般化しない。 | 目的とする decision または alert、effective な SLO、event volume、検出要件、response capability | incident、incident でない期間、no-data interval、ingestion delay に候補を適用し、precision、recall、detection time、reset time を比較する | query または alert configuration とともに記録し、policy から参照する。noise、見逃した impact、data volume の変更時に review する |
| Measurement frequency、probe frequency、synthetic transaction frequency | 測定を試行する頻度。設定された schedule と実際の coverage は同じではない。 | 観測が必要な user impact の継続時間、event の有無、scheduler reliability、コスト、安全性、operational response | 候補を試行し、synthetic transaction を user と同一視せず、実際の execution、gap、重複または cancel された run、ingestion delay、コストを測定する | 選択した configuration と実際の coverage を分けて `slo-document.md` と evidence に記録する。gap、scheduler、traffic、response 要件の変更後に review する |
| Measurement timeout | measurement tool が client-visible result を待つのを終了する時点。censoring を決める設定であり、SLI threshold ではない。 | supported client の挙動、SLI threshold、dependency behavior、コスト、未完了 request の classification | timeout の候補を試行し、transport error と timing field を保持して、どの outcome が right-censored になるかを確認する | SLI implementation と `slo-document.md` に記録する。SLI threshold、client、tool、dependency の変更時に review する |
| Client timeout | supported client が response を待つのを終了する時点。 | user expectation、interaction design、cancellation / retry behavior、SLI との整合性 | 候補設定付近の client-visible outcome を確認し、resource use と retry amplification を調べる | client configuration と `slo-document.md` に記録する。supported client または interaction の変更時に review する |
| Request timeout | server、ingress、dependency request を終了する時点。layer ごとに異なる正式な product setting を使用する場合がある。 | dependency limit、resource protection、retry behavior、end-to-end outcome、rollback safety | timeout と retry の組み合わせ、未完了の処理、resource occupancy、client-visible classification を test する | 実装する各 layer に記録し、`slo-document.md` から参照する。architecture、dependency、retry の変更時に review する |
| Retry count と retry timing | retry 可能な failure を再試行する回数と間隔。application または product の setting であり、SLO target ではない。 | operation の安全性と idempotency、dependency guidance と limit、user-visible timeout、failure duration、コスト、load amplification | 分類済みの failure を発生させ、attempt、elapsed time、duplicate effect、rate limiting、saturation、最終的な client-visible outcome を測定する | application または platform configuration に記録し、SLI に影響する場合は参照を追加する。dependency、timeout、failure、load の変更時に review する |
| campaign の sample size または request count | 対象の評価に使用する eligible observation の数。確認した official source には、この project に適用できる普遍的な最小値はない。 | campaign が支える decision、想定 variance、traffic model、failure mode、evidence が十分かを判断する方法 | analysis method を事前に宣言し、不確実性、representativeness、missingness、event を追加するコストと安全性を調べる | 選択した count と根拠を SLO target ではなく campaign plan に記録する。decision、variance、traffic model の変更時に review する |
| Concurrency と request interval | synthetic measurement または performance measurement の offered load 条件。それ自体は reliability target ではない。 | 想定する user または load model、dependency limit、data mutation、コスト、isolation、production-like な条件との対応 | payload、environment、tool を同一に保って候補を比較し、saturation、queueing、retry amplification、相互干渉を調べる | campaign plan と evidence に記録する。workload または capacity の変更時に review し、条件が異なる結果を暗黙に混在させない |
| Alert threshold と burn rate threshold | response を開始する条件。The Site Reliability Workbook は multiwindow, multi-burn-rate alert を説明しているが、example value や vendor default は普遍的な rule ではない。 | effective な SLO、有効な event stream、対応可能な user impact、event volume、incident の例、response の owner | incident、通常期間、zero-event period、telemetry loss に候補を適用し、precision、recall、detection time、reset time、operational load を比較する | 採用した値を、根拠と effective date とともに alert source と policy に記録する。alert、見逃し、noise、event volume の変更を review する |
| CPU、memory、replica、scaling、その他の capacity value | platform configuration または diagnostic threshold。implementation には Azure Container Apps の terminology と limit を適用する。default では user-facing SLO ではない。 | load model、response requirement、dependency behavior、cost boundary、platform limit、failure / recovery behavior | 管理された production-like test と Azure metrics を使用し、明示した configuration ごとに user-facing SLI と diagnostic behavior を比較する | infrastructure decision は Terraform に記録し、architectural decision なら ADR にも記録する。観測した configuration は evidence に記録し、workload、platform、dependency、コストの変更後に review する |
| RTO または RPO | workload の復旧と data loss についてそれぞれ定める recovery objective。この request-based error budget から導出しない。 | business impact、data criticality、restore / failover capability、compliance requirement、既存の recovery documentation | 該当する recovery drill を実施し、timestamp、recovery point、failure path、limitation を保存する | recovery objective を決定する既存の手順で決定、記録する。この SLO に値を複製せず参照を追加し、recovery evidence、architecture、requirement の変更後に review する |
| Review frequency | SLO、policy、evidence を review する頻度。measurement frequency や compliance period とは異なる。 | decision cadence、change rate、incident pattern、data availability、maintenance burden | cadence を試行し、review が適時で evidence に基づき、actionable かを評価する | 選択後にのみこの runbook へ記録する。下記の trigger に該当する場合は cadence を待たず review する |

## SLI implementation の検証

### repository と runtime の identity を記録する

repository root で実行する。次の command は読み取り専用で current fact を表示するものであり、
将来の target ではない。

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

resource name が変わった場合は、command の実行前に Terraform と Azure resource inventory から
resolve する。environment variable を抽出する query は、測定の解釈に必要な
non-secret configuration だけを表示する。
resource を推測せず、`DATABASE_URL`、`CHAT_API_KEY` などの secret value を出力しない。
現在 checkout している commit と deployment された container image は一致するとは限らない。
両方の identity を記録し、runtime behavior は build provenance または deployment された
source version で確認する。checkout の code だけから runtime の既定値を推定しない。

### classification の coverage を検証する

有効化の前と SLI implementation の変更後に、管理された test event を使用して次の path を
すべて検証する。

- intended user からの有効な request に対する通常の reply
- intended user からの有効な request に対する、意図した no-context response
- supported client での parsing または rendering の failure
- intended interaction に対する誤った authentication または authentication の欠落
- request が FastAPI に到達する前の failure
- application、database、LLM または provider の failure
- SLI threshold の案より遅い response
- client timeout と measurement timeout
- 不正または欠落した telemetry
- exclusion とする user 以外の traffic、または事前に宣言した test traffic
- collection の中断と再開
- deployment または measurement version の boundary

各 path について、期待する eligibility と outcome、観測した field、実際の classification、
timestamp、raw record を保存する。必須 path が失われる、誤分類される、または識別不能な場合は
有効化を停止する。

### evidence が十分かを確認する

対象の decision に必要な evidence が十分かを判断する方法を、事前に宣言する。event count、
representativeness、execution coverage、gap distribution、unclassifiable record、timeout censoring、
configuration change、warm / cold semantics を確認する。現時点で、official source にもこの
repository にも、普遍的に適用できる sample size は定められていない。

事前に宣言した基準を満たさない場合は、次のとおり記録する。

> この SLO を信頼できる形で評価するための evidence が不足している。

無理に pass または fail と判定しない。不足する evidence と、別の measurement campaign または
implementation の修正が必要かを記録する。

## 測定と評価

1. `slo-document.md` から effective な SLO version、service scope、SLI implementation、
   SLI threshold、SLO target、compliance period、policy link を確認する。
2. repository、deployment、configuration、client、measurement tool、dependency の identity を
   記録する。
3. 承認済みの raw event source が、今回評価する compliance period 全体を coverage していること、
   および期間内に schema や measurement semantics が変わっていないことを確認する。
4. `slo-document.md` に記録された、承認済みで version 管理された query または tool を実行する。
   現在の repository には primary `/chat` SLI の query がないため、実装と検証が完了するまで
   ここで停止する。
5. raw evidence、または再現可能で変更されない参照を保存する。
6. eligible、good、bad、excluded event と unclassifiable record を数え、exclusion と
   unclassifiable record を説明する。
7. event count から good event の割合を計算し、宣言した compliance period の effective な
   SLO target と比較する。
8. 許容される bad event と残りの error budget を request 単位で計算する。
9. 採用済みの implementation と decision rule が policy に記録されている場合にのみ、burn rate を
   計算する。
10. SLO compliance を示す前に、evidence が十分かを確認する。
11. 結果を記録し、measurement が有効な場合にのみ policy の action と調査へ進む。

既存の collector は、指定した半開区間に含まれる過去の `/readyz` workflow record を保存できる。
ただし、これは supporting evidence のままである。

```bash
scripts/collect-probe-records.sh --help
```

この record を収集する場合は、承認済みの正確な start / end timestamp を使用し、既存の
`docs/verification/` の campaign pattern に保存する。出力を primary `/chat` SLI として使用せず、
欠落した scheduled run が成功したと推定しない。

## 定期的な review と改善

SLO が effective になった後、次の順序で実施する。この順序は Google SRE の guidance を運用へ
適用したものであり、新しい正式な methodology name は付けない。

| 手順 | 確認または実行 | 計算または評価 | 記録 | 停止条件 | 正本の更新先 |
| --- | --- | --- | --- | --- | --- |
| current SLO を読む | effective version、scope、SLI implementation、target、compliance period、policy | review が現在の prospective decision に基づいているか | version と effective boundary | effective で内部的に一貫した SLO がない | 修正が承認された場合は `slo-document.md` |
| measurement を検証する | schema、source coverage、query または tool、gap、timeout、deployment boundary | event classification と evidence が有効か | validation result と limitation | eligibility、outcome、coverage を確認できない | `slo-document.md` の SLI implementation、`docs/verification/` 配下の raw evidence |
| SLI を測定する | 承認済みの raw event source と version 管理された query または tool | eligible、good、bad、excluded event と unclassifiable record の count、good event の割合 | count、query identity、period、evidence location | measurement が承認済みの implementation と異なる | evidence record |
| SLO compliance を評価する | SLI result、target、compliance period | 有効な測定結果が effective target を満たすか | 過去に遡って reclassification していない結果 | evidence が不足している | evidence record |
| error budget を評価する | eligible / bad event の count、effective target | 許容される bad event と残りの error budget（request 単位） | calculation input と result | SLO または event count が無効 | evidence record と、関連する Issue または PR |
| 必要な場合に burn rate を評価する | 採用済みの formula、look-back window、threshold、no-data behavior | 採用済みの alert condition を満たすか | input、result、alert behavior | burn rate の使用が採用されていない、または data が無効 | revision する場合に限り policy または alert source |
| engineering action を決定する | 有効な measurement、user impact、残りの error budget、提案する作業の risk | policy の比例した条件を適用する | 許可、延期、rollback、mitigation の decision と根拠 | evidence が矛盾する、または decision authority が不明 | 関連する Issue または PR と evidence record |
| 調査する | 下記の順序による measurement、application、platform、requirement の evidence | 最も可能性の高い failure domain と残る不確実性 | timeline、observation、否定した原因、evidence link | user、security、data への即時 risk を先に封じ込める必要がある | incident または evidence record |
| hypothesis を立てる | observation と failure domain の evidence | 反証可能な原因と測定可能な success criterion | hypothesis、予想する signal change、confounder | 提案する変更と failure の間に観測可能な関係がない | Issue または measurement plan |
| controlled change を行う | hypothesis、scope、risk、安全性、rollback | attribution が明確になるよう変更を切り分けられるか。技術上または安全上分離できない場合は変更を組み合わせる | change identity、approval、deployment boundary、rollback | 安全性、rollback、attribution が不十分 | code、Terraform、architectural decision なら ADR、Issue または PR |
| 再測定する | 同じ SLI specification と比較可能な条件 | before / after の差と不確実性 | 両方の evidence set と条件の差 | 関連する条件差により直接比較できない | evidence record |
| hypothesis を採用または却下する | before / after evidence | 許容できない regression を生じさせず、予測した変化が起きたか | decision、limitation、次の action | measurement が引き続き無効 | evidence record と関連する Issue |
| SLI、SLO、policy を review する | user impact、incident、false positive、false negative、コスト、risk、運用上の有用性 | specification、implementation、target、period、policy が引き続き必要性を表すか | 維持または将来に向けた revision の decision | SLO miss だけが target を緩める根拠になっている | 該当する SLO document、policy、runbook |

## 調査順序

調査開始時に SLO target を変更しない。

### Measurement の妥当性

最初に次を確認する。

- collection または query の defect、event の重複または欠落、schema drift
- intended user と eligible event の classification
- client、ingress、application の measurement point における gap
- measurement timeout、client timeout、right-censoring
- scheduler execution、collection gap、ingestion delay、clock behavior
- warm / cold condition、configuration または revision の boundary
- query、tool、SLI implementation の version

measurement が無効な場合は、影響した期間を保存し、結果を application に帰属させる前に
measurement を修正する。

### Application の確認

次を確認する。

- request validation、authentication、processing、response serialization
- embedding、RAG retrieval、no-context handling、provider response
- database query、connection handling、blocking I/O
- dependency の latency、error、limit、retry、cancellation、timeout behavior
- concurrency と resource occupancy
- client の parsing、rendering、cancellation、retry behavior

### Platform の確認

Microsoft Azure の terminology と current configuration に基づき、次を確認する。

- Azure Container Apps の revision、replica、ingress、startup probe、liveness probe、
  readiness probe、scaling、platform event
- CPU、memory、replica count、restart、saturation の evidence
- network と private database path
- Azure service と dependency の limit
- diagnostic setting、log ingestion、metric coverage

`minReplicas` は構成上の target であり、replica availability を保証しない。Azure Container Apps の
readiness probe は、replica が request を処理できる準備状態を示す signal であり、
critical user journey の成功を証明するものではない。

現在の Terraform と Azure runtime には明示的な HTTP probe がない。application の `/readyz`
endpoint と、それを呼び出す GitHub Actions workflow を、Azure Container Apps の
`readiness probe` とみなさない。

### SLO の妥当性

measurement、application、platform を確認した後に限り、次を review する。

- SLI が引き続き critical user journey を表しているか
- target が引き続き user / product / business requirement を表しているか
- reliability とコストの trade-off に根拠があるか
- risk tolerance、architecture、dependency、service scope が変わったか
- incident または user impact が error budget の消費に反映されていないか
- current performance を limit と誤認しているのではなく、実在する dependency constraint のためにのみ
  SLO を達成できないのか

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

attribution が明確になる場合は、変更を切り分ける。技術的に分離できない変更や、分離によって
安全性が低下する変更は分けない。measurement 自体の検証が目的である場合を除き、effective な
SLO、query、service implementation を同じ比較の中で変更しない。変更する場合は series boundary を
明示する。

## 比較可能な条件での再測定

結果の意味を変えうる次の条件をすべて記録し、比較する。

- endpoint、critical user journey、payload、authentication、supported client
- region、measurement location、event count、concurrency、request interval
- SLI threshold、measurement timeout、client timeout、request timeout
- warm / cold state、`min_replicas`、`max_replicas`、CPU、memory
- commit、application revision、container image、measurement tool version
- dependency provider、state、limit、configuration、retry behavior
- measurement point、schema、query、aggregation、collection coverage、ingestion behavior

関連する条件に差がある場合は、予想される影響を説明する。その影響を分離できなければ、結果は
直接比較できないと明記する。boundary を隠すために、互換性のない series を統合しない。

## evidence の記録

既存の `docs/verification/<campaign>/observations.md` pattern と、利用可能な場合は machine-readable な
raw record を使用する。SLO 作業だけのために新しい evidence framework を追加しない。

measurement または review の record には、該当する次の情報を含める。

- 目的、critical user journey、hypothesis、測定可能な success criterion
- period boundary と timezone
- SLO version、SLI implementation version、query または tool version
- timestamp、commit SHA、deployment revision、container image または digest、region
- current `min_replicas`、`max_replicas`、CPU、memory、関連する platform configuration。
  target ではなく observed configuration であることを明示する
- measurement source、location、command または tool、schema、raw evidence の path
- payload class、authentication method、event count、concurrency、request interval、
  SLI threshold、該当する各 timeout
- eligible、good、bad、excluded event と unclassifiable record の count、exclusion の根拠
- SLI result、measurement が有効な場合の SLO compliance、適用可能で採用済みの場合に限る
  error budget と burn rate
- execution coverage、collection gap、ingestion delay、censoring、configuration boundary、
  その他の limitation
- before / after condition、comparison result、採用または却下した hypothesis
- resulting engineering decision と関連する Issue、PR、incident、ADR

historical measurement は当時の定義のまま保存する。後の SLI / SLO に合わせて evidence を
書き換えず、factual error は明示的な correction として追記する。

## SLO revision

SLO violation だけを理由に SLO を緩めない。revision には user、product、business、risk、コスト、
architecture、dependency、measurement validity の evidence が必要であり、次の手順に従う。

1. current document と review の契機になった result を保存する。
2. SLO validity より先に measurement validity、application、platform を調査する。
3. 変更された requirement または assumption を記述し、supporting evidence を参照する。
4. 文書化した decision criteria に基づき、existing value と proposed value を比較する。
5. error budget policy、alert、query、historical comparability への影響を review する。
6. old value、new value、根拠、supporting evidence、decision date、effective date、owner、reviewer、
   series boundary を記録する。
7. revision を将来に向けて適用し、以前の SLO history を保持する。
8. revision 後の implementation を検証してから SLO compliance の評価に使用する。

変更が architectural decision であるか、repository の ADR criteria を満たす場合にのみ ADR を使用する。
すべての SLO edit に ADR を要求しない。historical failure を消すために、過去の target や
classification を変更しない。

## review の契機

Review frequency は未決定であり、上記の手順で選択する。将来決定する cadence とは別に、次のいずれかに
該当した場合は review を開始する。

- user population、supported client、service scope、critical user journey が変わった
- incident または重大な user impact を SLI が表していない
- SLI の変化が繰り返し user impact と対応しない、または measurement から説明できない結果が出る
- measurement point、schema、query、tool、collection system、timeout、event classification が変わった
- architecture、dependency provider、revision behavior、scaling、capacity、cost constraint が変わった
- warm / cold semantics、または他の comparability condition が変わった
- user / product / business / reliability / security / compliance requirement が変わった
- error budget policy の action が繰り返し影響に比例しない、または実行できない
- burn rate alerting を後日採用し、noise が多い、incident を見逃す、または action に必要な
  event volume がない

## 参考資料

### 方法論の primary source

- [Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Embracing Risk](https://sre.google/sre-book/embracing-risk/)
- [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)
- [Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [Monitoring](https://sre.google/workbook/monitoring/)
- [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)

### platform guidance と cross-check

- [Define reliability based on user-experience goals](https://docs.cloud.google.com/architecture/framework/reliability/define-reliability-based-on-user-experience-goals)
- [Architecture strategies for defining reliability targets](https://learn.microsoft.com/en-us/azure/well-architected/reliability/metrics)
- [Architecture strategies for monitoring workload reliability](https://learn.microsoft.com/en-us/azure/well-architected/reliability/monitoring)
- [Architecture strategies for performance testing](https://learn.microsoft.com/en-us/azure/well-architected/performance-efficiency/performance-test)
- [Monitor Azure Container Apps metrics](https://learn.microsoft.com/en-us/azure/container-apps/metrics)
- [Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- [\[O.SI.5\] Set and monitor service level objectives against performance standards](https://docs.aws.amazon.com/wellarchitected/latest/devops-guidance/o.si.5-set-and-monitor-service-level-objectives-against-performance-standards.html)
- [REL06-BP06 Regularly review monitoring scope and metrics](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_monitor_aws_resources_review_monitoring.html)
