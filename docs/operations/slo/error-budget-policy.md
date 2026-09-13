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
| Date | 2026-09-13 |
| Reviewers | project owner |
| Approvers | project owner |
| Approval Date | 未定（Status を Published にする時に記入） |
| Revisit Date | 未定（`Published` 時に次の scheduled review date を記入） |

本 project は個人開発であり、Author / Reviewers / Approvers はすべて project owner が兼ねる（§サービス概要 参照）。

SLO compliance または error budget の計算結果を trigger とする、この policy の対応を新たに開始できるのは、
次のすべてを満たす場合だけである。

- この policy と [slo-document.md](./slo-document.md) の Status がともに `Published` である
- 両文書に Approval Date と Revisit Date が記録されている
- `slo-document.md` の「有効化の条件」を満たす SLO Version である
- runbook により、対象 compliance period の data quality / coverage が SLO compliance の評価に使用できると確認されている

いずれかの文書が `Draft`、または measurement validity を確認できない場合は、SLO compliance または error budget を根拠とする
change freeze、reliability work の優先、Outage Policy の 20% 条件、burn rate による対応を新たに開始しない。

この gate は、§incident への対応、または data loss、手動介入、monitoring failure という error budget と独立した postmortem trigger には
適用しない。実際の user impact、security、data integrity、recoverability に対する incident の宣言、containment、復旧を
SLO の Status や measurement validity の確認まで待機させない。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)、
[The Site Reliability Workbook Ch.9「Incident Response」](https://sre.google/workbook/incident-response/)、
[SRE Book Ch.14「Managing Incidents」](https://sre.google/sre-book/managing-incidents/)、
[Azure Well-Architected Framework「Architecture strategies for designing an incident management process」](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/incident-response)。

## 位置づけ: 原則からの導出

この policy は [slo-document.md](./slo-document.md) の「原則 5: error budget は objective で reproducible な意思決定のためにある」と
「原則 6: SLO は living document であり、review 結果に応じて iterate する」から導く。

error budget は、許容する失敗量を明示し、reliability と feature delivery の優先順位を evidence に基づいて判断するための指標である。

根拠: [SRE Book Ch.3「Embracing Risk」](https://sre.google/sre-book/embracing-risk/)。

この service への帰結は次のとおりである。

| 事実 | 帰結 |
| --- | --- |
| repository の主目的は Backup / Restore / Maintenance の設計・検証で、`POST /chat` と無関係な作業が多い | policy は罰や全面的な変更停止ではない。change freeze の対象を critical user journey に影響する変更に限定する |
| 各 critical dependency の障害が独立していると仮定した公称 SLA の積が約 99.74% | external dependency のみに起因すると evidence で確認できた miss では change freeze を発動せず、hard dependency への対策の検討を必須にする。service 側の寄与を分離できない場合は発動する |
| 実測 0 件、low-traffic | 20% や Table 5-8 は Workbook の starting point として置き、baseline 後に見直す。paging はせず ticket のみ |
| 最初の iteration | この policy も Draft であり、最初の Revisit Date に Workbook が示す 4 つの選択肢とあわせて見直す |

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
それを補うため、policy の発動・解除・例外の判断はすべて Issue に evidence とともに記録する。

`Draft` の間は scenario walkthrough で矛盾を修正してから承認する。`Published` 後は、その時点の発動・解除・例外の判断を回避するために
policy 本文をその場で変更してはならない。本文の revision は、Revisit Date の定期 review、または §policy の見直しに定めた早期 review の
trigger に該当する場合だけ、review record と将来の effective date を記録して行う。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)、
[The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)。

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
- aspirational SLO の miss はこの policy に定めた対応を開始しない。aspirational SLO は測定・追跡のみを行う
- [slo-document.md](./slo-document.md) の §SLO の範囲外 と §SLO の対象外の設定 に置いたもの（diagnostic metric、
  recovery 要件など）を、同じ error budget として扱わない
- この policy は security、cost、backup、data integrity の制御手段の代わりにならない

## SLO miss 時の対応（SLO Miss Policy）

change freeze の要否は次の順序で判定する。後続の節はこの順序を上書きしない。

1. change freeze が発動中なら、「change freeze の解除条件」を満たすまで継続する。measurement validity を確認できなくなったことだけを理由に解除しない
2. 発動中でなければ、両文書が `Published` であり、対象 compliance period の measurement validity を確認できるかを確認する。
   確認できなければ error budget から change freeze を発動せず、測定の復旧を Issue として追跡する
3. `remaining error budget >= 0` なら change freeze を発動しない
4. `remaining error budget < 0` なら原因を確認する。外部 dependency のみに起因すると確認できた場合は発動せず、それ以外、
   service と dependency の両方が原因の場合、または原因を確定できない場合は発動する
5. change freeze 中の個別変更は、production への潜在的影響を先に判定し、対象なら「change freeze の例外」に該当する場合だけ実施する

### remaining error budget が 0 以上の場合

change freeze が発動していなければ、release は通常どおり進める。各変更について reliability risk と rollback を引き続き評価する。
0 は error budget をすべて消費した SLO の境界であり、change freeze の新たな発動条件ではない。

budget に余裕があると判断できる期間には、reliability risk のある変更（dependency の upgrade、scaling 設定の実験、
cold start の再検証など）をこの期間に寄せる。余剰 budget は、reliability を維持しながら変更速度を上げる余地として扱う。

根拠: [SRE Book Ch.3「Embracing Risk」](https://sre.google/sre-book/embracing-risk/)、
[The Site Reliability Workbook Ch.18「SRE Engagement Model」](https://sre.google/workbook/engagement-model/)。

### remaining error budget が 0 未満の場合: critical user journey に影響する変更の change freeze（暫定）

有効な直近の compliance period（four-week rolling window）で、次の条件を満たした場合に原因を確認し、上記の順序で
change freeze の発動を判定する。

```text
remaining error budget < 0
```

change freeze 発動中は、critical user journey の availability、latency、total events に含める event、good / bad の判定、
その SLI implementation、または production environment を変え得る変更を、記録された例外なしに merge、deploy、
または `terraform apply` してはならない。対象かどうかは path 名ではなく production への潜在的影響で判定し、影響を否定できない変更は対象とする。

少なくとも次の path と変更種別は対象候補として必ず review する。この一覧は完全な allowlist または denylist ではない。

- runtime code と contract: `backend/app/**`、`POST /chat` の schema や挙動を変える `backend/migrations/**`、
  `frontend/app/**`、`frontend/lib/**`、`docs/contracts/chat-sse/**`
- build artifact と dependency: `backend/Dockerfile`、`backend/.dockerignore`、`backend/pyproject.toml`、`backend/uv.lock`、
  `frontend/Dockerfile`、`frontend/.dockerignore`、`frontend/package.json`、`frontend/package-lock.json`、
  `frontend/next.config.ts`、`frontend/tsconfig.json`
- production infrastructure と configuration: critical user journey に関係する `terraform/ephemeral/**` と `terraform/persistent/**`
- release、deployment、measurement: `scripts/deploy/**`、production deployment workflow、現在または将来の SLI collector、
  schema、query、alerting rule

docs、backup / restore、CI、monitoring の変更も、runtime、protocol、deployment procedure、または SLI の判定を変えないと
確認できる場合にだけ change freeze の対象外とする。

Rationale（暫定である理由を含む）:

- policy には、`remaining error budget < 0` の時に必要な対応と実行者を明記する。裁量的な延期だけでは足りない
- 全面停止ではなく、risk に比例した release 制御を採る
- 本 repository の主目的（Backup / Restore / Maintenance の設計・検証）は `POST /chat` の reliability と無関係な作業が多く、
  全面的な change freeze は policy の目的と衝突する
- path は review の開始点に使用し、規範的な判定は critical user journey と SLI implementation への潜在的影響に基づける
- 全面的な change freeze（Workbook Example と 1:1）と現行の裁量的な運用を比較し、暫定で対象を限定した change freeze を採る。
  Revisit Date の定期 review、または §policy の見直しに定めた早期 review で見直す

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)、
[The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)、
[SRE Book Ch.3「Embracing Risk」](https://sre.google/sre-book/embracing-risk/)。

### change freeze の適用と記録

`remaining error budget < 0` で change freeze を発動すると判断したら、project owner は次を行う。

1. Issue を起票し、compliance の評価結果（eligible / good / bad の count、remaining error budget、measurement validity）、
   原因の判定、影響を受ける critical user journey を記録する
2. その Issue に label `status:blocked` を付け、change freeze 中であることを示す
3. 各 PR で PR template の Error budget policy 欄を記入する。対象変更は、下記の例外に該当しない限り merge しない
4. PR を伴わない deploy または `terraform apply` でも、同じ判定と必要事項を change freeze の Issue に記録する

CI による警告や block は導入しない。個人開発では機械的 block を自分で外せるため、block の強度は記録のみと実質変わらず、
CI の複雑さだけ増える。Issue と PR 本文の記録が繰り返し守られない場合は §policy の見直しに定めた早期 review を開始し、
CI warning への昇格を検討する。

### 原因別に必要な reliability work

原因に応じて reliability work を必須または任意とし、scope 外 traffic や user impact のない誤分類は measurement validity の問題として扱う。

根拠: [The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)。

| 原因 | change freeze | reliability work |
| --- | --- | --- |
| service の code、configuration、release または手順 | `remaining error budget < 0` なら発動する | 必須 |
| service と external dependency の両方、または原因不明 | `remaining error budget < 0` なら暫定で発動する | 原因の分離と mitigation が必須 |
| external dependency のみ | 発動しない | hard dependency への対策の検討が必須 |
| 誤分類で budget が消費されるべきだったのに消費されなかった | SLI implementation を修正し、有効な data で再計算して上記の原因別規則に従う | 必須 |
| SLO scope 外の traffic、または user impact のない誤分類 | 発動判定に使用しない | exclusion の再現性を確認し、SLI implementation を修正する |

### dependency 起因の SLO miss（暫定）

dependency 起因の SLO miss では、原因に関係なく change freeze を適用する方式と、適用せず resilience を高める方式がある。
本 project は、external dependency のみに起因すると evidence で確認できた場合に後者を採り、決定理由を記録する。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)。

- dependency 起因の bad event も error budget を消費する（SRE Book Ch.3 §Benefits。slo-document.md の §補足と留意点）
- external dependency のみに起因すると確認できた SLO miss では change freeze を発動しない
- service 側の寄与を分離できない場合、または原因を確定できない場合は change freeze を発動する
- hard dependency への対策（caching、graceful degradation、代替経路、retry policy）の検討を必須とし、postmortem または Issue に
  検討結果と採否の理由を記録する

Rationale: Azure 側だけの障害に change freeze を適用しても本 service 側に打つ手が無い期間が生じる。各 dependency の障害が独立していると
仮定した公称 SLA の積は SLO target の上限ではないが、dependency risk を検討する際の参考情報である。この判断は暫定であり、
Revisit Date の定期 review、または §policy の見直しに定めた早期 review で見直す。

### change freeze の例外

change freeze 中に対象変更を実施できるのは、次のいずれかに該当する場合だけである。この一覧を例外の正本とし、
一般的な feature work の例外は設けない。

- security remediation
- data integrity の保護
- incident の封じ込めまたは recovery
- 法令または policy の遵守
- 制御不能な cost の防止
- error budget 消費の原因へ直接対処する bug fix
- measurement validity を回復するための、承認済み SLI implementation に限定した変更

Workbook の Example が直接列挙するのは P0 issue と security fix である。incident の封じ込めと recovery は incident response の一次資料、
error budget 消費の原因へ直接対処する bug fix は P0 issue と reliability work をこの project へ具体化したものである。data integrity、
法令・policy、制御不能な cost、measurement validity の各 category は、この error budget policy がより優先度の高い control を妨げること、
または policy が停止し続ける deadlock を避けるための project 固有の規則である。いずれも通常の feature work を例外にする根拠には使用しない。
emergency change にも事前に定めた authorization、可能な validation、rollback または containment、全操作の記録を要求する。

根拠: [The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)、
[The Site Reliability Workbook Ch.9「Incident Response」](https://sre.google/workbook/incident-response/)、
[Azure Well-Architected Framework「Architecture strategies for safe deployment practices」](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/safe-deployments)。

例外を適用する場合は、次の内容を Issue または PR に記録する。

- 適用する例外と、延期する方が大きな risk を生む理由
- 影響を受ける critical user journey、変更の scope、予想する reliability impact、判明している不確実性
- validation と、rollback または containment の plan
- decision の timestamp、関連する Issue、PR、incident、ADR
- 直近の risk を制御した後に必要な follow-up

external dependency のみに起因する miss で change freeze を発動しない規則は、個別変更の例外ではなく発動判定である。
裁量的な作業を繰り返し緊急と呼ぶことで、恒常的な例外を作らない。

### change freeze の解除条件

次のすべてを満たした時に change freeze を解除する。

- 両文書が `Published` であり、直近の compliance period の measurement validity を確認できる
- 同 period の `remaining error budget >= 0` を確認できる
- budget 消費の原因に対する action item が Issue として起票されている

単発の良好な測定結果や measurement validity を確認できなくなったことだけで解除しない。解除前に、直近の user impact を封じ込めたか
復旧したこと、問題を示した evidence と比較可能な条件で再測定したことを確認し、解除の判断を Issue に記録する。

根拠: [The Site Reliability Workbook Ch.2「Implementing SLOs」](https://sre.google/workbook/implementing-slos/)。

## outage 時の対応（Outage Policy）

単一の incident が直近の four-week rolling window の error budget の **20%** 超を消費した場合、postmortem を書く。
postmortem には root cause に対する action item を 1 件以上 Issue として含める。

同一 class の outage が四半期で error budget の 20% 超を消費した場合、翌四半期の作業計画に対応項目を置く。

根拠: [The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)。

20% は Workbook の Example の値を starter として採用したものであり、本 service の evidence に基づく値ではない。
low-traffic では単一の bad event が 20% を超えうるため、最初の baseline 後に measurement frequency とあわせて見直す。
この 20% 条件は、冒頭の gate を満たして error budget を有効に計算できる場合にだけ使用する。

postmortem の trigger は事前に定義する。

根拠: [SRE Book Ch.15「Postmortem Culture: Learning from Failure」](https://sre.google/sre-book/postmortem-culture/)。

本 project の trigger は、上記の 20% 条件に加えて、data loss、手動介入（rollback、traffic の切替）、monitoring failure
（SLO alert が鳴らずに手動で発見した incident）とする。後者 3 つは error budget と独立した trigger であり、文書が `Draft`、または
measurement validity を確認できない場合にも適用する。

alert が発火しなかった incident は monitoring gap を示すため、postmortem の対象にする。

根拠: [SRE Book Ch.1「Introduction」](https://sre.google/sre-book/introduction/)。

postmortem は既存の `docs/verification/<campaign>/observations.md` に記録し、別の記録体系を追加しない。

## escalation（Escalation Policy）

error budget の計算または policy に定めた対応に疑義がある場合は、決定責任者へ escalate し、根拠と決定を記録する。

根拠: [The Site Reliability Workbook Appendix B「Example Error Budget Policy」](https://sre.google/workbook/error-budget-policy/)。

§サービス概要 のとおり、本 project では disagreement の当事者と決定者が同一人物である。計算または対応の妥当性に疑義がある場合、
project owner は疑義の内容、evidence、決定を Issue に記録する。その決定は、その Revisit Date の定期 review、または
§policy の見直しに従う早期 review で記録した後続 decision の effective date まで維持する。
第三者の視点が必要な場合は外部レビュー（ADR-0028 で用いた外部 LLM レビューを含む）を任意で用い、その結果も Issue に記録する。
決定を Issue に記録せずに policy に定めた対応を省略しない。

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
query または tool の version、outcome を判定できなかった record、欠落した telemetry data を残す。

error budget をこの policy の入力に使えるのは、[slo-document.md](./slo-document.md) の「有効化の条件」を満たし、
SLI implementation と対象期間の data quality / coverage が検証され、SLO compliance を評価できる compliance period だけである。
`Draft` または measurement validity を確認できない期間は、error budget を計算、報告、error budget policy に定めた対応の根拠に使用しない。

### 評価

review のたびに runbook に従い、最初に測定が有効であることを確認する。その後、有効な compliance period について、
観測した bad event 数と許容する bad event 数を比較する。丸めた割合だけでなく、各 event 数と `remaining error budget` を報告する。

### burn rate alert（starting point は Workbook Table 5-8）

burn rate は次のように計算する。

```text
burn rate = alerting window における観測 bad event の割合を
            SLO が許容する bad event の割合で割った値
```

burn rate alert を採用する場合、Workbook Table 5-8 を starting point とし、four-week（28 日 = 672 時間）window 用に
再計算した値を alerting rule に記録する。

根拠: [The Site Reliability Workbook Ch.5「Alerting on SLOs」](https://sre.google/workbook/alerting-on-slos/)。

Table 5-8 の parameter は 30 日 window を前提とするため、本 service の採用値ではない。
本 service の compliance period は four-week（28 日）なので burn rate は window 長に応じた再計算が要る
（burn rate = error budget の消費割合 × compliance period の長さ ÷ long-window の長さ）。再計算値は baseline に対して replay してから
記入する（未記入）。

low-traffic のため paging は行わず、ticket（GitHub Issue の起票）のみとする。

通知手段は、budget の消費速度と対応の緊急性に合わせる。本 service は low-traffic のため ticket のみとする。

根拠: [The Site Reliability Workbook Ch.5「Alerting on SLOs」](https://sre.google/workbook/alerting-on-slos/)。

緩い SLO（例 90〜95%）を採る場合は 1 h / 2% の条件が発火しないことに注意する。

緩い SLO では短い alerting window の条件が構造上発火しないことがあるため、採用前に replay で確認する。

根拠: [The Site Reliability Workbook Ch.5「Alerting on SLOs」](https://sre.google/workbook/alerting-on-slos/)。

low-traffic での誤発火を防ぐ原型として、比率と絶対数の両方を条件にし、最小持続時間を設ける SRE Book Ch.10 の例を参考にする。

根拠: [SRE Book Ch.10「Practical Alerting from Time-Series Data」](https://sre.google/sre-book/practical-alerting/)。

採用前に、project の evidence に対して候補の logic を replay し、event volume、event がない interval、missing telemetry data、
ingestion delay、alert precision、alert recall、detection time、reset time、運用対応能力を検証する。
それまでは、burn rate を対応開始の条件にしない。

## 測定が無効な場合

欠落した scheduled execution または measurement result、eligible event の母集団を特定できない状態、query の不具合、
measurement timeout による right-censoring、
cold-start 時と warm instance 利用時の測定結果の混在、異なる configuration version の data の混在、必要な field の欠落により
信頼できる評価ができない場合は、「この SLO を信頼できる形で評価するための data quality または coverage が不足している」と記録する。

missing telemetry data を good event に分類しない。未検証の値から error budget の消費や回復を算出しない。
利用可能な telemetry に合わせて SLO を変更しない。raw evidence の保持、影響期間の特定、測定の復旧、
修正した SLI implementation の検証を優先する。change freeze が発動していなければ、無効な measurement から新たに発動しない。
すでに発動している場合は無効な measurement だけを理由に解除せず、測定の復旧に必要な変更にも「change freeze の例外」を適用する。

測定の復旧後も、独立した data source によって分類を再現できる場合を除き、観測していない user outcome を遡って推定しない。
gap の対象期間、原因、影響範囲を記録する。

## regression への対応

有効な evidence に基づき、統計的または運用上意味のある regression が疑われる場合は、観測結果、configuration version、変更時刻を保持し、
原因を service に帰属させる前に測定の妥当性を確認する。現在の user impact と error budget を評価し、
予定する変更には §SLO miss 時の対応 を適用する。

調査、hypothesis、controlled change、比較可能な条件での再測定は [slo-review-runbook.md](./slo-review-runbook.md) の手順に従う。
SLO miss だけを理由に SLO を弱めない。user、business、risk、cost、architecture、測定の evidence が、
将来にのみ適用する revision を正当化する場合に限り変更する。

## incident への対応

この節は SLO 文書の Status と measurement validity にかかわらず適用する。SLO alert が発火したかどうかにかかわらず、
実際に発生している、または信頼できる兆候がある user impact、security、data integrity、recoverability に基づいて incident に対応する。
incident 中は、次のように行動する。

- 詳細な SLO review より先に、user impact を復旧または封じ込める
- timestamp、request ID または correlation ID、commit SHA、deployment revision、image digest、configuration version、
  missing telemetry data を保持する
- incident 中は SLI specification と有効な SLO target を変更しない
- 状況が安定した後、evidence が有効であれば、現在の error budget への影響を計算し、§outage 時の対応 の条件に該当するか判断する
- monitoring と SLO が incident を反映した、または反映しなかった理由を調査する

根拠: [The Site Reliability Workbook Ch.9「Incident Response」](https://sre.google/workbook/incident-response/)、
[SRE Book Ch.14「Managing Incidents」](https://sre.google/sre-book/managing-incidents/)、
[Azure Well-Architected Framework「Architecture strategies for designing an incident management process」](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/incident-response)。

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
| 2026-09-07 | Workbook Appendix B の節構成（ヘッダ表、Service Overview / Goals / Non-Goals / SLO Miss Policy / Outage Policy / Escalation Policy / Background）へ全面改訂。critical user journey に影響する変更の change freeze、label と PR 本文による適用記録、dependency 起因の miss の扱い、Outage Policy の 20%、Table 5-8 を starting point とする burn rate alert を暫定で記録（#242） |
| 2026-09-13 | `change freeze`、data quality / coverage、alerting rule などの標準用語または対象を直接表す記述へ統一。両文書の `Published` 化、`remaining error budget < 0`、impact-based scope、例外と解除条件を一意の手順に整理。error-budget-driven action と常時適用する incident response を分離し、定期・早期 review による policy revision を明確化（#253） |

## 参考資料

### 主な方法論上の根拠

- [the Google SRE books（公式書籍一覧）](https://sre.google/books/)
- [Introduction](https://sre.google/sre-book/introduction/)
- [Embracing Risk](https://sre.google/sre-book/embracing-risk/)
- [Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Practical Alerting from Time-Series Data](https://sre.google/sre-book/practical-alerting/)
- [Managing Incidents](https://sre.google/sre-book/managing-incidents/)
- [Postmortem Culture: Learning from Failure](https://sre.google/sre-book/postmortem-culture/)
- [A Collection of Best Practices for Production Services](https://sre.google/sre-book/service-best-practices/)
- [Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [Incident Response](https://sre.google/workbook/incident-response/)
- [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [SRE Engagement Model](https://sre.google/workbook/engagement-model/)
- [Example Error Budget Policy](https://sre.google/workbook/error-budget-policy/)

Example Error Budget Policy の 20% と Table 5-8 の parameter は starting point として採用し、本 service の evidence で見直す。

### Cross-check に用いた資料

- [Service level indicators in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/service-level-indicators-create)
- [Architecture strategies for designing an incident management process](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/incident-response)
- [Architecture strategies for safe deployment practices](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/safe-deployments)
- [Service level objectives (SLOs)](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-ServiceLevelObjectives.html)

### Project の根拠資料

- [ADR-0028: /chat の SSE 化と応答契約の固定](../../adr/0028-chat-sse-response-contract.md)
- [`/chat` SSE 共有 contract fixture](../../contracts/chat-sse/README.md)
