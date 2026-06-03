import clsx from "clsx";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { apiRequest } from "../lib/api";
import { btnPrimaryClass, thClass } from "../lib/styles";
import { useDocumentTitle } from "../lib/use-document-title";
import type { IRunResponse, ITestResultRow, ILLMStatusResponse } from "../types/api";
import PageHeader from "../components/PageHeader";
import { SkeletonTableRows } from "../components/Skeleton";

type TestType = "all" | "llm_connectivity" | "sign_providers" | "d_class";

function statusBadgeClass(status: ITestResultRow["status"]): string {
  switch (status) {
    case "pass":
      return "bg-green-100 text-green-800";
    case "fail":
      return "bg-red-100 text-red-800";
    case "skip":
      return "bg-neutral-200 text-neutral-600";
    default:
      return "bg-neutral-100 text-neutral-700";
  }
}

function llmStatusBadgeClass(status: string | null): string {
  if (status === "success") return "bg-green-100 text-green-800";
  if (status === "error") return "bg-red-100 text-red-800";
  return "bg-neutral-200 text-neutral-600";
}

function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return "从未";
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffMins < 1) return "刚刚";
  if (diffMins < 60) return `${diffMins} 分钟前`;
  if (diffHours < 24) return `${diffHours} 小时前`;
  return `${diffDays} 天前`;
}

export default function TestCenterPage() {
  useDocumentTitle("测试中心");
  const resultsRef = useRef<HTMLDivElement>(null);
  const [testType, setTestType] = useState<TestType>("all");

  const mutation = useMutation({
    mutationFn: () =>
      apiRequest<IRunResponse>("/api/test-center/run", {
        method: "POST",
        body: JSON.stringify({ test_type: testType }),
      }),
    onError: (e: Error) => {
      toast.error(e.message);
    },
  });

  const llmStatusQuery = useQuery<ILLMStatusResponse>({
    queryKey: ["llm-status"],
    queryFn: () => apiRequest<ILLMStatusResponse>("/api/test-center/llm-status"),
    refetchInterval: 30000,
  });

  const results = mutation.data?.results ?? [];

  useEffect(() => {
    if (mutation.isSuccess && results.length > 0) {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [mutation.isSuccess, results.length]);

  return (
    <div className="p-8">
      <PageHeader
        title="测试中心"
        description="测试 LLM 服务、签名服务（weex 等）、D-class 服务（tqsdk 等）的连通性。"
        action={
          <div className="flex items-center gap-3">
            <select
              value={testType}
              onChange={(e) => setTestType(e.target.value as TestType)}
              className="rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="all">全部测试</option>
              <option value="llm_connectivity">LLM 服务</option>
              <option value="sign_providers">签名服务</option>
              <option value="d_class">D-class 服务</option>
            </select>
            <button
              type="button"
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className={btnPrimaryClass}
            >
              {mutation.isPending ? "测试中…" : "运行测试"}
            </button>
          </div>
        }
      />

      {/* LLM Service Status Cards */}
      <div className="mt-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-neutral-900">LLM 服务状态</h2>
          <button
            type="button"
            onClick={() => llmStatusQuery.refetch()}
            className="text-sm text-neutral-500 hover:text-neutral-700"
          >
            刷新
          </button>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {llmStatusQuery.isLoading ? (
            <div className="col-span-full rounded-lg border border-neutral-200 p-4 text-center text-neutral-500">
              加载中...
            </div>
          ) : llmStatusQuery.data?.services ? (
            llmStatusQuery.data.services.map((svc) => (
              <div
                key={svc.service_name}
                className="rounded-lg border border-neutral-200 bg-white p-4 shadow-sm"
              >
                <div className="flex items-start justify-between">
                  <div className="font-mono text-sm font-medium text-neutral-900">
                    {svc.service_name}
                  </div>
                  <span
                    className={clsx(
                      "inline-flex rounded px-2 py-0.5 text-xs font-medium uppercase",
                      llmStatusBadgeClass(svc.last_call_status)
                    )}
                  >
                    {svc.last_call_status || "未知"}
                  </span>
                </div>
                <div className="mt-2 space-y-1 text-xs text-neutral-600">
                  <div className="flex justify-between">
                    <span>最近调用</span>
                    <span className="font-mono">{formatRelativeTime(svc.last_call_at)}</span>
                  </div>
                  {svc.last_call_latency_ms !== null && (
                    <div className="flex justify-between">
                      <span>延迟</span>
                      <span className="font-mono">{svc.last_call_latency_ms}ms</span>
                    </div>
                  )}
                  {svc.consecutive_failures > 0 && (
                    <div className="flex justify-between text-red-600">
                      <span>连续失败</span>
                      <span className="font-mono">{svc.consecutive_failures}次</span>
                    </div>
                  )}
                  {svc.last_call_error && (
                    <div className="mt-2 truncate text-red-600" title={svc.last_call_error}>
                      {svc.last_call_error}
                    </div>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="col-span-full rounded-lg border border-neutral-200 p-4 text-center text-neutral-500">
              暂无 LLM 服务状态
            </div>
          )}
        </div>
      </div>

      {/* Test Results Table */}
      <div className="mt-8">
        <h2 className="text-lg font-semibold text-neutral-900">连通性测试结果</h2>
        {mutation.isSuccess && results.length > 0 ? (
          <p className="mt-2 text-xs text-neutral-500">共 {results.length} 条结果</p>
        ) : null}
      </div>

      <div ref={resultsRef} className={`${results.length > 0 ? "mt-2" : "mt-4"} scroll-mt-8 overflow-x-auto rounded-lg border border-neutral-200`}>
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-neutral-200 bg-neutral-50">
            <tr>
              <th className={thClass}>服务名称</th>
              <th className={thClass}>状态</th>
              <th className={thClass}>消息</th>
              <th className={thClass}>耗时 (ms)</th>
            </tr>
          </thead>
          <tbody>
            {mutation.isPending ? (
              <SkeletonTableRows cols={4} rows={3} />
            ) : mutation.isIdle && !mutation.isSuccess ? (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-neutral-500">
                  点击「运行测试」查看服务配置状态。
                </td>
              </tr>
            ) : results.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-neutral-500">
                  未返回任何结果。
                </td>
              </tr>
            ) : (
              results.map((row, i) => (
                <tr key={`${row.name}-${i}`} className="border-b border-neutral-100 transition-colors hover:bg-neutral-50 last:border-0">
                  <td className="px-3 py-2 font-mono text-neutral-900">{row.name}</td>
                  <td className="px-3 py-2">
                    <span
                      className={clsx("inline-flex rounded px-2 py-0.5 text-xs font-medium uppercase", statusBadgeClass(row.status))}
                    >
                      {row.status}
                    </span>
                  </td>
                  <td className="max-w-md px-3 py-2 text-neutral-700" title={row.message}>
                    {row.message}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-neutral-800">
                    {row.duration_ms}
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
