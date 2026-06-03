import clsx from "clsx";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ICON_PATHS } from "../lib/icons";

interface IRoute {
  path: string;
  label: string;
  keywords: string;
  iconPath: string;
}

const ROUTES: IRoute[] = [
  { path: "/", label: "仪表盘", keywords: "home overview dashboard 首页", iconPath: ICON_PATHS.dashboard },
  { path: "/projects", label: "项目", keywords: "project folder 项目", iconPath: ICON_PATHS.projects },
  { path: "/secrets", label: "加密密钥", keywords: "secret key token api password 密钥 密码", iconPath: ICON_PATHS.secrets },
  { path: "/bindings", label: "绑定关系", keywords: "binding service map 绑定", iconPath: ICON_PATHS.bindings },
  { path: "/services", label: "自有服务", keywords: "service proxy api 服务 代理", iconPath: ICON_PATHS.services },
  { path: "/test-center", label: "测试中心", keywords: "test check connectivity 测试", iconPath: ICON_PATHS.testCenter },
  { path: "/users", label: "用户管理", keywords: "user account role 用户 账户", iconPath: ICON_PATHS.settings },
  { path: "/settings", label: "设置", keywords: "settings config port password 设置 配置", iconPath: ICON_PATHS.settings },
  { path: "/logs", label: "日志", keywords: "log audit debug error 日志", iconPath: ICON_PATHS.logs },
  { path: "/usage", label: "用量", keywords: "usage stats proxy 用量 统计 代理", iconPath: ICON_PATHS.logs },
  { path: "/about", label: "关于", keywords: "about version info 关于 版本", iconPath: ICON_PATHS.dashboard },
];

export default function CommandPalette() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const navigate = useNavigate();

  const open = useCallback(() => {
    setIsOpen(true);
    setQuery("");
    setActiveIndex(0);
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    setQuery("");
    setActiveIndex(0);
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (isOpen) close();
        else open();
      }
    }
    function onCustomOpen() {
      if (!isOpen) open();
    }
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("pp:open-command-palette", onCustomOpen);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("pp:open-command-palette", onCustomOpen);
    };
  }, [isOpen, open, close]);

  useEffect(() => {
    if (isOpen) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [isOpen]);

  const lowerQuery = query.toLowerCase().trim();
  const filtered = lowerQuery
    ? ROUTES.filter(
        (r) =>
          r.label.toLowerCase().includes(lowerQuery) ||
          r.keywords.includes(lowerQuery),
      )
    : ROUTES;

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  const goTo = (path: string) => {
    navigate(path);
    close();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      close();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (filtered.length > 0) setActiveIndex((i) => (i + 1) % filtered.length);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (filtered.length > 0) setActiveIndex((i) => (i - 1 + filtered.length) % filtered.length);
      return;
    }
    if (e.key === "Enter" && filtered.length > 0) {
      goTo(filtered[activeIndex].path);
    }
  };

  useEffect(() => {
    if (!listRef.current) return;
    const active = listRef.current.children[activeIndex] as HTMLElement | undefined;
    active?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-start justify-center bg-black/40 pt-[15vh]"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="快速导航"
    >
      <div className="w-full max-w-md overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-2xl dark:border-neutral-700 dark:bg-neutral-800">
        <div className="flex items-center gap-2 border-b border-neutral-200 px-4 dark:border-neutral-700">
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
            <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="跳转到…"
            className="w-full border-0 bg-transparent py-3 text-sm text-neutral-900 outline-none placeholder:text-neutral-400 dark:text-neutral-100"
            aria-label="搜索页面"
            aria-activedescendant={filtered.length > 0 ? `cmd-item-${activeIndex}` : undefined}
          />
          <kbd className="hidden shrink-0 rounded border border-neutral-200 bg-neutral-100 px-1.5 py-0.5 text-[10px] font-medium text-neutral-500 sm:inline-block">
            ESC
          </kbd>
        </div>
        <ul ref={listRef} className="max-h-64 overflow-y-auto py-1" role="listbox">
          {filtered.length === 0 ? (
            <li className="px-4 py-3 text-sm text-neutral-500">未找到结果。</li>
          ) : (
            filtered.map((route, i) => (
              <li
                key={route.path}
                id={`cmd-item-${i}`}
                role="option"
                aria-selected={i === activeIndex}
              >
                <button
                  type="button"
                  onClick={() => goTo(route.path)}
                  onMouseEnter={() => setActiveIndex(i)}
                  className={clsx(
                    "flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-neutral-900 dark:text-neutral-100",
                    i === activeIndex ? "bg-neutral-100 dark:bg-neutral-700" : "hover:bg-neutral-50 dark:hover:bg-neutral-700/50",
                  )}
                >
                  <svg className="h-4 w-4 shrink-0 text-neutral-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d={route.iconPath} />
                  </svg>
                  <span className="font-medium">{route.label}</span>
                  <span className="ml-auto font-mono text-xs text-neutral-400">{route.path}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
