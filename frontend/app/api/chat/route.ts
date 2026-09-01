/**
 * BFF: POST /api/chat（ADR-0027 決定 1 / 2 / 3 / 10）。
 *
 * - `CHAT_API_KEY` は本 Route Handler（server 側）だけが保持・付与する。
 *   client（ブラウザ）には一切配らない（決定 2。`NEXT_PUBLIC_` を使わない）
 * - upstream base URL は server 専用環境変数 `BACKEND_ORIGIN`（実行時に読む。
 *   ローカル開発の既定値 http://localhost:8000。決定 3）
 * - Easy Auth sidecar が注入する認証済み principal header
 *   （`X-MS-CLIENT-PRINCIPAL`）を持たない request には `CHAT_API_KEY` を付与せず
 *   401 を返す（決定 10 の深層防御）。ローカル開発向けの無効化フラグ
 *   `BFF_PRINCIPAL_CHECK_DISABLED=true` を持ち、既定は有効（fail-closed）
 * - backend の SSE 応答は加工せずそのまま stream で中継する。ストリーム開始前の
 *   失敗（401 / 404 / 422 / 502 / 503）は HTTP status ごと素通しする（ADR-0028 決定 2）
 */

import { isPrincipalCheckPassed } from "../../../lib/bff/principal";

export const dynamic = "force-dynamic";

const DEFAULT_BACKEND_ORIGIN = "http://localhost:8000";

function jsonResponse(status: number, detail: string): Response {
  return Response.json({ detail }, { status });
}

export async function POST(request: Request): Promise<Response> {
  if (!isPrincipalCheckPassed(request)) {
    // 認証済み principal を持たない request には key を付与しない（fail-closed）
    return jsonResponse(401, "認証されていないリクエストです");
  }

  const backendOrigin = process.env.BACKEND_ORIGIN ?? DEFAULT_BACKEND_ORIGIN;
  const apiKey = process.env.CHAT_API_KEY;

  let upstream: Response;
  try {
    upstream = await fetch(`${backendOrigin}/chat`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        // key 未設定時はヘッダ自体を送らない（backend 側が 401 を返す）
        ...(apiKey ? { "x-api-key": apiKey } : {}),
      },
      body: await request.text(),
      cache: "no-store",
      // client 切断を upstream へ伝播し、stream の垂れ流しを作らない
      signal: request.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    return jsonResponse(502, "backend に接続できませんでした");
  }

  const headers = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType !== null) {
    headers.set("content-type", contentType);
  }
  headers.set("cache-control", "no-store");
  return new Response(upstream.body, { status: upstream.status, headers });
}
