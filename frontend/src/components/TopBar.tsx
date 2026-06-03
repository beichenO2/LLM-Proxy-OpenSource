import clsx from "clsx";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../lib/api";
import { useUiStore } from "../stores/uiStore";
import type { IVaultStatus } from "../types/api";
import ProjectSelect from "./ProjectSelect";

export default function TopBar() {
  const queryClient = useQueryClient();
  const setVaultRole = useUiStore((s) => s.setVaultRole);
  const vaultRole = useUiStore((s) => s.vaultRole);

  const { data } = useQuery({
    queryKey: ["vault-status"],
    queryFn: () => apiRequest<IVaultStatus>("/api/vault/status"),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });

  const logoutMutation = useMutation({
    mutationFn: () =>
      apiRequest("/api/vault/logout", { method: "POST" }),
    onSuccess: () => {
      setVaultRole(null);
      void queryClient.invalidateQueries();
    },
  });

  const lockMutation = useMutation({
    mutationFn: () =>
      apiRequest("/api/vault/lock", { method: "POST" }),
    onSuccess: () => {
      setVaultRole(null);
      void queryClient.invalidateQueries();
    },
  });

  const locked = data?.locked ?? true;
  const isAdmin = vaultRole === "admin";
  const roleLabel = isAdmin ? "管理员" : vaultRole === "user" ? "用户" : null;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-neutral-200 bg-white px-6 dark:border-neutral-700 dark:bg-neutral-800">
      <div className="flex items-center gap-3">
        <ProjectSelect />
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => {
            window.dispatchEvent(new CustomEvent("pp:open-command-palette"));
          }}
          className="flex items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs text-neutral-500 hover:border-neutral-300 hover:bg-neutral-100 dark:border-neutral-600 dark:bg-neutral-700 dark:text-neutral-400 dark:hover:border-neutral-500 dark:hover:bg-neutral-600"
          aria-label="快速导航"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <span className="hidden sm:inline">导航</span>
          <kbd className="rounded border border-neutral-200 bg-white px-1 py-0.5 font-mono text-[10px] leading-none text-neutral-400">
            &#8984;K
          </kbd>
        </button>
        <span
          className={clsx(
            "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold",
            locked ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800",
          )}
          aria-label={locked ? "保险库已锁定" : "保险库已解锁"}
        >
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {locked ? (
              <path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            ) : (
              <path d="M8 11V7a4 4 0 118 0m-4 8v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z" />
            )}
          </svg>
          {locked ? "已锁定" : "已解锁"}
        </span>
        {!locked && roleLabel && (
          <span className="text-xs text-neutral-500">{roleLabel}</span>
        )}
        {!locked && isAdmin && (
          <button
            type="button"
            onClick={() => lockMutation.mutate()}
            disabled={lockMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs text-neutral-500 transition-colors hover:border-amber-200 hover:bg-amber-50 hover:text-amber-700"
            title="锁定保险库（所有浏览器将被登出）"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            {lockMutation.isPending ? "锁定中…" : "锁定"}
          </button>
        )}
        {!locked && (
          <button
            type="button"
            onClick={() => logoutMutation.mutate()}
            disabled={logoutMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs text-neutral-500 transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600"
            title="退出登录（仅此浏览器）"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
            </svg>
            {logoutMutation.isPending ? "退出中…" : "退出"}
          </button>
        )}
      </div>
    </header>
  );
}
