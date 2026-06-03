/**
 * Cross-service identity resolution via PolarPrivate identity_bindings API.
 *
 * @example
 * ```ts
 * import { resolveUser } from "@polarisor/privportal-sdk";
 * const user = await resolveUser("feishu", "ou_abc123");
 * // → { user_id: "...", username: "mac", service: "feishu", external_username: "ou_abc123" }
 * ```
 */

export interface ResolvedUser {
  user_id: string;
  username: string;
  service: string;
  external_username: string;
}

export interface IdentityBindingEntry {
  id: string;
  user_id: string;
  service: string;
  external_username: string;
  display_name: string | null;
  metadata_json: string | null;
  created_at: string;
  updated_at: string;
}

export interface IdentityBindingsListResponse {
  items: IdentityBindingEntry[];
  total: number;
}

function defaultBaseUrl(): string {
  const port = process.env.POLARPRIVATE_PORT ?? "12790";
  return `http://127.0.0.1:${port}`;
}

/**
 * Resolve an external service identity to a polarisor user_id.
 * Returns null if no binding exists.
 */
export async function resolveUser(
  service: string,
  externalUsername: string,
  baseUrl?: string,
): Promise<ResolvedUser | null> {
  const url = (baseUrl ?? defaultBaseUrl()).replace(/\/+$/, "");
  const params = new URLSearchParams({ service, external_username: externalUsername });
  const resp = await fetch(`${url}/api/identity-bindings/resolve?${params}`);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`resolveUser failed: ${resp.status} ${await resp.text()}`);
  return resp.json();
}

/**
 * List all identity bindings for a given polarisor user_id.
 */
export async function listUserBindings(
  userId: string,
  baseUrl?: string,
): Promise<IdentityBindingEntry[]> {
  const url = (baseUrl ?? defaultBaseUrl()).replace(/\/+$/, "");
  const resp = await fetch(`${url}/api/identity-bindings/user/${userId}`);
  if (!resp.ok) throw new Error(`listUserBindings failed: ${resp.status} ${await resp.text()}`);
  const data: IdentityBindingsListResponse = await resp.json();
  return data.items;
}

/**
 * Create a new identity binding.
 */
export async function createBinding(
  userId: string,
  service: string,
  externalUsername: string,
  displayName?: string,
  baseUrl?: string,
): Promise<IdentityBindingEntry> {
  const url = (baseUrl ?? defaultBaseUrl()).replace(/\/+$/, "");
  const body: Record<string, string> = {
    user_id: userId,
    service,
    external_username: externalUsername,
  };
  if (displayName) body.display_name = displayName;
  const resp = await fetch(`${url}/api/identity-bindings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`createBinding failed: ${resp.status} ${await resp.text()}`);
  return resp.json();
}
