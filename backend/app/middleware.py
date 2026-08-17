"""request ID の貫通とアクセスログ（latency 計測）。

- 受信 `X-Request-ID` があれば尊重し、無ければ採番する
- request ID はログ（contextvar 経由）とレスポンスヘッダに貫通させる。
  下流呼び出し（DB / LLM。後続 PR）にも同じ ID を引き回すこと
- duration_ms をアクセスログに出す。エクスポート先の整備は Day 3 以降
  （現時点ではログに出すだけに留める。過剰実装しない）
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_setup import request_id_var

access_logger = logging.getLogger("app.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        access_logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                # contextvar は reset 済みのため明示的に渡す
                "request_id": request_id,
            },
        )
        return response
