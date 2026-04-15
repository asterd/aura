import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { fetchPublicTenant } from "@/lib/tenant-auth";

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const error = url.searchParams.get("error");
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");

  const cookieStore = await cookies();
  const expectedState = cookieStore.get("aura_oidc_state")?.value;
  const codeVerifier = cookieStore.get("aura_oidc_verifier")?.value;
  const tenantSlug = cookieStore.get("aura_oidc_tenant")?.value;

  const clearTransientCookies = () => {
    cookieStore.delete("aura_oidc_state");
    cookieStore.delete("aura_oidc_verifier");
    cookieStore.delete("aura_oidc_tenant");
  };

  if (error || !tenantSlug) {
    clearTransientCookies();
    return NextResponse.redirect(new URL(`/tenant/${tenantSlug || ""}?error=oidc_callback_failed`, request.url));
  }
  if (!state || !expectedState || state !== expectedState || !codeVerifier || !code) {
    clearTransientCookies();
    return NextResponse.redirect(new URL(`/tenant/${tenantSlug}?error=oidc_state_mismatch`, request.url));
  }

  const tenant = await fetchPublicTenant(tenantSlug);
  if (!tenant || !tenant.okta_issuer || !process.env.AURA_OIDC_CLIENT_ID) {
    clearTransientCookies();
    return NextResponse.redirect(new URL(`/tenant/${tenantSlug}?error=oidc_not_configured`, request.url));
  }

  const redirectUri = new URL("/auth/oidc/callback", request.url).toString();
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri,
    client_id: process.env.AURA_OIDC_CLIENT_ID,
    code_verifier: codeVerifier,
  });

  const tokenResponse = await fetch(`${tenant.okta_issuer.replace(/\/$/, "")}/v1/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
    cache: "no-store",
  });
  if (!tokenResponse.ok) {
    clearTransientCookies();
    return NextResponse.redirect(new URL(`/tenant/${tenantSlug}?error=oidc_token_exchange_failed`, request.url));
  }

  const tokenPayload = (await tokenResponse.json()) as { access_token?: string; id_token?: string };
  const bearerToken = tokenPayload.access_token || tokenPayload.id_token;
  if (!bearerToken) {
    clearTransientCookies();
    return NextResponse.redirect(new URL(`/tenant/${tenantSlug}?error=oidc_token_missing`, request.url));
  }

  cookieStore.set("aura_token", bearerToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  cookieStore.set("aura_tenant_slug", tenant.slug, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  clearTransientCookies();

  return NextResponse.redirect(new URL("/chat", request.url));
}
