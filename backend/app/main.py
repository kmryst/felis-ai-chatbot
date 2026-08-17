"""FastAPI アプリケーション本体。

起動: `uv run uvicorn app.main:app --reload`（backend/ で実行）
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import Settings
from app.db import check_database_ready
from app.logging_setup import configure_logging
from app.middleware import RequestContextMiddleware

logger = logging.getLogger("app")

# 起動時に設定を読み、必須環境変数が欠けていれば即 fail する
settings = Settings.from_env()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup complete")
    yield
    # graceful shutdown の枠。DB プールのクローズ等は PR 2（DB 接続）で載せる
    logger.info("shutdown complete")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)


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
