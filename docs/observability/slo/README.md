# SLI / SLO の実装資料

felis-ai-chatbot の SLI / SLO の計測・集計に用いる、具体的な仕様や設定をまとめる。
the Google SRE books 等の一次資料に基づく SRE の指針は `docs/operations/slo/` で管理し、このフォルダの実装資料から参照する。

## 資料

| 文書 | 内容 | 状態 |
| --- | --- | --- |
| [SLI measurement record schema](./sli-measurement-schema.md) | 記録項目名、型、未観測時の扱い、状態値、算出方法 | Draft（実装・検証前の仕様案） |

collector、保存先、集計処理は未実装または未決定である。実装時の設定・使用する版・検証結果への参照も、このフォルダで管理する。
実測や検証の証跡は、既存の [docs/verification/](../../verification/) に保存する。

## 参照する SRE の指針

- [SLO document](../../operations/slo/slo-document.md): service scope、SLI specification、SLO、timestamp / clock の定義
- [Error budget policy](../../operations/slo/error-budget-policy.md): error budget に基づく対応方針
- [SLO review runbook](../../operations/slo/slo-review-runbook.md): 計測の実装・検証、baseline 収集、SLO の採用・review の手順

指針の定義は各文書を参照し、このフォルダに複製しない。
