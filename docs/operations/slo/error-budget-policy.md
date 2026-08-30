# error budget の運用方針

## 目的

この方針は、有効になった SLO とその error budget を
`felis-ai-chatbot` の技術上の判断にどう反映するかを定める。このプロジェクトの
今後の判断に適用するものであり、SLA ではない。また、独立した SRE team、
product team、management approval process が存在することを前提としない。

service scope、SLI specification、SLI implementation、SLO の正本は
[slo-document.md](./slo-document.md) とする。測定結果は evidence record に保存し、測定、
調査、改善、review の手順は [slo-review-runbook.md](./slo-review-runbook.md) に定める。

現時点では、定量的な SLO も error budget も有効ではない。以下の規則を
適用できるのは、この方針に定める前提条件を満たした後に限る。以下の規則は、
新たな target 値、threshold、window、review frequency を定めるものではない。

## 適用範囲

この方針は、[slo-document.md](./slo-document.md) に記録する user-facing かつ
request-based の SLO だけに適用する。`/readyz`、observation freshness、CPU、
memory、replica count、RTO、RPO、その他の diagnostic metric や recovery
要件を、同じ error budget として扱わない。

この方針の適用と記録は project owner が担う。特定の判断について reviewer を
定めることはできるが、この文書に project に存在しない組織上の役割を追加しない。

## error budget の計算

有効な SLO とその compliance period について、次のように計算する。

```text
許容する bad event の割合 = 1 から SLO target を引いた値

許容する bad event 数 = 許容する bad event の割合と eligible event 数の積

残りの error budget = 許容する bad event 数から観測した bad event 数を引いた値
```

`slo-document.md` に記録した eligible event と good event の規則、SLI
implementation version、compliance period を使用する。error budget の単位は
SLI と同じ request-based の単位とし、downtime の分数へ変換しない。

表示する比率を丸める前に、event 数から計算する。各結果には eligible event 数、
good event 数、bad event 数、query または tool の version、unclassifiable record、
欠落した telemetry を残す。

次のすべてがそろうまでは、計算できる error budget は存在しない。

- 承認済みの SLO target と compliance period
- effective date と version
- 検証済みの SLI implementation
- 再現可能な eligible event と good event の分類
- 評価目的に照らして十分な evidence

## error budget の評価

review のたびに runbook に従い、最初に測定が有効であることを確認する。
その後、有効な compliance period について、観測した bad event 数と許容する
bad event 数を比較する。丸めた割合だけでなく、各 event 数と残りの
error budget を報告する。

burn rate を評価できるのは、その利用目的、look-back window、alert threshold、
no-data behavior を決定し、記録した後に限る。request-based の burn rate は
次のように計算する。

```text
burn rate = look-back window における観測 bad event の割合を
            SLO が許容する bad event の割合で割った値
```

The Site Reliability Workbook の multiwindow, multi-burn-rate alert の例や、Azure または AWS product
固有の default は、このプロジェクトの値ではない。burn rate alerting を採用する
前に、プロジェクトの evidence に対して候補の logic を replay し、event volume、
event がない interval、telemetry gap、ingestion delay、alert precision、alert recall、
detection time、reset time、運用対応能力を検証する。それまでは、burn rate を技術上の対応を
開始する条件にしない。

## 技術判断と対応

evidence、user impact、予定する変更の risk に応じて、対応の強さを決める。単一の
bad event やすべての SLO miss を理由に、feature 開発を自動的にすべて停止しない。

| 観測条件 | 必要な判断と対応 | 記録する evidence |
| --- | --- | --- |
| 測定が有効で、SLO を満たし、残りの error budget が尽きていない | プロジェクトの通常の優先順位で作業を続ける。各変更について、reliability risk と rollback を引き続き評価する。 | SLI の event 数、compliance の評価結果、残りの error budget、測定の妥当性、変更についての判断 |
| 採用済みで有効な burn rate alert の条件を満たした | 現在の user impact を評価し、error budget を消費している failure mode を調査し、予定する変更がその failure mode を悪化させるかを判断する。より安全で制御可能な対応になる場合は、mitigation または rollback を行う。 | alert の入力、event 数、impact、調査結果、判断、変更または rollback の evidence |
| 有効な evidence に基づき error budget が尽きた、または SLO miss となった | 影響を受ける critical user journey の reliability risk を増やす可能性がある裁量的な変更を延期する。復旧、測定を保全した調査、failure hypothesis に基づく作業を優先する。独立性と rollback を記録できる、無関係で risk の低い作業は継続できる。 | compliance の評価結果、影響を受ける critical user journey、原因または現時点の不確実性、延期した作業と許可した作業、hypothesis、recovery の evidence |
| user impact は重大だが、compliance period または event volume のため、まだ SLO miss になっていない | impact に基づいて incident に対応する。SLO は判断材料であり、error budget が残っている間は被害を無視してよいという許可ではない。 | incident の evidence、user impact、対応、SLI または target がその impact を表せなかったかどうか |
| SLO miss となったが、調査により SLI または SLO target が user requirement を表さなくなっていると判明した | 過去の結果を保持する。runbook に従って、将来にのみ適用する revision を提案する。SLO miss を消すために、過去の SLO target を書き換えたり event を再分類したりしない。 | 測定の調査結果、user または requirement の evidence、revision 案、decision date、将来の effective date |

## reliability に関する作業と feature 開発

reliability に関する作業は、観測した risk または検証可能な hypothesis に対応させる。
測定の復旧、user-facing な failure の修正、dependency または platform
behavior の改善、安全な rollback の追加、user impact を表していないことが
実証された SLI の修正などが該当する。

error budget が尽きた場合も、関連する reliability risk を十分に制御できない作業
だけを延期する。継続を認める作業については、独立している理由、または safety、
security、data integrity、recovery、cost control の利点が risk を上回る理由を
記録する。この文書で engineering capacity に新たな割合を割り当てたり、
別の定量的な gate を設定したりしない。

## 測定が無効な場合

collection gap、eligible event の母集団を特定できない状態、query の不具合、
timeout による censoring、warm と cold の semantics の混在、configuration
boundary、必要な field の欠落により信頼できる評価ができない場合は、次のように
記録する。

> この SLO を信頼できる形で評価するための evidence が不足している。

欠落した telemetry を good event に分類しない。未検証の値から error budget の
消費や回復を算出しない。利用可能な telemetry に合わせて SLO を変更しない。
raw evidence の保持、影響期間の特定、測定の復旧、修正した SLI implementation の
検証を優先する。測定の復旧に必要な変更は、scope と
rollback を記録できる場合に実施できる。

測定の復旧後も、独立した data source によって分類を再現できる場合を除き、
観測していない user outcome を遡って推定しない。gap は evidence record に
明示する。

## regression への対応

有効な evidence に基づき、統計的または運用上意味のある regression が疑われる場合は、
観測結果と configuration boundary を保持し、原因を service に帰属させる前に測定の
妥当性を確認する。現在の user impact と error budget を評価し、予定する変更には上記の
技術判断と対応を適用する。

調査、hypothesis、controlled change、比較可能な条件での再測定は
[slo-review-runbook.md](./slo-review-runbook.md) の手順に従う。SLO miss だけを理由に
SLO を弱めない。user、business、risk、cost、architecture、測定の evidence が、
将来にのみ適用する revision を正当化する場合に限り変更する。

## incident への対応

SLO alert が発火したかどうかにかかわらず、実際に発生している、または信頼できる
兆候がある user impact、security、data integrity、recoverability に基づいて
incident に対応する。incident 中は、次のように行動する。

- 詳細な SLO review より先に、user impact を復旧または封じ込める。
- timestamp、request ID または correlation ID、deployment と configuration の
  識別情報、telemetry gap を保持する。
- incident 中は SLI specification と有効な SLO target を変更しない。
- 状況が安定した後、evidence が有効であれば、現在の error budget への影響を
  計算する。
- monitoring と SLO が incident を反映した、または反映しなかった理由を調査する。

SLO alert は、security、cost、backup、data integrity の制御手段の代わりには
ならない。

## 例外

security remediation、data integrity の保護、incident の封じ込め、recovery、
法令または policy の遵守、制御不能な cost の防止は、reliability risk を伴う
場合でも実施できる。emergency work であっても、可能な限り evidence の記録、
変更の scope、validation、rollback plan を省略しない。

例外を適用する場合は、次の内容を記録する。

- 例外が必要な条件と、影響を受ける critical user journey
- 延期する方が大きな risk を生む理由
- 予想する reliability impact と判明している不確実性
- validation、rollback、containment の plan
- decision owner、timestamp、関連する Issue、PR、incident、ADR
- 直近の risk を制御した後に必要な follow-up

裁量的な作業を繰り返し緊急と呼ぶことで、恒常的な例外を作らない。

## 作業再開の条件

延期した作業の再開は判断を要する。単発の良好な測定結果だけで自動的に
再開しない。再開前に、次の項目を確認する。

- 測定方法が有効であること
- 直近の user impact を封じ込めた、または復旧したこと
- 問題を示した evidence と比較可能な条件で再測定したこと
- 過去の結果を書き換えず、有効な SLO と error budget を評価したこと
- failure hypothesis、実施した変更、比較結果、残る risk、rollback 可能な状態を
  記録したこと
- 予定する作業が同じ failure mode を再発または悪化させる可能性を判断したこと

project owner は、再開の判断を関連する evidence record と Issue または PR に
記録する。evidence が引き続き不足している場合は、その事実を明記する。SLO が
回復したと扱うのではなく、risk に基づく判断を明示する。

## policy の見直し

service scope、critical user journey、SLI implementation、SLO、user または
business requirement、risk tolerance、dependency、architecture、運用対応能力、
観測した incident の傾向が変わった場合は、この方針を見直す。また、方針に
基づく対応が繰り返し不釣り合い、不明確、実行不能となる場合や、user impact を
反映しない場合も見直す。

revision ごとに、変更前と変更後の規則、理由、裏付ける evidence、
decision date、effective date、過去の判断への影響を記録する。過去の履歴は
保持する。policy の変更によって、過去の SLO の結果を遡って変更したり、尽きた
error budget を回復させたりしない。

## 参考資料

### 主な方法論上の根拠

- [Embracing Risk](https://sre.google/sre-book/embracing-risk/)
- [Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [Example Error Budget Policy](https://sre.google/workbook/error-budget-policy/)
- [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)

`Example Error Budget Policy` と alerting の例にある数値条件は、それぞれの例に
固有であり、このプロジェクトでは採用しない。

### Cross-check に用いた資料

- [Service level indicators in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/service-level-indicators-create)
- [Service level objectives (SLOs)](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-ServiceLevelObjectives.html)
