"""FastAPI アプリケーション本体。

起動: `uv run uvicorn app.main:app --reload`（backend/ で実行）
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings
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
async def readyz() -> dict[str, str]:
    """readiness: トラフィックを受けられるか。

    現時点ではプロセス生存のみ。DB 到達性チェックは PR 2（docker compose +
    PostgreSQL）で追加する。
    """
    return {"status": "ok"}
