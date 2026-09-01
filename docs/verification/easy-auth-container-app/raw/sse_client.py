#!/usr/bin/env python3
"""SSE timing client for Issue #183 ingress-timeout test.

Usage: sse_client.py <url> <label>
Logs, with wall-clock elapsed seconds, every line received and the
disconnect condition (clean end, error, or how long after the last byte
the socket was closed).
"""
import socket
import ssl
import sys
import time
from urllib.parse import urlparse

url = sys.argv[1]
label = sys.argv[2]
u = urlparse(url)
host = u.hostname
port = u.port or (443 if u.scheme == "https" else 80)
path = u.path + ("?" + u.query if u.query else "")

start = time.time()


def log(msg):
    sys.stdout.write("[%s t=%8.2f] %s\n" % (label, time.time() - start, msg))
    sys.stdout.flush()


log("connecting to %s:%d path=%s" % (host, port, path))
raw = socket.create_connection((host, port), timeout=30)
if u.scheme == "https":
    ctx = ssl.create_default_context()
    sock = ctx.wrap_socket(raw, server_hostname=host)
else:
    sock = raw

req = (
    "GET %s HTTP/1.1\r\nHost: %s\r\nAccept: text/event-stream\r\n"
    "User-Agent: felis-ephem-183-timing\r\nConnection: close\r\n\r\n"
    % (path, host)
)
sock.sendall(req.encode())
log("request sent")

sock.settimeout(600)
last_byte_t = time.time()
buf = b""
try:
    while True:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            log("SOCKET RECV TIMEOUT (600s no data) -- giving up")
            break
        now = time.time()
        if not chunk:
            gap = now - last_byte_t
            log("CONNECTION CLOSED by peer. gap since last byte = %.2fs" % gap)
            break
        last_byte_t = now
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.rstrip(b"\r").decode("utf-8", "replace")
            if text.startswith("event:") or text.startswith("data:") or text.startswith(":"):
                log("RECV %s" % text)
            elif text == "":
                pass
            else:
                log("RECV(raw) %s" % text)
except Exception as e:  # noqa: BLE001
    log("EXCEPTION %r after %.2fs since last byte" % (e, time.time() - last_byte_t))
finally:
    sock.close()
    log("done. total elapsed %.2fs" % (time.time() - start))
