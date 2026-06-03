/**
 * LLM chat completion via PolarPrivate's /v1/ unified gateway.
 *
 * Callers only need a model name — PolarPrivate handles routing and auth.
 *
 * @example
 * ```ts
 * import { chatCompletion } from "privportal-sdk/llm";
 *
 * const reply = await chatCompletion("qwen3-coder-plus", [
 *   { role: "user", content: "Hello!" },
 * ]);
 *
 * // With options:
 * const reply2 = await chatCompletion("minimax", messages, {
 *   temperature: 0.3,
 *   maxTokens: 2048,
 * });
 * ```
 *
 * Port discovery: POLARPRIVATE_URL env → POLARPRIVATE_PORT env → default 12790.
 */

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatCompletionOptions {
  temperature?: number;
  maxTokens?: number;
  /** Request timeout in milliseconds (default 300_000) */
  timeoutMs?: number;
  /** Override base URL (default: auto-discovered PolarPrivate) */
  baseUrl?: string;
  /** Extra fields merged into the request body */
  extra?: Record<string, unknown>;
}

export interface ModelInfo {
  id: string;
  object: string;
  created: number;
  owned_by: string;
  service: string;
  description: string;
}

function getBaseUrl(override?: string): string {
  if (override) return override.replace(/\/$/, "");
  if (typeof process !== "undefined" && process.env) {
    if (process.env.POLARPRIVATE_URL)
      return process.env.POLARPRIVATE_URL.replace(/\/$/, "");
    const port = process.env.POLARPRIVATE_PORT || "12790";
    return `http://127.0.0.1:${port}`;
  }
  return "http://127.0.0.1:12790";
}

/**
 * Send a chat completion request to PolarPrivate's unified /v1/ gateway.
 * Returns the assistant's reply text.
 */
export async function chatCompletion(
  model: string,
  messages: ChatMessage[],
  opts: ChatCompletionOptions = {},
): Promise<string> {
  const base = getBaseUrl(opts.baseUrl);
  const url = `${base}/v1/chat/completions`;
  const timeoutMs = opts.timeoutMs ?? 300_000;

  const body: Record<string, unknown> = {
    model,
    messages,
    ...opts.extra,
  };
  if (opts.temperature !== undefined) body.temperature = opts.temperature;
  if (opts.maxTokens !== undefined) body.max_tokens = opts.maxTokens;

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`PolarPrivate LLM error ${res.status}: ${text.slice(0, 300)}`);
  }

  const data = (await res.json()) as {
    choices?: Array<{ message?: { content?: string } }>;
  };
  const content = data.choices?.[0]?.message?.content;
  if (!content) throw new Error("PolarPrivate LLM returned empty response");
  return content;
}

/**
 * Check if PolarPrivate is reachable and vault is unlocked.
 */
export async function isHealthy(baseUrl?: string): Promise<boolean> {
  try {
    const base = getBaseUrl(baseUrl);
    const res = await fetch(`${base}/health`, {
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { vault_unlocked?: boolean };
    return data.vault_unlocked === true;
  } catch {
    return false;
  }
}

/**
 * List available models from GET /v1/models.
 */
export async function listModels(baseUrl?: string): Promise<ModelInfo[]> {
  const base = getBaseUrl(baseUrl);
  const res = await fetch(`${base}/v1/models`, {
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    throw new Error(`Failed to list models: ${res.status}`);
  }
  const data = (await res.json()) as { data?: ModelInfo[] };
  return data.data ?? [];
}
