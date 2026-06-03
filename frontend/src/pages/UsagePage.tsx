import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest } from "../lib/api";
import PageHeader from "../components/PageHeader";
import { SkeletonCard } from "../components/Skeleton";
import { useDocumentTitle } from "../lib/use-document-title";

interface UsageStats {
  period_days: number;
  total_requests: number;
  total_errors: number;
  by_service: Record<string, { requests: number; errors: number }>;
  daily: Record<string, number>;
}

function BarChart({ data, maxVal }: { data: [string, number][]; maxVal: number }) {
  if (!data.length) return <p className="text-sm text-neutral-400">暂无数据</p>;
  const last14 = data.slice(-14);
  return (
    <div className="flex items-end gap-1 h-32">
      {last14.map(([date, count]) => (
        <div key={date} className="flex flex-col items-center flex-1 min-w-0">
          <div
            className="w-full rounded-t bg-indigo-500 transition-all"
            style={{ height: `${Math.max(4, (count / (maxVal || 1)) * 100)}%` }}
            title={`${date}: ${count}`}
          />
          <span className="text-[9px] text-neutral-400 mt-1 truncate w-full text-center">
            {date.slice(5)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function UsagePage() {
  useDocumentTitle("用量看板");
  const [days, setDays] = useState(30);

  const { data, isLoading } = useQuery<UsageStats>({
    queryKey: ["proxy-usage", days],
    queryFn: () => apiRequest(`/proxy/usage/stats?days=${days}`),
    refetchInterval: 30_000,
  });

  const dailyEntries = data ? Object.entries(data.daily).sort() : [];
  const maxDaily = dailyEntries.reduce((m, [, v]) => Math.max(m, v), 0);
  const services = data ? Object.entries(data.by_service).sort((a, b) => b[1].requests - a[1].requests) : [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="用量看板"
        description="代理服务调用统计"
        action={
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-neutral-200 bg-white px-3 py-1.5 text-sm"
          >
            <option value={7}>近 7 天</option>
            <option value={30}>近 30 天</option>
            <option value={90}>近 90 天</option>
          </select>
        }
      />

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-3"><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>
      ) : data ? (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm">
              <p className="text-sm text-neutral-500">总请求数</p>
              <p className="mt-1 text-3xl font-bold text-neutral-900">{data.total_requests.toLocaleString()}</p>
            </div>
            <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm">
              <p className="text-sm text-neutral-500">错误数</p>
              <p className="mt-1 text-3xl font-bold text-red-600">{data.total_errors.toLocaleString()}</p>
            </div>
            <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm">
              <p className="text-sm text-neutral-500">成功率</p>
              <p className="mt-1 text-3xl font-bold text-green-600">
                {data.total_requests > 0
                  ? `${(((data.total_requests - data.total_errors) / data.total_requests) * 100).toFixed(1)}%`
                  : "N/A"}
              </p>
            </div>
          </div>

          <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-medium text-neutral-700 mb-4">每日请求量</h3>
            <BarChart data={dailyEntries} maxVal={maxDaily} />
          </div>

          <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-medium text-neutral-700 mb-4">按服务统计</h3>
            {services.length === 0 ? (
              <p className="text-sm text-neutral-400">暂无代理调用记录</p>
            ) : (
              <div className="space-y-3">
                {services.map(([name, stats]) => (
                  <div key={name} className="flex items-center gap-3">
                    <span className="text-sm font-mono text-neutral-600 w-48 truncate">{name}</span>
                    <div className="flex-1 h-5 bg-neutral-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full"
                        style={{ width: `${(stats.requests / (data.total_requests || 1)) * 100}%` }}
                      />
                    </div>
                    <span className="text-sm text-neutral-500 w-20 text-right">{stats.requests}</span>
                    {stats.errors > 0 && (
                      <span className="text-xs text-red-500">({stats.errors} err)</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
