# ADR-0004: LLM はスタブで開発し、CI・テストから LLM を呼ばない

## ステータス

Accepted

## 日付

2026-08-17

## 決定内容

- LLM（chat / embedding）への参照は `backend/app/llm/` に閉じ込め、他モジュールは `LLMClient` 経由でのみ利用する。Azure OpenAI / OpenAI API 両対応の抽象化レイヤーは作らず、提供元確定後に transport をこのモジュールへ追加して差し替える
- 開発・テスト・CI では**故障注入可能なスタブ**を使い、実 LLM（OpenAI / Azure OpenAI）を一切呼ばない
- すべての LLM 呼び出しに明示的な timeout を設定し、retryable なエラー（timeout / rate limit / server error）に限り、上限回数つき exponential backoff + jitter で retry する。bad request 系は retry しない
- embedding スタブは決定的（同一入力→同一ベクトル）で 1536 次元を返す

## 背景

- LLM 提供元は未確定（Azure OpenAI 可否判定 = Day 0 フェーズB が未実施）。提供元が決まらなくても Day 1〜2 の開発を止めない必要がある
- 本プロジェクトの主眼は PostgreSQL 運用であり、LLM 呼び出しの信頼性設計（timeout / retry / backoff）は「実装した」ではなく「意図的に失敗させて挙動を確認した」と言える状態にしたい

## 検討した選択肢

1. **スタブ（故障注入つき）で開発し、CI から LLM を呼ばない**（採択）
2. 実 LLM を CI から呼ぶ（record/replay なし）
3. VCR 等で実応答を録画して CI で再生する

## 採択理由

CI から実 LLM を呼ばない理由:

- **非決定的**で出力のアサーションが書けず、テストが flaky になる
- **遅い**（CI 時間が LLM 応答時間に律速される）
- **課金される**（PR ごとに費用が発生する）
- **CI に API キーを置きたくない**（漏洩面が増える。現時点ではそもそもキーが存在しない）

スタブに故障注入を持たせる理由:

- timeout / retry / exponential backoff は「失敗しないと動かないコード」であり、実 LLM 相手では再現条件を制御できない。遅延・例外・先頭 N 回失敗を決定的に注入できるスタブだけが、これらを再現可能にテストできる

## 却下理由

- 選択肢2: 上記4点そのまま。品質保証にならない
- 選択肢3: 録画資産の管理コストが 5 日制約に見合わず、録画には結局キーと課金が必要。故障系（429/5xx/timeout）の録画は特に困難

## 影響

- `LLM_PROVIDER` 既定は `stub`。本実装追加時も既定・テストはスタブのまま（実 LLM の疎通確認は手動・ローカルで行う）
- retry パラメータは環境変数（`LLM_TIMEOUT_SECONDS` / `LLM_MAX_ATTEMPTS` / `LLM_RETRY_BASE_DELAY_SECONDS` / `LLM_RETRY_MAX_DELAY_SECONDS`）
- pgvector の類似検索テストは手書きの固定ベクトルで行う（embedding 生成に LLM 不要。Day 1 PR 5）

## 未確定・要レビュー

- retry 既定値（3 回 / base 0.5s / max 8s / jitter 0.5〜1.5 倍）は一般的な初期値であり、実測に基づかない。提供元確定後、実 API のレート制限仕様に合わせて見直す

## 関連

- Issue: #16
- ADR-0003（embedding 1536 次元固定）
- `docs/operations/bootstrap.md` §2（Azure OpenAI 可否判定・フェーズB）
