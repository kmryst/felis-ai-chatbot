# Error budget policy

この文書は、[slo-document.md](./slo-document.md) の SLO とその error budget を
`felis-ai-chatbot` の engineering decision にどう反映するかを定める。
節構成は The Site Reliability Workbook Appendix B「Example Error Budget Policy」
（Service Overview → Goals → Non-Goals → SLO Miss Policy → Outage Policy → Escalation Policy → Background）に揃える。
見出しは既存の運用文書に合わせて日本語で置き、対応する Workbook の節名を各見出しに併記する。

| 項目 | 値 |
| --- | --- |
| Status | Draft |
| Author | project owner（kmryst） |
| Date | 2026-09-07 |
| Reviewers | project owner |
| Approvers | project owner |
| Approval Date | 未定（Status を Published にする時に記入） |
| Revisit Date | 未定（Approval Date + 6 か月。暫定） |

本 project は個人開発であり、Author / Reviewers / Approvers はすべて project owner が兼ねる（§サービス概要 参照）。
この policy または [slo-document.md](./slo-document.md) の Status が `Draft` の間、action は発動しない。
この policy は、`slo-document.md` の「有効化の条件」を満たす `Published` SLO Version と、runbook で `sufficient` と判定された
compliance period にだけ適用する。

## 位置づけ: 原則からの導出

この policy は [slo-document.md](./slo-document.md) の「原則 5: error budget は objective で reproducible な意思決定のためにある」と
「原則 6: SLO は living document であり、4 つの出口で iterate する」から導く。

error budget は、許容する失敗量を明示し、reliability と feature delivery の優先順位を evidence に基づいて判断するための指標である。

根拠: [SRE Book Ch.3「Embracing Risk」](https://sre.google/sre-book/embracing-risk/)。

この service への帰結は次のとおりである。

| 事実 | 帰結 |
| --- | --- |
| repository の主目的は Backup / Restore / Maintenance の設計・検証で、`POST /chat` と無関係な作業が多い | policy は罰や全面的な変更停止ではない。freeze の対象を critical user journey の code path に限定する |
| critical dependency（Azure OpenAI ほか）の composite 参考値が約 99.74% | dependency 起因の miss で freeze しても本 service 側に打つ手が無い期間が生じる。freeze せず、hard dependency への対策の検討を must にする |
| 実測 0 件、low-traffic | 20% や Table 5-8 は Workbook の starting point として置き、baseline 後に見直す。paging はせず ticket のみ |
| 最初の iteration | この policy も Draft であり、Revisit Date で 4 つの出口とあわせて見直す |

## サービス概要（Service Overview）

`felis-ai-chatbot` は、Easy Auth（Entra ID）で認証した intended user が supported client から `POST /chat` を呼び、
SSE stream（`message` / `notice` / `error` / `done` event）で RAG chatbot の応答を受け取る service である。
service scope、critical user journey、SLI、SLO の正本は [slo-document.md](./slo-document.md) である。

release と Terraform apply の定義は [slo-document.md](./slo-document.md) の §サービス概要 を正本とする。
この policy は backend / frontend の code 変更と Terraform 変更の両方に適用する。

この policy は SLA ではない。独立した SRE team、product team、management approval process が存在することを前提としない。

### 開発者と承認者は同一人物である

本 project は個人開発であり、SLO の author / reviewer / approver、error budget policy の適用者、escalation の決定者、
release を行う開発者は**すべて同一人物（project owner）**である。SLO 側の 3 役の兼務は
[slo-document.md](./slo-document.md) のヘッダ注記を正本とする。この policy に固有の帰結は、
Workbook が求める product / development / production の 3 者合意が 1 人の中で完結することである。

専任 product team がない場合は、開発者が risk tolerance と優先順位を明示的に引き受ける必要がある。

根拠: [SRE Book Ch.3「Embracing Risk」](https://sre.google/sre-book/embracing-risk/)。

したがってこの policy の拘束力は自己拘束に依存する。SLO miss 時に変更を止める権限は project owner 自身にしかない。
それを補うため、policy の発動・解除・例外の判断はすべて Issue に evidence とともに記録し、
Revisit Date まで policy 本文を変更しない。

## 目的（Goals）

根拠: [The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)。

本 project では次のとおりとする。

- intended user を repeated SLO miss から守る
- reliability と feature 開発（Backup / Restore / Maintenance / Monitoring の設計・実装・検証）の balance に、
  裁量ではなく objective な根拠を与える
- error budget が余っている期間には、reliability risk のある変更を能動的に寄せる（§SLO miss 時の対応 参照）

## 対象外（Non-Goals）

policy は SLO miss に対する罰ではなく、evidence が reliability を優先すべきことを示す場合に作業を振り向けるためのものである。

根拠: [The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)。

- この policy は SLO miss に対する罰ではない
- 単一の bad event やすべての SLO miss を理由に、feature 開発を自動的にすべて停止しない
- aspirational SLO の miss はこの policy の action を発動しない。aspirational SLO は測定・追跡のみを行う
- [slo-document.md](./slo-document.md) の §SLO の範囲外 と §SLO の対象外の設定 に置いたもの（diagnostic metric、
  recovery 要件など）を、同じ error budget として扱わない
- この policy は security、cost、backup、data integrity の制御手段の代わりにならない

## SLO miss 時の対応（SLO Miss Policy）

### SLO 内で error budget が残っている場合

release は通常どおり進める。各変更について reliability risk と rollback を引き続き評価する。

budget が十分残っている期間には、reliability risk のある変更（dependency の upgrade、scaling 設定の実験、cold start の再検証など）を
この期間に寄せる。SRE Book と Workbook は余剰 budget を能動的に使うことを推す。

余剰 budget は、reliability を維持しながら変更速度を上げる余地として扱う。

根拠: [SRE Book Ch.3「Embracing Risk」](https://sre.google/sre-book/embracing-risk/)、
[The Site Reliability Workbook Ch.18「SRE Engagement Model」](https://sre.google/workbook/engagement-model/)。

### error budget が枯渇した場合: critical path 限定 freeze（暫定）

直近の compliance period（four-week rolling window）で current SLO の error budget を超過した場合、
**critical user journey の code path に触れる変更**の PR マージと Terraform apply を、SLO 内に戻るまで停止する。
対象は次の path とする。

- `backend/app/`
- `frontend/app/`、`frontend/lib/`
- `terraform/ephemeral/` のうち serving / frontend / Azure OpenAI に関わる部分

例外は次の 2 つに限る。

- security fix
- budget 消費の原因に対する bug fix

根拠: [The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)。

docs、backup / restore、CI、監視の追加など、critical user journey の code path に触れない変更は継続できる。
境界上の変更（例: 監視の追加が `backend/app/` に触れる）は freeze 対象として扱い、例外にする場合はその理由を PR に書く。

Rationale（暫定である理由を含む）:

- policy には、budget 枯渇時に必要な action と実行者を明記する。裁量的な延期だけでは足りない
- 全面停止ではなく、risk に比例した release 制御を採る
- 本 repository の主目的（Backup / Restore / Maintenance の設計・検証）は `POST /chat` の reliability と無関係な作業が多く、
  全面 freeze は policy の目的と衝突する
- freeze 対象を path で列挙することで、開発者と承認者が同一人物でも機械的に判定できる
- 全面 freeze（Workbook Example と 1:1）と現行の裁量的な運用を比較し、暫定で限定 freeze を採る。Revisit Date で見直す

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)、
[The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)、
[SRE Book Ch.3「Embracing Risk」](https://sre.google/sre-book/embracing-risk/)。

### 強制の手段: label と PR template の欄（暫定）

budget 超過を確認したら、project owner は次を行う。

1. Issue を起票し、compliance の評価結果（eligible / good / bad の count、残りの error budget、measurement の妥当性）と
   影響を受ける critical user journey を記録する
2. その Issue に label `status:blocked` を付け、freeze 中であることを示す
3. freeze 中に critical path に触れる PR を出す場合、PR 本文に「policy 適用外の理由」（security fix か、原因に対する bug fix か）を書く

CI による警告や block は導入しない。個人開発では機械的 block を自分で外せるため、block の強度は記録のみと実質変わらず、CI の複雑さだけ増える。
label と PR 本文の記録が繰り返し守られない場合は Revisit Date で CI warning への昇格を検討する。

### 原因別の must / may

原因に応じて reliability work を必須または任意とし、scope 外 traffic や user impact のない誤分類は再現性を確認した上で別扱いにする。

根拠: [The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)。

本 project では次のとおりとする。

| 原因 | freeze | reliability 作業 |
| --- | --- | --- |
| 自 code または手順の誤り | する | must |
| postmortem が hard dependency を緩める機会を示した | する | must |
| 誤分類で budget が消費されるべきだったのに消費されなかった | 再計算して超過ならする | must（SLI implementation の修正） |
| Azure 側の dependency（Container Apps / Azure OpenAI / PostgreSQL / Entra ID）の障害 | しない（下記） | hard dependency への対策の検討が must |
| SLO scope 外の traffic（load test、drill）が budget を消費した | しない | may。exclusion の再現性を確認する |
| 誤分類で user impact 無しに budget が消費された | しない | may。SLI implementation を修正する |

### dependency 起因の SLO miss（暫定）

dependency 起因の SLO miss では、原因に関係なく freeze する方式と、freeze せず resilience を高める方式がある。
本 project は service と dependency の性質を踏まえて後者を採り、決定理由を記録する。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)。

本 project は暫定で次を採る。

- dependency 起因の bad event も error budget を消費する（SRE Book Ch.3 §Benefits。slo-document.md の §補足と留意点）
- dependency 起因の SLO miss では freeze しない
- ただし hard dependency への対策（caching、graceful degradation、代替経路、retry 境界の再検討）の検討を **must** とし、
  postmortem または Issue に検討結果と採否の理由を記録する

Rationale: Azure 側の障害で freeze しても本 service 側に打つ手が無い期間が生じる。dependency の composite 参考値は
SLO target の硬い上限ではないが、dependency risk の input である。原因不問の freeze は採らず、hard dependency を
緩める設計（caching、graceful degradation、代替経路、retry 境界）を検討して記録する。この判断は暫定であり Revisit Date で見直す。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)。

### 例外

security remediation、data integrity の保護、incident の封じ込め、recovery、法令または policy の遵守、
制御不能な cost の防止は、reliability risk を伴う場合でも実施できる。emergency work であっても、可能な限り
evidence の記録、変更の scope、validation、rollback plan を省略しない。

例外を適用する場合は、次の内容を Issue または PR に記録する。

- 例外が必要な条件と、影響を受ける critical user journey
- 延期する方が大きな risk を生む理由
- 予想する reliability impact と判明している不確実性
- validation、rollback、containment の plan
- decision の timestamp、関連する Issue、PR、incident、ADR
- 直近の risk を制御した後に必要な follow-up

裁量的な作業を繰り返し緊急と呼ぶことで、恒常的な例外を作らない。

### freeze の解除条件

次の両方を満たした時に freeze を解除する。

- 直近の compliance period で current SLO 内に戻っている
- budget 消費の原因に対する action item が Issue として起票されている

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)。

単発の良好な測定結果だけで自動的に解除しない。解除前に、測定方法が有効であること、直近の user impact を封じ込めたか復旧したこと、
問題を示した evidence と比較可能な条件で再測定したことを確認し、解除の判断を Issue に記録する。

## outage 時の対応（Outage Policy）

単一の incident が直近の four-week rolling window の error budget の **20%** 超を消費した場合、postmortem を書く。
postmortem には root cause に対する action item を 1 件以上 Issue として含める。

同一 class の outage が四半期で error budget の 20% 超を消費した場合、翌四半期の作業計画に対応項目を置く。

根拠: [The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)。

20% は Workbook の Example の値を starter として採用したものであり、本 service の evidence に基づく値ではない。
low-traffic では単一の bad event が 20% を超えうるため、最初の baseline 後に measurement frequency とあわせて見直す。

postmortem の trigger は事前に定義する。

根拠: [SRE Book Ch.15「Postmortem Culture: Learning from Failure」](https://sre.google/sre-book/postmortem-culture/)。

本 project の trigger は、上記の 20% 条件に加えて、data loss、手動介入（rollback、traffic の切替）、monitoring failure
（SLO alert が鳴らずに手動で発見した incident）とする。

alert が発火しなかった incident は monitoring gap を示すため、postmortem の対象にする。

根拠: [SRE Book Ch.1「Introduction」](https://sre.google/sre-book/introduction/)。

postmortem は既存の `docs/verification/<campaign>/observations.md` pattern に置き、新しい evidence framework を追加しない。

## escalation（Escalation Policy）

error budget の計算または policy action に疑義がある場合は、決定責任者へ escalate し、根拠と決定を記録する。

根拠: [The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)。

§サービス概要 のとおり、本 project では disagreement の当事者と決定者が同一人物である。計算または action の妥当性に疑義がある場合、
project owner は疑義の内容、evidence、決定を Issue に記録し、その決定を Revisit Date まで維持する。
第三者の視点が必要な場合は外部レビュー（ADR-0028 で用いた外部 LLM レビューを含む）を任意で用い、その結果も Issue に記録する。
決定を Issue に記録せずに policy の action を省略しない。

## error budget の計算と評価

この節は Workbook の Example に無いが、本 service の request-based error budget を engineering decision に接続する規則として維持する。

### 計算

有効な SLO とその compliance period の error budget の定義と計算式は
[slo-document.md](./slo-document.md) の §error budget を正本とする。
この policy はその結果を engineering decision に接続する側だけを定める。

error budget の運用は、SLO を満たすための engineering decision を一貫させる。

根拠: [SRE Book Ch.4「Service Level Objectives」](https://sre.google/sre-book/service-level-objectives/)。

[slo-document.md](./slo-document.md) に記録した eligible event と good event の規則、SLI implementation version、
compliance period を使用する。error budget の単位は SLI と同じ request-based の単位とし、downtime の分数へ変換しない。

表示する比率を丸める前に、event 数から計算する。各結果には eligible event 数、good event 数、bad event 数、
query または tool の version、unclassifiable record、欠落した telemetry を残す。

error budget をこの policy の入力に使えるのは、[slo-document.md](./slo-document.md) の「有効化の条件」を満たし、
runbook で `sufficient` と記録された compliance period だけである。`Draft` または `insufficient` の期間は、
error budget を計算、報告、policy action の根拠に使用しない。

### 評価

review のたびに runbook に従い、最初に測定が有効であることを確認する。その後、有効な compliance period について、
観測した bad event 数と許容する bad event 数を比較する。丸めた割合だけでなく、各 event 数と残りの error budget を報告する。

### burn rate alerting（starting point は Workbook Table 5-8）

burn rate は次のように計算する。

```text
burn rate = alerting window における観測 bad event の割合を
            SLO が許容する bad event の割合で割った値
```

burn rate alerting を採用する場合、Workbook Table 5-8 を starting point とし、four-week（28 日 = 672 時間）window 用に
再計算した値を alert source に記録する。

根拠: [The Site Reliability Workbook Ch.5「Alerting on SLOs」](https://sre.google/workbook/alerting-on-slos/)。

Table 5-8 の parameter は 30 日 window を前提とするため、本 service の採用値ではない。
本 service の compliance period は four-week（28 日）なので burn rate は window 長に応じた再計算が要る
（burn rate = 消費割合 × window 時間 ÷ long window 時間）。再計算値は baseline に対して replay してから記入する（未記入）。

low-traffic のため paging は行わず、ticket（GitHub Issue の起票）のみとする。

通知手段は、budget の消費速度と対応の緊急性に合わせる。本 service は low-traffic のため ticket のみとする。

根拠: [The Site Reliability Workbook Ch.5「Alerting on SLOs」](https://sre.google/workbook/alerting-on-slos/)。

緩い SLO（例 90〜95%）を採る場合は 1 h / 2% の条件が発火しないことに注意する。

緩い SLO では短い alerting window の条件が構造上発火しないことがあるため、採用前に replay で確認する。

根拠: [The Site Reliability Workbook Ch.5「Alerting on SLOs」](https://sre.google/workbook/alerting-on-slos/)。

low-traffic での誤発火を防ぐ原型として、比率と絶対数の両方を条件にし、最小持続時間を設ける SRE Book Ch.10 の例を参考にする。

根拠: [SRE Book Ch.10「Practical Alerting from Time-Series Data」](https://sre.google/sre-book/practical-alerting/)。

採用前に、project の evidence に対して候補の logic を replay し、event volume、event がない interval、telemetry gap、
ingestion delay、alert precision、alert recall、detection time、reset time、運用対応能力を検証する。
それまでは、burn rate を action を開始する条件にしない。

## 測定が無効な場合

collection gap、eligible event の母集団を特定できない状態、query の不具合、timeout による censoring、
warm と cold の semantics の混在、configuration boundary、必要な field の欠落により信頼できる評価ができない場合は、
evidence record に「この SLO を信頼できる形で評価するための evidence が不足している」と記録する。

欠落した telemetry を good event に分類しない。未検証の値から error budget の消費や回復を算出しない。
利用可能な telemetry に合わせて SLO を変更しない。raw evidence の保持、影響期間の特定、測定の復旧、
修正した SLI implementation の検証を優先する。測定の復旧に必要な変更は、scope と rollback を記録できる場合に実施できる。

測定の復旧後も、独立した data source によって分類を再現できる場合を除き、観測していない user outcome を遡って推定しない。
gap は evidence record に明示する。

## regression への対応

有効な evidence に基づき、統計的または運用上意味のある regression が疑われる場合は、観測結果と configuration boundary を保持し、
原因を service に帰属させる前に測定の妥当性を確認する。現在の user impact と error budget を評価し、
予定する変更には §SLO miss 時の対応 を適用する。

調査、hypothesis、controlled change、比較可能な条件での再測定は [slo-review-runbook.md](./slo-review-runbook.md) の手順に従う。
SLO miss だけを理由に SLO を弱めない。user、business、risk、cost、architecture、測定の evidence が、
将来にのみ適用する revision を正当化する場合に限り変更する。

## incident への対応

SLO alert が発火したかどうかにかかわらず、実際に発生している、または信頼できる兆候がある user impact、security、
data integrity、recoverability に基づいて incident に対応する。incident 中は、次のように行動する。

- 詳細な SLO review より先に、user impact を復旧または封じ込める
- timestamp、request ID または correlation ID、deployment と configuration の識別情報、telemetry gap を保持する
- incident 中は SLI specification と有効な SLO target を変更しない
- 状況が安定した後、evidence が有効であれば、現在の error budget への影響を計算し、§outage 時の対応 の条件に該当するか判断する
- monitoring と SLO が incident を反映した、または反映しなかった理由を調査する

## policy の見直し

Revisit Date に見直す。それより前でも、service scope、critical user journey、SLI implementation、SLO、
user または business requirement、risk tolerance、dependency、architecture、運用対応能力、観測した incident の傾向が変わった場合、
または policy に基づく対応が繰り返し不釣り合い、不明確、実行不能となる場合は見直す。

revision ごとに、変更前と変更後の規則、理由、裏付ける evidence、decision date、effective date、過去の判断への影響を記録し、
ヘッダ表の Date / Approval Date / Revisit Date / Status を更新する。過去の履歴は保持する。
policy の変更によって、過去の SLO の結果を遡って変更したり、尽きた error budget を回復させたりしない。

## 背景（Background）

この節は Workbook の Example と同じく boilerplate であり、error budget に馴染みのない読者向けの要約である。

error budget は、SLO で定めた許容失敗量を使って、reliability と変更速度の優先順位を制御する。割合の定義と計算式は
`slo-document.md` を正本とする。

根拠: [The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)。

本 service での定義と計算式は [slo-document.md](./slo-document.md) の §error budget を参照する。

## 変更履歴

| 日付 | 変更内容 |
| --- | --- |
| 2026-08-30 | request-based の計算規則、比例的な engineering decision、測定が無効な場合の扱いを記録 |
| 2026-09-07 | Workbook Appendix B の節構成（ヘッダ表、Service Overview / Goals / Non-Goals / SLO Miss Policy / Outage Policy / Escalation Policy / Background）へ全面改訂。critical path 限定 freeze、label と PR 本文による強制、dependency 起因の miss の扱い、Outage Policy の 20%、Table 5-8 を starting point とする burn rate alerting を暫定で記録（#242） |

## 参考資料

### 主な方法論上の根拠

- [the Google SRE books（公式書籍一覧）](https://sre.google/books/)
- [Introduction](https://sre.google/sre-book/introduction/)
- [Embracing Risk](https://sre.google/sre-book/embracing-risk/)
- [Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Practical Alerting from Time-Series Data](https://sre.google/sre-book/practical-alerting/)
- [Postmortem Culture: Learning from Failure](https://sre.google/sre-book/postmortem-culture/)
- [A Collection of Best Practices for Production Services](https://sre.google/sre-book/service-best-practices/)
- [Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [SRE Engagement Model](https://sre.google/workbook/engagement-model/)
- [Example Error Budget Policy](https://sre.google/workbook/error-budget-policy/)

Example Error Budget Policy の 20% と Table 5-8 の parameter は starting point として採用し、本 service の evidence で見直す。

### Cross-check に用いた資料

- [Service level indicators in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/service-level-indicators-create)
- [Service level objectives (SLOs)](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-ServiceLevelObjectives.html)

### Project の根拠資料

- [ADR-0028: /chat の SSE 化と応答契約の固定](../../adr/0028-chat-sse-response-contract.md)
- [`/chat` SSE 共有 contract fixture](../../contracts/chat-sse/README.md)
