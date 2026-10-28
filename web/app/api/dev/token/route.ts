import { createHmac } from "node:crypto";
import { NextResponse } from "next/server";
import { DEV_SHELL_ENABLED } from "@/lib/dev-shell";

/**
 * Signs a dev-only HS256 JWT for the Atlan shell simulator. The API accepts
 * HS256 only when CONSTAT_ENV=dev, with the same shared secret.
 */
function b64url(input: Buffer | string): string {
  return Buffer.from(input).toString("base64url");
}

export async function GET(req: Request) {
  if (!DEV_SHELL_ENABLED) return NextResponse.json({ error: "not found", code: "NOT_FOUND" }, { status: 404 });
  const url = new URL(req.url);
  const email = url.searchParams.get("email") ?? "fde@atlan.com";
  const role = url.searchParams.get("role") ?? "reviewer";
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = b64url(
    JSON.stringify({
      iss: "atlan-dev-shell",
      aud: "constat",
      sub: `dev:${email}`,
      email,
      role,
      tenant: "dev-tenant",
      iat: now,
      exp: now + 3600,
    }),
  );
  const secret = process.env.CONSTAT_DEV_JWT_SECRET ?? "constat-dev-secret";
  const sig = b64url(createHmac("sha256", secret).update(`${header}.${payload}`).digest());
  return NextResponse.json({ token: `${header}.${payload}.${sig}`, expires_in: 3600 });
}
