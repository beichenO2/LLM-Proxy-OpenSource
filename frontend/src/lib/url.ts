/**
 * Build a paginated list API URL with optional project, search, and category filters.
 */
export function buildListUrl(
  basePath: string,
  opts: {
    projectId?: string | null;
    q?: string;
    category?: string;
    limit?: number;
  } = {},
): string {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 200));
  if (opts.projectId) params.set("project_id", opts.projectId);
  if (opts.q?.trim()) params.set("q", opts.q.trim());
  if (opts.category?.trim()) params.set("category", opts.category.trim());
  return `${basePath}?${params.toString()}`;
}
