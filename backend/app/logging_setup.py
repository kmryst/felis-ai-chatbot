"""構造化ログ（JSON 1行）の設定。

stdlib logging のみで実装する（5日制約下で structlog は過剰）。
request ID は contextvar で保持し、リクエスト処理中のすべてのログに自動で付く。

注意: ログに secret（API キー・パスワード・接続文字列）を出さないこと。
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# リクエスト処理中の request ID。ミドルウェアが設定する。
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id
        # logger.info(..., extra={"duration_ms": 12.3}) のような追加フィールドを拾う
        for key, value in record.__dict__.items():
            if key in ("duration_ms", "method", "path", "status_code", "request_id"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn の access log は自前のアクセスログ（request ID・duration 付き）と重複するため無効化
    logging.getLogger("uvicorn.access").disabled = True
