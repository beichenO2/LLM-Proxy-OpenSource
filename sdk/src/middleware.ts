/**
 * PolarPrivate TypeScript SDK — sanitize/resolve middleware.
 *
 * Mirrors the Python `privportal-sdk` API. Loads identity mappings from
 * PolarPrivate once, then performs pure in-memory string replacement.
 *
 * @example
 * ```ts
 * const mw = new PrivPortalMiddleware("http://127.0.0.1:12790");
 * await mw.loadMappings();
 * const safe = mw.sanitize("你好，我是张三");     // → "你好，我是[[identity.student.name]]"
 * const real = mw.resolve("[[identity.student.name]] 你好"); // → "张三你好"
 * ```
 */

export interface IdentityMapping {
  key: string;
  value: string;
  project_id: string | null;
}

export interface SecretMapping {
  key: string;
  project_id: string | null;
}

export interface MappingsResponse {
  identities: IdentityMapping[];
  secrets: SecretMapping[];
  version: string;
}

export interface LeakInfo {
  key: string;
  value: string;
  position: number;
}

export interface PrivPortalOptions {
  baseUrl?: string;
  projectId?: string | null;
  autoLoad?: boolean;
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export class PrivPortalMiddleware {
  private _baseUrl: string;
  private _projectId: string | null;
  private _identities: IdentityMapping[] = [];
  private _secrets: SecretMapping[] = [];
  private _valueToPlaceholder = new Map<string, string>();
  private _placeholderToValue = new Map<string, string>();
  private _sanitizePattern: RegExp | null = null;
  private _loaded = false;

  constructor(options: PrivPortalOptions | string = {}) {
    if (typeof options === "string") {
      options = { baseUrl: options };
    }
    this._baseUrl = (options.baseUrl ?? "http://127.0.0.1:12790").replace(
      /\/+$/,
      ""
    );
    this._projectId = options.projectId ?? null;
  }

  get isLoaded(): boolean {
    return this._loaded;
  }

  get identityCount(): number {
    return this._identities.length;
  }

  get secretCount(): number {
    return this._secrets.length;
  }

  /**
   * Fetch mappings from PolarPrivate API and build lookup tables.
   * The /api/sanitize/mappings endpoint requires no authentication
   * (any localhost caller can use it).
   */
  async loadMappings(timeout = 5000): Promise<void> {
    const url = new URL(`${this._baseUrl}/api/sanitize/mappings`);
    if (this._projectId) {
      url.searchParams.set("project_id", this._projectId);
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const resp = await fetch(url.toString(), {
        signal: controller.signal,
      });
      if (!resp.ok) {
        throw new Error(
          `PolarPrivate API returned ${resp.status}: ${resp.statusText}`
        );
      }
      const data = (await resp.json()) as MappingsResponse;
      this._rebuild(data);
    } finally {
      clearTimeout(timer);
    }
  }

  /**
   * Load mappings from a raw object (useful for testing without a running server).
   */
  loadFromObject(data: MappingsResponse): void {
    this._rebuild(data);
  }

  private _rebuild(data: MappingsResponse): void {
    this._identities = data.identities ?? [];
    this._secrets = data.secrets ?? [];

    this._valueToPlaceholder.clear();
    this._placeholderToValue.clear();

    const sorted = [...this._identities].sort(
      (a, b) => b.value.length - a.value.length
    );

    for (const entry of sorted) {
      if (!entry.value) continue;
      const placeholder = `[[${entry.key}]]`;
      this._valueToPlaceholder.set(entry.value, placeholder);
      this._placeholderToValue.set(placeholder, entry.value);
    }

    if (this._valueToPlaceholder.size > 0) {
      const escaped = [...this._valueToPlaceholder.keys()].map(escapeRegex);
      this._sanitizePattern = new RegExp(escaped.join("|"), "g");
    } else {
      this._sanitizePattern = null;
    }

    this._loaded = true;
  }

  /**
   * Replace known identity values with their placeholders.
   * This is the INBOUND path (user message → LLM).
   */
  sanitize(text: string): string {
    if (!this._loaded || !this._sanitizePattern) return text;
    this._sanitizePattern.lastIndex = 0;
    return text.replace(this._sanitizePattern, (match) => {
      return this._valueToPlaceholder.get(match) ?? match;
    });
  }

  /**
   * Replace placeholders with real identity values.
   * This is the OUTBOUND path (LLM reply → user).
   */
  resolve(text: string): string {
    if (!this._loaded || this._placeholderToValue.size === 0) return text;
    let result = text;
    for (const [placeholder, value] of this._placeholderToValue) {
      result = result.replaceAll(placeholder, value);
    }
    return result;
  }

  /**
   * Check if text contains any known identity values (leak detection).
   * Returns a list of detected leaks with key and matched value.
   */
  detectLeaks(text: string): LeakInfo[] {
    if (!this._loaded || !this._sanitizePattern) return [];
    this._sanitizePattern.lastIndex = 0;
    const leaks: LeakInfo[] = [];
    let match: RegExpExecArray | null;
    while ((match = this._sanitizePattern.exec(text)) !== null) {
      const value = match[0];
      const placeholder = this._valueToPlaceholder.get(value);
      if (placeholder) {
        leaks.push({
          key: placeholder.slice(2, -2),
          value,
          position: match.index,
        });
      }
    }
    return leaks;
  }

  toString(): string {
    return `PrivPortalMiddleware(baseUrl=${this._baseUrl}, loaded=${this._loaded}, identities=${this.identityCount}, secrets=${this.secretCount})`;
  }
}
