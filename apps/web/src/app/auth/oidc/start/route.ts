import { createHash, randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { fetchPublicTenant } from "@/lib/tenant-auth";

function buildCodeChallenge(verifier: string): string {
  return createHash("sha256").update(verifier).digest("base64url");
}

export async function GET(request: NextRequest) {
  const tenantRef = request.nextUrl.searchParams.get("tenant");
  if (!tenantRef) {
    return NextResponse.redirect(new URL("/?error=tenant_not_found", request.url));
  }

  const tenant = await fetchPublicTenant(tenantRef);
  if (!tenant) {
    return NextResponse.redirect(new URL("/?error=tenant_not_found", request.url));
  }
  if (tenant.auth_mode !== "okta" || !tenant.okta_issuer || !process.env.AURA_OIDC_CLIENT_ID) {
    return NextResponse.redirect(new URL(`/tenant/${tenant.slug}?error=oidc_not_configured`, request.url));
  }

  const codeVerifier = randomBytes(32).toString("base64url");
  const state = randomBytes(24).toString("base64url");
  const nonce = randomBytes(24).toString("base64url");
  const redirectUri = new URL("/auth/oidc/callback", request.url).toString();
  const authorizeUrl = new URL(`${tenant.okta_issuer.replace(/\/$/, "")}/v1/authorize`);
  authorizeUrl.searchParams.set("client_id", process.env.AURA_OIDC_CLIENT_ID);
  authorizeUrl.searchParams.set("response_type", "code");
  authorizeUrl.searchParams.set("response_mode", "query");
  authorizeUrl.searchParams.set("scope", process.env.AURA_OIDC_SCOPES || "openid profile email");
  authorizeUrl.searchParams.set("redirect_uri", redirectUri);
  authorizeUrl.searchParams.set("state", state);
  authorizeUrl.searchParams.set("nonce", nonce);
  authorizeUrl.searchParams.set("code_challenge", buildCodeChallenge(codeVerifier));
  authorizeUrl.searchParams.set("code_challenge_method", "S256");

  const cookieStore = await cookies();
  cookieStore.set("aura_oidc_state", state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 10,
  });
  cookieStore.set("aura_oidc_verifier", codeVerifier, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 10,
  });
  cookieStore.set("aura_oidc_tenant", tenant.slug, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 10,
  });

  return NextResponse.redirect(authorizeUrl);
}
