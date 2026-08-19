# ADR-0009: LLM 提供元を Azure OpenAI（japaneast）に確定する

## ステータス

Accepted

## 日付

2026-08-19

## 決定内容

- LLM 提供元を **Azure OpenAI Service** に確定する（Day 0 フェーズB「Azure OpenAI 可否判定」の結論。`docs/operations/bootstrap.md` §2）
- リソースは `felisaichatbot-openai-dev`（リソースグループ `rg-felisaichatbot-dev` / **japaneast**）
  - デプロイ `chat`: gpt-4.1-mini 2025-04-14 / **GlobalStandard** / capacity 10
  - デプロイ `embedding`: text-embedding-3-small v1 / **Standard** / capacity 10（1536 次元。ADR-0003 のとおり）
- backend には `AzureOpenAITransport` を `backend/app/llm/client.py` へ追加する（ADR-0004 の方針どおり transport 追加のみ。抽象化レイヤーは新設しない）
- `LLM_PROVIDER` の既定は `stub` のまま維持し、CI・テストから実 LLM を呼ばない決定（ADR-0004）は変更しない。実 LLM は `LLM_PROVIDER=azure-openai` の明示指定でのみ使う
- api-version は疎通実測済みの GA 版 `2024-10-21` を既定とする（`AZURE_OPENAI_API_VERSION` で上書き可能）
- 認証は当面 **API キー**（`.env` にのみ置く。コミット禁止）。**Day 3 で Managed Identity への置き換えを検討する**

## 背景

- ADR-0004 時点では提供元（Azure OpenAI / OpenAI API）が未確定で、スタブで開発を進めていた。bootstrap §2 の可否判定（タイムボックス 2h・撤退基準つき）を実施し、撤退基準に該当せず Azure OpenAI 採用が確定した
- リージョン決定ルール（bootstrap §2）: アプリと PostgreSQL は必ず同一リージョン、LLM は跨いでよい。判定の結果、chat / embedding の両方が japaneast で取れたため、アプリ・PostgreSQL・LLM をすべて japaneast に置ける構成になった

## 制約: chat デプロイが GlobalStandard SKU であること

正直に記録する。**無料試用サブスクリプションでは、japaneast の Standard 系 chat モデルのクォータがすべて limit 0 だった。** limit > 0 だった chat 系は `GlobalStandard.gpt4.1-mini`（200）と `GlobalStandard.gpt-5-mini`（500）のみで、`gpt-4o-mini` はクォータ一覧に存在しなかった。このため chat は GlobalStandard SKU の gpt-4.1-mini を選んだ。

この選択の含意:

- **保存データ（at rest）と embedding の処理は japaneast 内に留まるが、chat の推論処理（GlobalStandard のルーティング）はリージョンを跨ぎ得る**
- 有償契約（Pay-As-You-Go 以上）で Standard 系クォータが付与されれば、デプロイの SKU を Standard へ切り替えることで chat も japaneast 内に閉じられる。アプリ側は SKU を意識しない（エンドポイント・デプロイ名は不変）ため、切り替えにコード変更は不要

## 検討した選択肢

1. **Azure OpenAI Service（japaneast / chat は GlobalStandard）**（採択）
2. OpenAI API へのフォールバック

## 採択理由

- 可否判定の撤退基準（クォータ承認待ち・どちらか一方でもデプロイ不可・タイムボックス超過）に該当しなかった。第一選択をそのまま採る
- chat / embedding の両方が japaneast のリソースで疎通済み（chat は日本語応答、embedding は 1536 次元を実測）
- アプリ・PostgreSQL（Day 3 以降）と同一リージョンに LLM リソースを置け、Day 3 の Key Vault / Managed Identity / Private ネットワーク統合など Azure ネイティブの運用設計に自然につながる

## 却下理由

- 選択肢2（OpenAI API）: フォールバック条件（撤退基準）に該当しなかったため採らない。採ると認証が Azure の外に出て Managed Identity 化（Day 3）の対象外になり、キー管理の面が増える。embedding を text-embedding-3-small（1536 次元）で統一している限り将来の切り替え余地は残る

## 影響

- `LLM_PROVIDER=azure-openai` のとき `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` が必須（欠落は起動時 `MissingEnvError`）。`stub` のままなら不要（CI・既存テストに影響なし）
- transport は timeout / retry / backoff を再実装せず、HTTP エラーの分類（429 → rate limit / 5xx → server error / その他 4xx → bad request）だけを担う。分類はテスト（`tests/test_azure_transport.py`）で検証する
- httpx を dev 依存から本体依存へ昇格する。**openai SDK は追加しない**（SDK 内蔵の retry が既存の `LLMClient` の retry と二重になるため。REST エンドポイント 2 本（chat / embedding）の直叩きで十分）
- retry 既定値（ADR-0004 の「未確定・要レビュー」）は今回も据え置き。GlobalStandard capacity 10 の実運用でレート制限に当たったら見直す

## 関連

- Issue: #49
- ADR-0003（embedding 1536 次元固定）
- ADR-0004（スタブ開発・CI から実 LLM を呼ばない。**この決定は本 ADR 後も有効**）
- ADR-0008（気象業務法対応システムプロンプト。実 LLM での挙動実測は Issue #49 で実施）
- `docs/operations/bootstrap.md` §2（可否判定・リージョン決定ルール・判定結果）
