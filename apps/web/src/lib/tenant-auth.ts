import type { PublicTenantInfo } from "./types";

const API_BASE_URL = process.env.AURA_API_BASE_URL || "http://localhost:8000";

export async function fetchPublicTenants(): Promise<PublicTenantInfo[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/public/tenants`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load tenants (${response.status})`);
  }
  return response.json() as Promise<PublicTenantInfo[]>;
}

export async function fetchPublicTenant(tenantRef: string): Promise<PublicTenantInfo | null> {
  const response = await fetch(`${API_BASE_URL}/api/v1/public/tenants/${encodeURIComponent(tenantRef)}`, { cache: "no-store" });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Failed to load tenant (${response.status})`);
  }
  return response.json() as Promise<PublicTenantInfo>;
}

export function getTenantErrorMessage(code: string | undefined): string | null {
  if (!code) return null;
  switch (code) {
    case "invalid_credentials":
      return "Invalid email or password for this tenant.";
    case "tenant_not_found":
      return "Tenant not found.";
    case "oidc_not_configured":
      return "SSO is not configured for this environment.";
    case "oidc_state_mismatch":
      return "SSO session expired. Start the sign-in flow again.";
    case "oidc_callback_failed":
      return "SSO callback failed.";
    case "oidc_token_exchange_failed":
      return "Could not complete the SSO token exchange.";
    case "oidc_token_missing":
      return "The identity provider did not return a usable token.";
    default:
      return "Authentication failed.";
  }
}
