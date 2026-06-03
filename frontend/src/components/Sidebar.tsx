import clsx from "clsx";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { ICON_PATHS } from "../lib/icons";
import { useUiStore } from "../stores/uiStore";

interface INavItem {
  to: string;
  label: string;
  icon: ReactNode;
  adminOnly?: boolean;
}

interface INavGroup {
  title: string;
  items: INavItem[];
}

function Icon({ d }: { d: string }) {
  return (
    <svg
      className="h-4 w-4 shrink-0"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

const navGroups: INavGroup[] = [
  {
    title: "",
    items: [
      { to: "/", label: "仪表盘", icon: <Icon d={ICON_PATHS.dashboard} /> },
      { to: "/projects", label: "项目", icon: <Icon d={ICON_PATHS.projects} /> },
    ],
  },
  {
    title: "保险库",
    items: [
      { to: "/secrets", label: "加密密钥", icon: <Icon d={ICON_PATHS.secrets} /> },
      { to: "/bindings", label: "绑定关系", icon: <Icon d={ICON_PATHS.bindings} /> },
    ],
  },
  {
    title: "工具",
    items: [
      { to: "/test-center", label: "测试中心", icon: <Icon d={ICON_PATHS.testCenter} /> },
    ],
  },
  {
    title: "系统",
    items: [
      { to: "/settings", label: "设置", icon: <Icon d={ICON_PATHS.settings} />, adminOnly: true },
      { to: "/users", label: "用户管理", icon: <Icon d={ICON_PATHS.users} />, adminOnly: true },
      { to: "/logs", label: "日志", icon: <Icon d={ICON_PATHS.logs} /> },
      { to: "/usage", label: "用量", icon: <Icon d={ICON_PATHS.logs} /> },
      { to: "/about", label: "关于", icon: <Icon d={ICON_PATHS.about} /> },
    ],
  },
];

export default function Sidebar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const vaultRole = useUiStore((s) => s.vaultRole);

  return (
    <aside
      className={clsx(
        "flex shrink-0 flex-col border-r border-neutral-200 bg-white transition-[width] duration-200 ease-in-out dark:border-neutral-700 dark:bg-neutral-800",
        collapsed ? "w-14" : "w-56",
      )}
      role="navigation"
      aria-label="主导航"
    >
      <div className="flex h-14 shrink-0 items-center border-b border-neutral-200 px-3 dark:border-neutral-700">
        <button
          type="button"
          onClick={toggleSidebar}
          className="flex h-8 w-8 items-center justify-center rounded-md text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-700 dark:hover:text-neutral-100"
          aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}
          title={collapsed ? "展开侧边栏" : "收起侧边栏"}
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {collapsed ? (
              <path d="M4 6h16M4 12h16M4 18h16" />
            ) : (
              <path d="M4 6h16M4 12h10M4 18h16" />
            )}
          </svg>
        </button>
        {!collapsed && (
          <span className="ml-2 text-base font-bold tracking-tight text-neutral-900 dark:text-neutral-100">PolarPrivate</span>
        )}
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2">
        {navGroups.map((group) => {
          const visibleItems = group.items.filter(
            (item) => !item.adminOnly || vaultRole === "admin",
          );
          if (!visibleItems.length) return null;
          return (
          <div key={group.title || "__root"}>
            {group.title && !collapsed ? (
              <div className="mb-1 mt-3 px-3 text-[10px] font-semibold uppercase tracking-wider text-neutral-400 first:mt-0 dark:text-neutral-500">
                {group.title}
              </div>
            ) : group.title && collapsed ? (
              <div className="mx-auto my-2 h-px w-5 bg-neutral-200 dark:bg-neutral-700" />
            ) : null}
            {visibleItems.map(({ to, label, icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                title={collapsed ? label : undefined}
                className={({ isActive }) =>
                  clsx(
                    "relative flex items-center rounded-md transition-colors",
                    collapsed ? "justify-center px-2 py-2" : "gap-2.5 px-3 py-2",
                    isActive
                      ? "bg-neutral-100 font-medium text-neutral-900 dark:bg-neutral-700 dark:text-neutral-100"
                      : "text-neutral-600 hover:bg-neutral-50 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-700/50 dark:hover:text-neutral-100",
                    !collapsed && "text-sm",
                    isActive && !collapsed && "before:absolute before:inset-y-1 before:left-0 before:w-[3px] before:rounded-full before:bg-neutral-900 dark:before:bg-neutral-300",
                  )
                }
              >
                {icon}
                {!collapsed && label}
              </NavLink>
            ))}
          </div>
          );
        })}
      </nav>
      {!collapsed && (
        <div className="shrink-0 border-t border-neutral-200 px-3 py-2 dark:border-neutral-700">
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-neutral-400">
            <span>
              <kbd className="rounded border border-neutral-200 bg-neutral-50 px-1 py-0.5 font-mono">&#8984;K</kbd> 导航
            </span>
            <span>
              <kbd className="rounded border border-neutral-200 bg-neutral-50 px-1 py-0.5 font-mono">&#8984;B</kbd> 切换
            </span>
          </div>
        </div>
      )}
    </aside>
  );
}
