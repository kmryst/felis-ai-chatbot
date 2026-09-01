#!/usr/bin/env python3
"""Ephemeral verification server for Issue #183.

Endpoints:
  GET /            -> "ok" (health / revision marker via REV_MARKER env)
  GET /echo        -> JSON echo of all received request headers (header-spoofing test)
  GET /sse?interval=<sec>&count=<n>  -> SSE stream, one `message` event every <interval> sec,
                                        <n> events, then a `done` event. Chunked transfer.
Disposable. No dependencies (Python stdlib only).
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", "8080"))
REV_MARKER = os.environ.get("REV_MARKER", "unset")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _write_chunk(self, data: bytes) -> bool:
        try:
            self.wfile.write(b"%X\r\n" % len(data))
            self.wfile.write(data)
            self.wfile.write(b"\r\n")
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)

        if u.path == "/echo":
            payload = {
                "path": self.path,
                "rev_marker": REV_MARKER,
                "server_time": time.time(),
                "received_headers": {k: v for k, v in self.headers.items()},
            }
            body = json.dumps(payload, indent=2, sort_keys=True).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if u.path == "/sse":
            interval = float(q.get("interval", ["10"])[0])
            count = int(q.get("count", ["10"])[0])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            start = time.time()
            # initial comment so the client sees bytes immediately
            self._write_chunk(b": stream-open rev=" + REV_MARKER.encode() + b"\n\n")
            for i in range(count):
                time.sleep(interval)
                elapsed = round(time.time() - start, 3)
                data = json.dumps({"seq": i, "elapsed_s": elapsed, "epoch": time.time()})
                if not self._write_chunk(("event: message\ndata: %s\n\n" % data).encode()):
                    sys.stderr.write("client gone at seq=%d elapsed=%.3f\n" % (i, elapsed))
                    return
                sys.stderr.write("sent seq=%d elapsed=%.3f\n" % (i, elapsed))
            self._write_chunk(b"event: done\ndata: {}\n\n")
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except OSError:
                pass
            return

        # root / health
        body = ("ok rev=%s\n" % REV_MARKER).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    sys.stderr.write("listening on :%d rev=%s\n" % (PORT, REV_MARKER))
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
