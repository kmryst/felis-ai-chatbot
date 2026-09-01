/**
 * GET /readyz: backend `/readyz` への透過 proxy（ADR-0027 決定 8）。
 *
 * - パスは `/readyz`（`/api/readyz` にしない）。ADR-0026 の URL 契約
 *   （`https://<host>/readyz` のみ許可）と readyz-probe workflow の検証正規表現
 *   `^https://[^/]+/readyz$` に適合させる
 * - backend の status / body をそのまま返す（判定を加えない素通し）。
 *   backend に到達できない場合のみ 503 を返す
 */

export const dynamic = "force-dynamic";

const DEFAULT_BACKEND_ORIGIN = "http://localhost:8000";

export async function GET(): Promise<Response> {
  const backendOrigin = process.env.BACKEND_ORIGIN ?? DEFAULT_BACKEND_ORIGIN;
  let upstream: Response;
  try {
    upstream = await fetch(`${backendOrigin}/readyz`, { cache: "no-store" });
  } catch {
    return Response.json(
      { detail: "backend に接続できませんでした" },
      { status: 503 },
    );
  }
  const headers = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType !== null) {
    headers.set("content-type", contentType);
  }
  headers.set("cache-control", "no-store");
  return new Response(upstream.body, { status: upstream.status, headers });
}
