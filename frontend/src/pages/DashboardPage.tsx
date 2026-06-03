import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiRequest } from "../lib/api";
import { ICON_PATHS } from "../lib/icons";
import { thClass } from "../lib/styles";
import { showApiError, toast } from "../lib/toast";
import { useDocumentTitle } from "../lib/use-document-title";
import { useUiStore } from "../stores/uiStore";
import type { IAuditListResponse, IDashboardSummary, IRecentEntriesResponse, IRecentEntryOut, IRecentProjectsResponse } from "../types/api";
import PageHeader from "../components/PageHeader";
import { SkeletonCard, SkeletonTableRows } from "../components/Skeleton";

function withProjectParams(
  path: string,
  baseParams: Record<string, string>,
  projectId: string | null,
): string {
  const params = new URLSearchParams(baseParams);
  if (projectId) params.set("project_id", projectId);
  const q = params.toString();
  return q ? `${path}?${q}` : path;
}

interface IStatCardProps {
  label: string;
  value: number | string;
  isLoading: boolean;
  icon: ReactNode;
  accentClass: string;
  to: string;
}

function StatCard({ label, value, isLoading, icon, accentClass, to }: IStatCardProps) {
  return (
    <Link
      to={to}
      className="flex items-center gap-4 rounded-xl border border-neutral-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md"
    >
      <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${accentClass}`}>
        {icon}
      </div>
      <div>
        <div className="text-sm font-medium text-neutral-500">{label}</div>
        <div className="mt-0.5 font-mono text-2xl font-semibold text-neutral-900">
          {isLoading ? "—" : value}
        </div>
      </div>
    </Link>
  );
}

function SvgIcon({ d, className }: { d: string; className?: string }) {
  return (
    <svg className={className ?? "h-5 w-5"} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

function IdentitySecurityBadge() {
  const [show, setShow] = useState(false);
  return (
    <span className="relative ml-1 inline-flex">
      <button
        type="button"
        className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-blue-100 text-[9px] font-bold text-blue-600 hover:bg-blue-200"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onFocus={() => setShow(true)}
        onBlur={() => setShow(false)}
        onClick={() => setShow((v) => !v)}
        aria-label="安全说明"
      >
        ?
      </button>
      {show && (
        <div className="absolute bottom-full left-1/2 z-50 mb-1.5 w-56 -translate-x-1/2 rounded-lg border border-neutral-200 bg-white p-2.5 text-[11px] leading-relaxed text-neutral-600 shadow-lg">
          <div className="font-semibold text-blue-600 mb-1">安全说明</div>
          <p>此值仅在本地 UI 明文显示。</p>
          <p className="mt-1">磁盘加密存储 · LLM 端变量名传输 · 发回飞书最后一步才解密</p>
          <p className="mt-1 text-neutral-400">您的隐私不会泄露。</p>
        </div>
      )}
    </span>
  );
}

function InlineEditCell({ entry }: { entry: IRecentEntryOut }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const patchMutation = useMutation({
    mutationFn: (value: string) => {
      const endpoint = entry.type === "identity"
        ? `/api/identities/${entry.id}`
        : `/api/secrets/${entry.id}`;
      return apiRequest(endpoint, {
        method: "PATCH",
        body: JSON.stringify({ value }),
      });
    },
    onSuccess: () => {
      toast.success(`${entry.key} 已保存`);
      setEditing(false);
      void queryClient.invalidateQueries({ queryKey: ["recent-entries"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
    onError: (err) => {
      showApiError(err);
    },
  });

  const startEditing = () => {
    setDraft(entry.value ?? "");
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const save = () => {
    const trimmed = draft.trim();
    if (!trimmed) {
      setEditing(false);
      return;
    }
    if (trimmed === (entry.value ?? "")) {
      setEditing(false);
      return;
    }
    patchMutation.mutate(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      save();
    } else if (e.key === "Escape") {
      setEditing(false);
    }
  };

  if (editing) {
    return (
      <div className="flex items-center gap-1">
        <input
          ref={inputRef}
          type={entry.type === "secret" ? "password" : "text"}
          className="w-full rounded border border-blue-300 bg-white px-1.5 py-0.5 font-mono text-xs text-neutral-900 outline-none focus:ring-1 focus:ring-blue-400"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={save}
          onKeyDown={handleKeyDown}
          disabled={patchMutation.isPending}
          placeholder="输入值后回车保存"
        />
        {patchMutation.isPending && (
          <span className="shrink-0 text-[10px] text-neutral-400">保存中…</span>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {entry.has_value ? (
        <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">
          已填写
        </span>
      ) : (
        <button
          type="button"
          className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-600 hover:bg-amber-100"
          onClick={startEditing}
          title="点击填写"
        >
          待填写
          <svg className="ml-1 h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
          </svg>
        </button>
      )}
      {entry.has_value && (
        <button
          type="button"
          className="text-neutral-400 hover:text-blue-600"
          onClick={startEditing}
          title="点击修改"
        >
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
          </svg>
        </button>
      )}
      {entry.type === "identity" && <IdentitySecurityBadge />}
    </div>
  );
}

const moduleLinks: { to: string; label: string; description: string; iconPath: string }[] = [
  { to: "/identities", label: "身份信息", description: "管理文档级别的个人身份信息", iconPath: ICON_PATHS.identities },
  { to: "/secrets", label: "加密密钥", description: "API 密钥、令牌和密码", iconPath: ICON_PATHS.secrets },
  { to: "/bindings", label: "绑定关系", description: "将服务映射到密钥引用", iconPath: ICON_PATHS.bindings },
  { to: "/services", label: "自有服务", description: "代理服务状态和连通性测试", iconPath: ICON_PATHS.services },
  { to: "/test-center", label: "测试中心", description: "运行自动化检查", iconPath: ICON_PATHS.testCenter },
  { to: "/settings", label: "设置", description: "端口、偏好设置、主密码", iconPath: ICON_PATHS.settings },
  { to: "/logs", label: "日志", description: "结构化应用日志", iconPath: ICON_PATHS.logs },
];

export default function DashboardPage() {
  useDocumentTitle("仪表盘");
  const navigate = useNavigate();
  const activeProjectId = useUiStore((s) => s.activeProjectId);
  const setActiveProjectId = useUiStore((s) => s.setActiveProjectId);

  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary", activeProjectId],
    queryFn: () =>
      apiRequest<IDashboardSummary>(
        withProjectParams("/api/dashboard/summary", {}, activeProjectId),
      ),
  });

  const recentQuery = useQuery({
    queryKey: ["recent-projects"],
    queryFn: () => apiRequest<IRecentProjectsResponse>("/api/dashboard/recent-projects"),
  });

  const recentEntriesQuery = useQuery({
    queryKey: ["recent-entries"],
    queryFn: () => apiRequest<IRecentEntriesResponse>("/api/dashboard/recent-entries"),
    refetchInterval: 30_000,
  });

  const auditQuery = useQuery({
    queryKey: ["audit-log", activeProjectId],
    queryFn: () =>
      apiRequest<IAuditListResponse>(
        withProjectParams("/api/audit-log", { limit: "10" }, activeProjectId),
      ),
  });

  const s = summaryQuery.data;
  const recentProjects = recentQuery.data?.items ?? [];
  const items = auditQuery.data?.items ?? [];

  return (
    <div className="p-8">
      <PageHeader
        title="仪表盘"
        description="保险库概览和所有模块的快速入口。"
      />

      <section className="mt-8">
        {summaryQuery.isError ? (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <span className="font-medium">加载摘要失败</span> — {summaryQuery.error?.message ?? "请检查后端服务"}
            <button type="button" className="ml-3 underline hover:no-underline" onClick={() => void summaryQuery.refetch()}>重试</button>
          </div>
        ) : summaryQuery.isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard
            label="身份信息"
            value={s?.identity_count ?? "—"}
            isLoading={summaryQuery.isLoading}
            accentClass="bg-blue-50 text-blue-600"
            icon={<SvgIcon d={ICON_PATHS.identities} />}
            to="/identities"
          />
          <StatCard
            label="加密密钥"
            value={s?.secret_count ?? "—"}
            isLoading={summaryQuery.isLoading}
            accentClass="bg-amber-50 text-amber-600"
            icon={<SvgIcon d={ICON_PATHS.secrets} />}
            to="/secrets"
          />
          <StatCard
            label="绑定关系"
            value={s?.binding_count ?? "—"}
            isLoading={summaryQuery.isLoading}
            accentClass="bg-emerald-50 text-emerald-600"
            icon={<SvgIcon d={ICON_PATHS.bindings} />}
            to="/bindings"
          />
        </div>
        )}
      </section>

      {/* ─── Recent Entries (新十条 & 最近上新) ──────────────── */}
      <section className="mt-10">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium uppercase tracking-wide text-neutral-500">
            最近条目
          </h2>
          <span className="text-[11px] text-neutral-400">
            最新 10 条 + 最近 1 小时新增
          </span>
        </div>
        {recentEntriesQuery.isError ? (
          <div role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <span className="font-medium">加载最近条目失败</span>
            <button type="button" className="ml-3 underline hover:no-underline" onClick={() => void recentEntriesQuery.refetch()}>重试</button>
          </div>
        ) : recentEntriesQuery.isLoading ? (
          <div className="mt-3 space-y-2">
            <SkeletonCard /><SkeletonCard />
          </div>
        ) : (recentEntriesQuery.data?.items?.length ?? 0) === 0 ? (
          <p className="mt-3 text-sm text-neutral-400">暂无新条目。Agent 添加的密钥会在这里出现。</p>
        ) : (
          <div className="mt-3 overflow-x-auto rounded-lg border border-neutral-200">
            <table className="w-full min-w-[480px] text-left text-sm">
              <thead className="border-b border-neutral-200 bg-neutral-50">
                <tr>
                  <th className={thClass}>类型</th>
                  <th className={thClass}>Key</th>
                  <th className={thClass}>值状态</th>
                  <th className={thClass}>时间</th>
                </tr>
              </thead>
              <tbody>
                {(recentEntriesQuery.data?.items ?? []).map((entry) => {
                  const isNew = Date.now() - new Date(entry.created_at).getTime() < 3600000;
                  return (
                    <tr key={entry.id} className="border-b border-neutral-100 transition-colors hover:bg-neutral-50 last:border-0">
                      <td className="px-3 py-2">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                          entry.type === "identity"
                            ? "bg-blue-50 text-blue-600"
                            : "bg-amber-50 text-amber-600"
                        }`}>
                          {entry.type === "identity" ? "身份" : "密钥"}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          to={entry.type === "identity" ? "/identities" : "/secrets"}
                          className="font-mono text-neutral-900 hover:text-blue-600"
                        >
                          {entry.key}
                        </Link>
                        {isNew && (
                          <span className="ml-2 inline-block rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-600">
                            新
                          </span>
                        )}
                      </td>
                      <td className="max-w-[240px] px-3 py-2">
                        <InlineEditCell entry={entry} />
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-neutral-500 text-xs">
                        {new Date(entry.created_at).toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ─── New / Recent Projects ──────────────────────────── */}
      <section className="mt-10">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium uppercase tracking-wide text-neutral-500">
            新增和近期项目
          </h2>
          <Link to="/projects" className="text-xs font-medium text-neutral-500 hover:text-neutral-700">
            查看全部 →
          </Link>
        </div>
        {recentQuery.isError ? (
          <div role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <span className="font-medium">加载项目列表失败</span>
            <button type="button" className="ml-3 underline hover:no-underline" onClick={() => void recentQuery.refetch()}>重试</button>
          </div>
        ) : recentQuery.isLoading ? (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : recentProjects.length === 0 ? (
          <p className="mt-3 text-sm text-neutral-400">暂无项目。创建一个项目即可开始。</p>
        ) : (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {recentProjects.map((proj) => {
              const isNew = Date.now() - new Date(proj.created_at).getTime() < 3600000;
              return (
                <button
                  key={proj.id}
                  type="button"
                  onClick={() => {
                    setActiveProjectId(proj.id);
                    navigate("/secrets");
                  }}
                  className="group relative rounded-xl border border-neutral-200 bg-white p-4 text-left shadow-sm transition-all hover:border-neutral-300 hover:shadow-md"
                >
                  {isNew && (
                    <span className="absolute right-3 top-3 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">
                      新
                    </span>
                  )}
                  <div className="font-medium text-neutral-900 group-hover:text-neutral-700">
                    {proj.name}
                  </div>
                  {proj.description && (
                    <div className="mt-1 line-clamp-2 text-xs text-neutral-500">
                      {proj.description}
                    </div>
                  )}
                  <div className="mt-2 text-[11px] text-neutral-400">
                    {new Date(proj.created_at).toLocaleDateString()}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-medium uppercase tracking-wide text-neutral-500">
          近期活动
        </h2>
        <div className="mt-3 overflow-x-auto rounded-lg border border-neutral-200">
          <table className="w-full min-w-[480px] text-left text-sm">
            <thead className="border-b border-neutral-200 bg-neutral-50">
              <tr>
                <th className={thClass}>操作</th>
                <th className={thClass}>详情</th>
                <th className={thClass}>时间</th>
              </tr>
            </thead>
            <tbody>
              {auditQuery.isError ? (
                <tr>
                  <td colSpan={3} className="px-3 py-6 text-center text-red-600">
                    加载审计日志失败 —
                    <button type="button" className="ml-2 underline hover:no-underline" onClick={() => void auditQuery.refetch()}>重试</button>
                  </td>
                </tr>
              ) : auditQuery.isLoading ? (
                <SkeletonTableRows cols={3} rows={3} />
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-3 py-6 text-center text-neutral-500">
                    暂无近期活动。
                  </td>
                </tr>
              ) : (
                items.map((row) => (
                  <tr key={row.id} className="border-b border-neutral-100 transition-colors hover:bg-neutral-50 last:border-0">
                    <td className="px-3 py-2 font-mono text-neutral-900">{row.action}</td>
                    <td className="px-3 py-2 text-neutral-700">{row.detail ?? "\u2014"}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-neutral-600">
                      {new Date(row.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-medium uppercase tracking-wide text-neutral-500">功能模块</h2>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {moduleLinks.map(({ to, label, description, iconPath }) => (
            <Link
              key={to}
              to={to}
              className="group flex items-start gap-3 rounded-xl border border-neutral-200 bg-white p-4 shadow-sm transition-all hover:border-neutral-300 hover:shadow-md"
            >
              <SvgIcon d={iconPath} className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400 group-hover:text-neutral-600" />
              <div className="min-w-0">
                <div className="font-medium text-neutral-900 group-hover:text-neutral-700">{label}</div>
                <div className="mt-1 text-xs text-neutral-500">{description}</div>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
