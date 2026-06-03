import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../lib/api";
import { ICON_PATHS } from "../lib/icons";
import { useDocumentTitle } from "../lib/use-document-title";
import PageHeader from "../components/PageHeader";
import { Skeleton } from "../components/Skeleton";

interface IHealthResponse {
  status: string;
  version?: string;
}

function SvgIcon({ d }: { d: string }) {
  return (
    <svg className="h-5 w-5 text-neutral-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

const FEATURES = [
  { icon: ICON_PATHS.identities, label: "身份保险库", desc: "管理文档级 PII（姓名、邮箱、学号等），支持占位符替换。" },
  { icon: ICON_PATHS.secrets, label: "密钥保险库", desc: "使用 Fernet 加密存储 API 密钥、令牌和密码。" },
  { icon: ICON_PATHS.bindings, label: "服务绑定", desc: "将上游服务映射到密钥引用，实现自动请求头注入。" },
  { icon: ICON_PATHS.template, label: "模板引擎", desc: "使用 [[占位符]] 语法实时预览和导出身份值。" },
  { icon: ICON_PATHS.testCenter, label: "连通性测试", desc: "在部署前验证绑定密钥的服务是否可达。" },
];

const KEYBOARD_SHORTCUTS = [
  { keys: "⌘K", desc: "快速导航" },
  { keys: "⌘B", desc: "切换侧边栏" },
  { keys: "Esc", desc: "关闭弹窗 / 命令面板" },
];

export default function AboutPage() {
  useDocumentTitle("关于");

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: () => apiRequest<IHealthResponse>("/api/health"),
    retry: false,
  });

  return (
    <div className="p-8">
      <PageHeader
        title="关于 PolarPrivate"
        description="本地隐私代理与脱敏门户 — 将敏感数据隔离在 AI 工作流之外。"
      />

      <div className="mt-8 max-w-3xl space-y-8">
        <section className="rounded-lg border border-neutral-200 bg-white p-6">
          <h2 className="text-lg font-semibold text-neutral-900">系统信息</h2>
          <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
            <dt className="font-medium text-neutral-500">版本</dt>
            <dd className="font-mono text-neutral-900">
              {healthQuery.isLoading ? <Skeleton className="h-4 w-20" /> : healthQuery.data?.version ?? "—"}
            </dd>
            <dt className="font-medium text-neutral-500">状态</dt>
            <dd className="font-mono text-neutral-900">
              {healthQuery.isLoading ? (
                <Skeleton className="h-4 w-16" />
              ) : healthQuery.data?.status === "ok" ? (
                <span className="inline-flex items-center gap-1.5 text-emerald-700">
                  <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
                  运行中
                </span>
              ) : (
                "未知"
              )}
            </dd>
            <dt className="font-medium text-neutral-500">运行时</dt>
            <dd className="text-neutral-900">Python + FastAPI + SQLite（仅本地）</dd>
            <dt className="font-medium text-neutral-500">前端</dt>
            <dd className="text-neutral-900">React + TypeScript + Vite + Tailwind</dd>
          </dl>
        </section>

        <section className="rounded-lg border border-neutral-200 bg-white p-6">
          <h2 className="text-lg font-semibold text-neutral-900">功能特性</h2>
          <ul className="mt-4 space-y-3">
            {FEATURES.map(({ icon, label, desc }) => (
              <li key={label} className="flex items-start gap-3">
                <SvgIcon d={icon} />
                <div>
                  <div className="text-sm font-medium text-neutral-900">{label}</div>
                  <div className="text-sm text-neutral-500">{desc}</div>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-lg border border-neutral-200 bg-white p-6">
          <h2 className="text-lg font-semibold text-neutral-900">键盘快捷键</h2>
          <div className="mt-4 space-y-2">
            {KEYBOARD_SHORTCUTS.map(({ keys, desc }) => (
              <div key={keys} className="flex items-center gap-3 text-sm">
                <kbd className="inline-block min-w-[3rem] rounded border border-neutral-200 bg-neutral-50 px-2 py-1 text-center font-mono text-xs text-neutral-600">
                  {keys}
                </kbd>
                <span className="text-neutral-700">{desc}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
