import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../lib/api";
import { ICON_PATHS } from "../lib/icons";
import { useUiStore } from "../stores/uiStore";
import type { IProjectListResponse } from "../types/api";

export default function ProjectSelect() {
  const activeProjectId = useUiStore((s) => s.activeProjectId);
  const setActiveProjectId = useUiStore((s) => s.setActiveProjectId);

  const { data } = useQuery({
    queryKey: ["projects"],
    queryFn: () => apiRequest<IProjectListResponse>("/api/projects?limit=200"),
  });

  const items = data?.items ?? [];

  return (
    <div className="flex items-center gap-2">
      <svg
        className="h-4 w-4 shrink-0 text-neutral-400"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d={ICON_PATHS.projects} />
      </svg>
      <select
        className="max-w-[220px] rounded-md border border-neutral-200 bg-neutral-50 px-2.5 py-1.5 text-sm text-neutral-900 outline-none ring-neutral-400 transition-colors hover:border-neutral-300 hover:bg-neutral-100 focus:ring-2"
        value={activeProjectId ?? ""}
        onChange={(e) => {
          const v = e.target.value;
          setActiveProjectId(v === "" ? null : v);
        }}
        aria-label="当前项目"
      >
        <option value="">全部项目</option>
        {items.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </div>
  );
}
