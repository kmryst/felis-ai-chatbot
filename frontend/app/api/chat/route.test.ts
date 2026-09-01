/**
 * BFF POST /api/chat のテスト（ADR-0027 決定 2 / 3 / 10）。
 * upstream（backend）は fetch の stub で置き換える（実 LLM・実 backend は呼ばない）。
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";

function chatRequest(headers: Record<string, string> = {}): Request {
  return new Request("http://localhost:3000/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify({ message: "警報とは" }),
  });
}

const PRINCIPAL = { "x-ms-client-principal": "eyJhdXRoX3R5cCI6ImFhZCJ9" };

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("principal header 確認（決定 10。fail-closed）", () => {
  it("principal header を持たない request は 401 になり、upstream を呼ばない", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(chatRequest());
    expect(res.status).toBe(401);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("principal header が空文字列でも 401 になる", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(chatRequest({ "x-ms-client-principal": "" }));
    expect(res.status).toBe(401);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("無効化フラグ BFF_PRINCIPAL_CHECK_DISABLED=true のときだけ header なしで通す", async () => {
    vi.stubEnv("BFF_PRINCIPAL_CHECK_DISABLED", "true");
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(chatRequest());
    expect(res.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledOnce();
  });
});

describe("CHAT_API_KEY の server 側付与（決定 2）", () => {
  it("upstream へ x-api-key を付与し、client の送るヘッダに依存しない", async () => {
    vi.stubEnv("CHAT_API_KEY", "test-key-value");
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    await POST(chatRequest(PRINCIPAL));
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/chat");
    expect((init.headers as Record<string, string>)["x-api-key"]).toBe(
      "test-key-value",
    );
  });

  it("CHAT_API_KEY 未設定なら x-api-key ヘッダ自体を送らない", async () => {
    vi.stubEnv("CHAT_API_KEY", "");
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    await POST(chatRequest(PRINCIPAL));
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(init.headers as Record<string, string>).not.toHaveProperty(
      "x-api-key",
    );
  });
});

describe("BACKEND_ORIGIN（決定 3。実行時に読む）", () => {
  it("BACKEND_ORIGIN を実行時に読んで upstream URL を組み立てる", async () => {
    vi.stubEnv("BACKEND_ORIGIN", "http://backend.internal:8000");
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    await POST(chatRequest(PRINCIPAL));
    expect(fetchSpy.mock.calls[0][0]).toBe("http://backend.internal:8000/chat");
  });
});

describe("応答の中継", () => {
  it("SSE 応答を加工せず status / content-type ごと素通しする", async () => {
    const sse = 'event: done\ndata: {}\n\n';
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(sse, {
          status: 200,
          headers: { "content-type": "text/event-stream; charset=utf-8" },
        }),
      ),
    );

    const res = await POST(chatRequest(PRINCIPAL));
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe(
      "text/event-stream; charset=utf-8",
    );
    expect(await res.text()).toBe(sse);
  });

  it("ストリーム開始前の失敗の HTTP status を素通しする（ADR-0028 決定 2）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "unauthorized" }), {
          status: 401,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const res = await POST(chatRequest(PRINCIPAL));
    expect(res.status).toBe(401);
  });

  it("backend に接続できないときは 502 を返す", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("fetch failed")),
    );

    const res = await POST(chatRequest(PRINCIPAL));
    expect(res.status).toBe(502);
  });
});
