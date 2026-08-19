"""FastAPI アプリケーション本体。

起動: `uv run uvicorn app.main:app --reload`（backend/ で実行）
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import Settings
from app.db import check_database_ready
from app.llm.client import (
    AzureOpenAIConfig,
    LLMError,
    RetryConfig,
    create_llm_client,
)
from app.llm.prompts import build_messages
from app.logging_setup import configure_logging
from app.middleware import RequestContextMiddleware

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
    allow_headers=["Content-Type", "X-Request-ID"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """liveness: プロセスが生きているかだけを返す。依存先（DB 等）は見ない。

    依存先を見ると、DB 障害時にコンテナ再起動ループを引き起こすため。
    """
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    """readiness: トラフィックを受けられるか。DB 到達性を実際に確認する。

    DB に到達できない間は 503 を返し、トラフィックを受けない。
    liveness（/health）とは役割が異なり、こちらが落ちてもプロセスは再起動されない。
    """
    db_ok = await check_database_ready(
        settings.database_url, settings.db_connect_timeout_seconds
    )
    if not db_ok:
        return JSONResponse(
            status_code=503, content={"status": "unavailable", "db": "unreachable"}
        )
    return JSONResponse(status_code=200, content={"status": "ok", "db": "ok"})


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    # 回答ごとの出典表示（references）は行わない（ADR-0008）。出典はツール
    # 全体としてフロントエンドのフッターで常設表示し、個別ページ URL へは
    # docs/data-sources.md で辿れるようにする
    reply: str


@app.post("/chat")
async def chat(req: ChatRequest) -> ChatResponse:
    """チャット応答（現在はスタブ LLM）。RAG 検索の本結線は次フェーズ。

    システムプロンプト（予報・警報の生成禁止。気象業務法対応。ADR-0008）を
    必ず適用する。
    """
    try:
        reply = await app.state.llm.chat(build_messages(req.message))
    except LLMError as exc:
        # 詳細（プロンプト等）はログに出さない。分類だけ返す
        logger.error(
            "chat failed", extra={"error_type": type(exc).__name__}
        )
        raise HTTPException(
            status_code=502, detail="LLM 呼び出しに失敗しました"
        ) from exc
    return ChatResponse(reply=reply)
