import { createServer } from "node:http";
import { setTimeout as delay } from "node:timers/promises";
import { scenarios } from "./scenarios.mjs";

const EVENT_DELAY_MS = 25;
const MAX_BODY_BYTES = 4096;

function json(response, status, body) {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

async function handle(request, response) {
  if (request.method === "GET" && request.url === "/healthz") {
    json(response, 200, { status: "ok" });
    return;
  }
  if (request.method !== "POST" || request.url !== "/chat") {
    json(response, 404, { error: "Unknown route" });
    return;
  }
  if (!/^application\/json(?:;|$)/i.test(request.headers["content-type"] ?? "")) {
    json(response, 415, { error: "Expected application/json" });
    return;
  }

  const chunks = [];
  let bodyBytes = 0;
  for await (const chunk of request.iterator({ destroyOnReturn: false })) {
    bodyBytes += chunk.length;
    if (bodyBytes > MAX_BODY_BYTES) {
      request.resume();
      json(response, 413, { error: "Request body too large" });
      return;
    }
    chunks.push(chunk);
  }

  let body;
  try {
    body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    json(response, 400, { error: "Invalid JSON" });
    return;
  }
  if (
    body === null ||
    typeof body !== "object" ||
    Array.isArray(body) ||
    Object.keys(body).length !== 1 ||
    typeof body.message !== "string"
  ) {
    json(response, 400, { error: "Expected a message string" });
    return;
  }
  const scenario = scenarios.find(({ message }) => message === body.message);
  if (!scenario) {
    json(response, 400, { error: "Unknown scenario message" });
    return;
  }

  const cancellation = new AbortController();
  const cancel = () => cancellation.abort();
  response.once("close", cancel);
  response.writeHead(200, {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-store",
  });
  try {
    // Keep each delimiter and all canonical fixture bytes unchanged.
    for (const block of scenario.wireSse.split(/(?<=\n\n)/)) {
      if (cancellation.signal.aborted) return;
      response.write(Buffer.from(block, "utf8"));
      await delay(EVENT_DELAY_MS, undefined, { signal: cancellation.signal });
    }
    response.end();
  } catch (error) {
    if (!cancellation.signal.aborted) throw error;
  } finally {
    response.off("close", cancel);
  }
}

const server = createServer((request, response) => {
  handle(request, response).catch(() => {
    if (response.destroyed) return;
    if (response.headersSent) response.destroy();
    else json(response, 500, { error: "Fixture stub failed" });
  });
});

server.listen(18173, "127.0.0.1");

function shutdown() {
  server.close();
  server.closeAllConnections();
}

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
