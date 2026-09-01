/**
 * Easy Auth principal header 確認（ADR-0027 決定 10 の深層防御）。
 *
 * Easy Auth sidecar が注入する認証済み principal header
 * （`X-MS-CLIENT-PRINCIPAL`）を持たない request を拒否する。ローカル開発向けの
 * 無効化フラグ `BFF_PRINCIPAL_CHECK_DISABLED=true` を持ち、既定は有効
 * （fail-closed）。
 *
 * 注意: sidecar 稼働時に外部 caller の同名 header 偽装が上書き・除去されるかは
 * 未検証の前提（ADR-0027）であり、この確認は決定 6 の apply 順序の代替ではない
 * （多層防御の 2 枚目）。
 */

const PRINCIPAL_HEADER = "x-ms-client-principal";

export function isPrincipalCheckPassed(request: Request): boolean {
  if (process.env.BFF_PRINCIPAL_CHECK_DISABLED === "true") {
    return true;
  }
  const principal = request.headers.get(PRINCIPAL_HEADER);
  return principal !== null && principal !== "";
}
