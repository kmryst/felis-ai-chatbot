/**
 * GET /readyz 透過 proxy のテスト（ADR-0027 決定 8）。
 * upstream（backend）は fetch の stub で置き換える。
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("GET /readyz", () => {
  it("backend /readyz の status / body を素通しする", async () => {
    const body = JSON.stringify({ status: "ok" });
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(body, {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET();
    expect(fetchSpy.mock.calls[0][0]).toBe("http://localhost:8000/readyz");
    expect(res.status).toBe(200);
    expect(await res.text()).toBe(body);
  });

  it("backend が 503 を返したら 503 のまま返す（判定を加えない）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: "stale" }), { status: 503 }),
      ),
    );

    const res = await GET();
    expect(res.status).toBe(503);
  });

  it("BACKEND_ORIGIN を実行時に読む（決定 3 と同じ server 専用変数）", async () => {
    vi.stubEnv("BACKEND_ORIGIN", "http://backend.internal:8000");
    const fetchSpy = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);

    await GET();
    expect(fetchSpy.mock.calls[0][0]).toBe(
      "http://backend.internal:8000/readyz",
    );
  });

  it("backend に接続できないときは 503 を返す", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("fetch failed")),
    );

    const res = await GET();
    expect(res.status).toBe(503);
  });
});
