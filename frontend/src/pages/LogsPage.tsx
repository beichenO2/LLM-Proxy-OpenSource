import clsx from "clsx";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest, getErrorMessage } from "../lib/api";
import { inputClass, selectClass, thClass } from "../lib/styles";
import { useDebouncedValue } from "../lib/use-debounced-value";
import { useDocumentTitle } from "../lib/use-document-title";
import type { ILogListResponse } from "../types/api";
import PageHeader from "../components/PageHeader";
import { SkeletonTableRows } from "../components/Skeleton";

const LEVEL_OPTIONS = ["", "DEBUG", "INFO", "WARNING", "ERROR"] as const;

function levelLabel(v: (typeof LEVEL_OPTIONS)[number]): string {
  return v === "" ? "全部" : v;
}

function levelBadgeClass(level: string): string {
  switch (level.toUpperCase()) {
    case "ERROR":
      return "bg-red-100 text-red-800";
    case "WARNING":
      return "bg-amber-100 text-amber-800";
    case "INFO":
      return "bg-blue-100 text-blue-800";
    case "DEBUG":
      return "bg-neutral-100 text-neutral-600";
    default:
      return "bg-neutral-100 text-neutral-700";
  }
}

export default function LogsPage() {
  useDocumentTitle("日志");
  const [levelFilter, setLevelFilter] = useState<(typeof LEVEL_OPTIONS)[number]>("");
  const [sourceInput, setSourceInput] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const sourceFilter = useDebouncedValue(sourceInput);
  const searchQuery = useDebouncedValue(searchInput);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const logsQuery = useQuery({
    queryKey: ["logs", levelFilter, sourceFilter, searchQuery],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("limit", "300");
      if (levelFilter) params.set("level", levelFilter);
      if (sourceFilter.trim()) params.set("source", sourceFilter.trim());
      if (searchQuery.trim()) params.set("q", searchQuery.trim());
      return apiRequest<ILogListResponse>(`/api/logs?${params.toString()}`);
    },
    refetchInterval: autoRefresh ? 5000 : false,
  });

  const items = logsQuery.data?.items ?? [];

  return (
    <div className="p-8">
      <PageHeader
        title="日志"
        description="来自内存缓冲区的结构化应用日志（存储前已脱敏）。"
      />

      <div className="mt-6 flex flex-wrap items-end gap-4">
        <div>
          <label htmlFor="log-level" className="text-xs font-medium uppercase tracking-wide text-neutral-500">
            级别
          </label>
          <select
            id="log-level"
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value as (typeof LEVEL_OPTIONS)[number])}
            className={`mt-1 block ${selectClass}`}
          >
            {LEVEL_OPTIONS.map((v) => (
              <option key={v || "all"} value={v}>
                {levelLabel(v)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="log-source" className="text-xs font-medium uppercase tracking-wide text-neutral-500">
            来源包含
          </label>
          <input
            id="log-source"
            type="text"
            value={sourceInput}
            onChange={(e) => setSourceInput(e.target.value)}
            placeholder="例如 app.services"
            className={`mt-1 block w-56 ${inputClass}`}
          />
        </div>
        <div className="min-w-[200px] flex-1">
          <label htmlFor="log-search" className="text-xs font-medium uppercase tracking-wide text-neutral-500">
            搜索消息
          </label>
          <input
            id="log-search"
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="子串匹配"
            className={`mt-1 block w-full max-w-md ${inputClass}`}
          />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-neutral-800">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            className="rounded border-neutral-300 text-neutral-900 focus:ring-neutral-400"
          />
          自动刷新 (5s)
          {autoRefresh ? (
            <span className="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-500" aria-label="自动刷新已启用" />
          ) : null}
        </label>
      </div>

      {logsQuery.isError ? (
        <p role="alert" className="mt-8 text-sm text-red-600">
          {getErrorMessage(logsQuery.error, "加载日志失败")}
        </p>
      ) : null}

      {!logsQuery.isLoading && !logsQuery.isError && items.length > 0 ? (
        <p className="mt-8 text-xs text-neutral-500">共 {items.length} 条日志</p>
      ) : null}

      <div className={`${items.length > 0 ? "mt-2" : "mt-8"} overflow-x-auto rounded-lg border border-neutral-200`}>
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-neutral-200 bg-neutral-50">
            <tr>
              <th className={thClass}>时间</th>
              <th className={thClass}>级别</th>
              <th className={thClass}>来源</th>
              <th className={thClass}>消息</th>
            </tr>
          </thead>
          <tbody>
            {logsQuery.isLoading ? (
              <SkeletonTableRows cols={4} rows={5} />
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-neutral-500">
                  没有匹配当前筛选条件的日志。
                </td>
              </tr>
            ) : (
              items.map((row, i) => (
                <tr key={`${row.timestamp}-${row.source}-${i}`} className="border-b border-neutral-100 transition-colors hover:bg-neutral-50 last:border-0">
                  <td className="whitespace-nowrap px-3 py-2 text-neutral-600">{row.timestamp}</td>
                  <td className="px-3 py-2">
                    <span className={clsx("inline-flex rounded px-2 py-0.5 text-xs font-medium uppercase", levelBadgeClass(row.level))}>
                      {row.level}
                    </span>
                  </td>
                  <td className="max-w-[200px] truncate px-3 py-2 font-mono text-neutral-800" title={row.source}>
                    {row.source}
                  </td>
                  <td
                    className="max-w-xl truncate px-3 py-2 font-mono text-xs text-neutral-900"
                    title={row.message}
                  >
                    {row.message}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
