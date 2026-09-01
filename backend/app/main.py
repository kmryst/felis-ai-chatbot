"""FastAPI アプリケーション本体。

起動: `uv run uvicorn app.main:app --reload`（backend/ で実行）
"""

import logging
import secrets
from contextlib import asynccontextmanager

from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import CHAT_API_KEY_MIN_LENGTH, Settings
from app.db import check_database_ready, fetch_observation_freshness
from app.llm.client import (
    AzureOpenAIConfig,
    LLMError,
    RetryConfig,
    create_llm_client,
)
from app.llm.prompts import NO_CONTEXT_NOTICE, build_context, build_messages
from app.logging_setup import configure_logging
from app.middleware import RequestContextMiddleware
from app.rag import fetch_property_records, search_similar_documents
from app.sse import SSE_HEADERS, SSE_MEDIA_TYPE, error_class_for, format_sse_event

logger = logging.getLogger("app")

# 起動時に設定を読み、必須環境変数が欠けていれば即 fail する
settings = Settings.from_env()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # LLM クライアントは境界モジュール（app.llm）でのみ組み立てる（ADR-0004）
    app.state.llm = create_llm_client(
        settings.llm_provider,
        RetryConfig(
            max_attempts=settings.llm_max_attempts,
            timeout_seconds=settings.llm_timeout_seconds,
            base_delay_seconds=settings.llm_retry_base_delay_seconds,
            max_delay_seconds=settings.llm_retry_max_delay_seconds,
        ),
        # azure-openai のときだけ組み立てる（stub では credential を含む
        # オブジェクトを作らない）。endpoint / api_key の非空は Settings が
        # 起動時に保証している（config.py）
        azure=(
            AzureOpenAIConfig(
                endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                chat_deployment=settings.azure_openai_chat_deployment,
                embedding_deployment=settings.azure_openai_embedding_deployment,
            )
            if settings.llm_provider == "azure-openai"
            else None
        ),
    )
    if not settings.chat_api_key:
        # fail-closed の可視化（値は出さない）。本番でこの警告が出ていたら設定漏れ
        logger.warning("CHAT_API_KEY is not set; /chat is disabled (fail-closed)")
    logger.info("startup complete")
    yield
    # graceful shutdown の枠。DB プールのクローズ等は PR 2（DB 接続）で載せる
    logger.info("shutdown complete")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
# frontend（ブラウザ）からの呼び出し用。許可 origin は環境変数で絞る
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID", "X-API-Key"],
)


@app.get("/livez")
async def livez() -> dict[str, str]:
    """liveness: プロセスが生きているかだけを返す。依存先（DB 等）は見ない。

    依存先を見ると、DB 障害時にコンテナ再起動ループを引き起こすため。

    パス名は Kubernetes の標準に揃えている（liveness = /livez、readiness = /readyz の対）。
    /healthz は v1.16 で deprecated され、公式に "use livez and readyz instead" と
    書かれている。出典:
    https://kubernetes.io/docs/reference/using-api/health-checks/
    """
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    """readiness: トラフィックを受けられるか。DB 到達性を実際に確認する。

    DB に到達できない間は 503 を返し、トラフィックを受けない。
    liveness（/livez）とは役割が異なり、こちらが落ちてもプロセスは再起動されない。
    """
    db_ok = await check_database_ready(
        settings.database_url, settings.db_connect_timeout_seconds
    )
    if not db_ok:
        return JSONResponse(
            status_code=503, content={"status": "unavailable", "db": "unreachable"}
        )
    # 観測 3 系列の鮮度（#104。外形監視 #106 が系列別に判定する。
    # 取得できない場合は null — readiness の可否には影響させない）
    obs = await fetch_observation_freshness(
        settings.database_url, settings.db_connect_timeout_seconds
    )
    return JSONResponse(
        status_code=200, content={"status": "ok", "db": "ok", "obs": obs}
    )


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def _enforce_chat_gate(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """/chat の保護ゲート（Issue #107。ADR-0020 の常時稼働の先行ゲート）。

    route の dependency として評価される（Issue #113 の 2）。FastAPI は
    dependencies をボディ検証より先に解決するため、無認証・遮断中のリクエストに
    フィールド名入りの 422 詳細を返さない（ゲートが 404 / 401 を先に返す）。

    - 緊急遮断フラグ（CHAT_DISABLED=true）: 404。消費超過時の打ち切りスイッチ
      （credit-window-execution-plan.md §9 の 2）。HTTP 応答上は「/chat が無い」
      ように見せる。ただし /docs・/openapi.json には /chat が載ったままであり、
      スキーマ面の存在秘匿はしていない（本番構成で閉じるかは Issue #113 の 1 =
      ユーザー判断待ち）
    - API キー未設定・空白のみ・最小長（32 文字）未満: 404（fail-closed）。キーを配らずに
      デプロイした場合や弱い鍵の設定ミスで、無認証・弱認証の LLM 課金経路が公開される事故を
      「/chat が無い」側に倒す
    - キー不一致・未提示: 401。比較は secrets.compare_digest（タイミング攻撃対策の定石。
      このアプリの脅威モデルでは過剰気味だが、コストゼロなので定石に従う）
    - /readyz・/livez はこのゲートの対象外（外形監視と両立させる。#106）
    """
    # 最小長チェックは from_env（起動時）と二重に行う（防御の深さ。
    # from_env を経ない経路で短い / 空白のみのキーが settings に入っても閉じたままにする）
    if (
        settings.chat_disabled
        or len(settings.chat_api_key.strip()) < CHAT_API_KEY_MIN_LENGTH
    ):
        raise HTTPException(status_code=404, detail="Not Found")
    if x_api_key is None or not secrets.compare_digest(
        x_api_key.encode(), settings.chat_api_key.encode()
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _guard_notice_events() -> AsyncIterator[str]:
    """guard 経路の wire 出力: `notice` → `done`（ADR-0028 決定 3）。

    raw stream を持たず直接生成する（LLM を呼ばない構造は不変。ADR-0010）。
    """
    yield format_sse_event("notice", {"text": NO_CONTEXT_NOTICE})
    yield format_sse_event("done", {})


async def _chat_stream_events(deltas: AsyncIterator[str]) -> AsyncIterator[str]:
    """LLM stream を wire contract の event 列へ組み立てる（ADR-0028 決定 2）。

    - 正常: `message`（1 回以上）→ `done`（1 回）。`done` の送出は変換器
      （decision 5 の表の実装 = app.llm.streaming）が raw `[DONE]` の受信まで
      遅延させた結果の正常 return に対応する
    - 失敗: `message`（0 回以上）→ `error`（1 回）で終端し `done` を出さない。
      error の data は class のみ（詳細メッセージを含めない）。content filter の
      error field 検出時は class `content_filter` になり、consumer 側の
      撤回契約（決定 6）の入力になる
    - client 切断時は StreamingResponse が本 generator を close し、
      LLMClient.chat_stream → transport の finally が provider stream を
      打ち切る（決定 2）
    """
    try:
        try:
            async for delta in deltas:
                # 変換器は非空 content のみを yield する（決定 4: 空 message を
                # 送出しない）
                yield format_sse_event("message", {"text": delta})
        except LLMError as exc:
            # 詳細（プロンプト等）はログに出さない。wire には class だけ載せる
            logger.error(
                "chat stream failed", extra={"error_type": type(exc).__name__}
            )
            yield format_sse_event("error", {"class": error_class_for(exc)})
            return
        yield format_sse_event("done", {})
    finally:
        # client 切断（GeneratorExit）を含むあらゆる終了経路で upstream の
        # generator を閉じ、provider stream を打ち切る（決定 2）
        aclose = getattr(deltas, "aclose", None)
        if aclose is not None:
            await aclose()


@app.post("/chat", dependencies=[Depends(_enforce_chat_gate)])
async def chat(req: ChatRequest) -> StreamingResponse:
    """RAG つきチャット応答（ADR-0010）。応答は SSE（ADR-0028）。

    - ユーザー質問を embedding し、documents を cosine 類似度で検索する
    - ハルシネーション・ガード: 検索結果が 0 件、または最上位の類似度が
      閾値未満なら、LLM を呼ばずに固定文言（NO_CONTEXT_NOTICE）を `notice`
      event で返す。参照資料が空のとき LLM が事前知識で誤答する事象を
      実測しており、プロンプト指示ではなくコードで担保する
    - システムプロンプト（予報・警報の生成禁止。気象業務法対応。ADR-0008）を
      必ず適用する。回答ごとの出典表示（references）は行わない（ADR-0008。
      出典はフロントエンドのフッターに常設表示する）
    - ストリーム開始前の失敗（ゲートの 404 / 401、validation の 422、
      embedding の 502、検索の 503）は SSE を開始せず現行の HTTP status を
      維持する。chat stream 開始後の失敗は `error` event で終端する
    """
    try:
        query_embedding = await app.state.llm.embed(req.message)
    except LLMError as exc:
        logger.error(
            "chat embed failed", extra={"error_type": type(exc).__name__}
        )
        raise HTTPException(
            status_code=502, detail="LLM 呼び出しに失敗しました"
        ) from exc

    try:
        chunks = await search_similar_documents(
            settings.database_url,
            query_embedding,
            settings.rag_top_k,
            settings.db_connect_timeout_seconds,
        )
    except Exception as exc:
        # DSN（secret）を含み得るため例外本文は出さずクラス名のみログへ
        logger.error(
            "rag search failed", extra={"error_type": type(exc).__name__}
        )
        raise HTTPException(
            status_code=503, detail="検索に失敗しました"
        ) from exc

    top_similarity = chunks[0].similarity if chunks else None
    if not chunks or top_similarity < settings.rag_similarity_threshold:
        # ガード発動: LLM は呼ばない（ADR-0010）
        logger.info(
            "rag guard rejected",
            extra={
                "top_similarity": top_similarity,
                "threshold": settings.rag_similarity_threshold,
            },
        )
        return StreamingResponse(
            _guard_notice_events(),
            media_type=SSE_MEDIA_TYPE,
            headers=SSE_HEADERS,
        )

    try:
        property_records = await fetch_property_records(
            settings.database_url, settings.db_connect_timeout_seconds
        )
    except Exception as exc:
        logger.error(
            "rag properties fetch failed",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=503, detail="検索に失敗しました"
        ) from exc

    context = build_context(
        [chunk.content for chunk in chunks], property_records
    )
    # ここから先の失敗は chat stream の失敗であり、SSE の `error` event で
    # 終端する（retry は最初の content delta 受信前に限る。ADR-0028 決定 10。
    # retry・timeout・raw stream の変換は app.state.llm.chat_stream が担う）
    deltas = app.state.llm.chat_stream(build_messages(req.message, context))
    return StreamingResponse(
        _chat_stream_events(deltas),
        media_type=SSE_MEDIA_TYPE,
        headers=SSE_HEADERS,
    )
