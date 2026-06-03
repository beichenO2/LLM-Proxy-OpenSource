/**
 * 通过 Funnel 访问时，API 请求也需要带上 base path 前缀，
 * 因为 Tailscale Funnel 按前缀匹配路由。
 * 开发模式 BASE_URL="/"，API_BASE="" → Vite proxy 处理
 * 生产模式 BASE_URL="/12790_PolarPrivate/" → 前缀带上 → Funnel 匹配 → strip → 后端收到原始路径
 */
export const API_BASE =
  import.meta.env.VITE_API_BASE ??
  (import.meta.env.BASE_URL === "/" ? "" : import.meta.env.BASE_URL.replace(/\/+$/, ""));

export function getErrorMessage(err: unknown, fallback = "An error occurred"): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  return fallback;
}

function extractErrorMessage(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Record<string, unknown>;
  if (typeof d.detail === "string") return d.detail;
  if (d.detail && typeof d.detail === "object") {
    const inner = d.detail as Record<string, unknown>;
    if (typeof inner.detail === "string") return inner.detail;
  }
  return null;
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = response.statusText;
    let code: string | undefined;
    try {
      const data: unknown = await response.json();
      const extracted = extractErrorMessage(data);
      if (extracted) message = extracted;
      if (data && typeof data === "object") {
        const d = data as Record<string, unknown>;
        const detail = d.detail as Record<string, unknown> | undefined;
        code = (detail?.code ?? d.code) as string | undefined;
      }
    } catch {
      // keep statusText
    }
    if (response.status === 401 && code === "SESSION_EXPIRED") {
      window.dispatchEvent(new CustomEvent("pp:session-expired"));
    }
    if (response.status === 403 && code === "FULL_SESSION_REQUIRED") {
      window.dispatchEvent(new CustomEvent("pp:session-expired"));
    }
    throw new Error(message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  if (!text.trim()) {
    return undefined as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(`Invalid JSON response from ${path}`);
  }
}
