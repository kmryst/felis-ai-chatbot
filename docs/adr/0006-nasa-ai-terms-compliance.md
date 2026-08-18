# ADR-0006: NASA AI 条項準拠 — 帰属の対象を AI 生成文から未加工の原文抜粋へ付け替える

## ステータス

Superseded（[ADR-0008](./0008-jma-attribution-and-weather-act-compliance.md) により置き換え）

## 日付

2026-08-18

## 決定内容

NASA Brand Center の "Artificial Intelligence (AI) Applications" 条項（<https://www.nasa.gov/nasa-brand-center/images-and-media/>）に準拠するため、次の 3 点を実装する。

1. **AI 生成文には出典を付けない。** システムプロンプトで「NASA によると」「NASA 公式では」等の帰属表現と、NASA による審査・許可・公認を示唆する表現を禁止し、資料の内容に言及する場合は「参照資料には〜と記載されています」という資料参照の形へ誘導する（`backend/app/llm/prompts.py`）
2. **出典（URL / ページタイトル / 取得日 / クレジット）は、LLM を通していない未加工の原文抜粋にのみ付ける。** `/chat` レスポンスの `references` フィールドに原文抜粋 + 出所を載せ、フロントエンドは回答本文と分離した折りたたみ枠「参照した資料」にのみ表示する。RAG 本結線は次フェーズのため、現時点では器（構造）のみ用意し `references` は常に空
3. **ツール全体としての開示をフッターに常設する。** 「本ツールは NASA の公開情報を素材として利用しています。回答は AI が生成したものであり、NASA による審査・許可・公認を受けたものではありません。NASA の見解ではありません。」

データベースの provenance 設計（ADR-0003。`object_properties.source_id NOT NULL` による値ごとの出所記録）は変更しない。**表示上の帰属を制限することと、記録上の出所管理を厳密に行うことは独立**であり、後者はむしろ強化する。

## 背景

本チャットボットは NASA の公開情報（science.nasa.gov / imagine.gsfc.nasa.gov / nasa.gov）を素材として利用する。NASA Brand Center の AI 条項は、AI 製品に対して明文の制約を置いている（2026-08 時点の原文）。

> attribution of the information directly to NASA is **not permitted**
>
> References like "according to NASA" or similar are **prohibited** in AI products
>
> As a statement of fact, you can acknowledge your AI tool includes NASA source material, but **do not imply any review or permission was granted by NASA**
>
> NASA strongly encourages AI-generated products maintain a marking indicating the product is AI generated

一方で、素材としての取り込み・利用そのものは禁止されていない。したがって「NASA によると〜」と喋らせる実装は明確に禁止であり、AI 生成物である旨の表示は強く推奨されている。

## 検討した選択肢

1. **帰属の対象を未加工の原文抜粋に付け替える**（採択）— AI 生成文は無帰属、出典は LLM を通していない原文引用にのみ付け、ツール単位の開示をフッターに常設する
2. **回答ごとに「参照ソース」ブロックとして出典 URL 等を列挙する**（当初案。撤回）— 回答本文と視覚的に分離したブロックに、その回答の生成に使った出典を列挙する
3. **出典を一切表示しない** — 帰属リスクは最小だが、provenance を示せることが本プロジェクトの要件であり不採用

## 採択理由（当初案を撤回した経緯を含む）

最初の設計案は選択肢 2 だった。「帰属の形にしなければ出典の事実列挙は許可されている」という読みで、回答ごとに出典 URL を分離ブロックに並べる設計である。しかしレビューで「それも『NASA によると』と言っているのと大差ないのではないか」という指摘を受け、条文を読み直した結果、以下の理由で撤回した。

- 許可文言の主語は **"your AI tool"** である（"you can acknowledge **your AI tool** includes NASA source material"）。許可されているのは**ツール全体についての開示**であって、回答 1 件ごとに出典を並べることではない
- 回答ごとに出典を付ける形は、その生成文の内容を NASA に帰属させているのと機能的に同じであり、禁止条項 "attribution of the information directly to NASA is not permitted" に接近する
- 禁止の理由は「LLM に取り込まれた後の情報の正確性を NASA が保証できない」ことにある。**LLM が生成した文に NASA の出典を並べる形は、まさにこの懸念そのもの**になる

そこで、帰属の対象を「生成文」から「未加工の原文」に付け替えた。

- **AI 生成文（reply）**: 無帰属。AI 製品自身に帰属させ、フッターの常設開示（NASA 素材を含む事実 + AI 生成である旨 + 無公認の明示）でツール単位の開示を行う。これは条項が明示的に許可している形である
- **未加工の原文抜粋（references）**: 検索でヒットした原文を、LLM を通さずそのまま引用し、回答と明確に分離した枠に表示する。ここには URL / ページタイトル / 取得日 / クレジットを付ける。LLM を通っていない原文であれば「取り込み後の正確性を保証できない」という NASA の懸念が発生しないため、帰属させて問題ない

最初から正解だったように記録するのではなく、この線引きに至った過程を残す（ツール単位の開示とレスポンス単位の帰属は別物である、という区別が本 ADR の核心である）。

## 影響

- `backend/app/llm/prompts.py` のシステムプロンプトが帰属表現を禁止する。禁止フレーズはテスト（`tests/test_prompts.py`）で検証する
- `/chat` レスポンスに `references: list[Reference]`（excerpt / url / title / retrieved_at / credit）が追加される。RAG 本結線（次フェーズ）では、検索でヒットした `documents` チャンクの原文と `sources` 行の情報をここへ詰める。**チャンクを LLM で要約・書き換えして references に入れてはならない**（未加工であることが帰属を許す前提のため）
- フロントエンドは references を折りたたみ枠「参照した資料（未加工の抜粋）」にのみ表示し、AI 生成の回答本文とは混在させない
- フッターの開示文言は常設とし、削除・簡略化する場合は本 ADR の再検討を要する
- NASA インシグニア（Meatball / Worm / Seal）・NASA 画像は AI 生成物への表示・学習利用とも不許可のため使用しない。第三者クレジット付き素材（ESA / ESO / STScI 等）も使用しない
- DB スキーマ（ADR-0003）は変更なし。値ごとの provenance 記録は表示方針と独立に維持する

## 関連

- [ADR-0008](./0008-jma-attribution-and-weather-act-compliance.md) — 題材の気象庁乗り換え（ADR-0007）に伴い本 ADR を置き換えた
- Issue: #33
- ADR-0003（provenance スキーマ設計）
- ADR-0004（スタブ LLM）
- NASA Brand Center: <https://www.nasa.gov/nasa-brand-center/images-and-media/>
