import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { apiRequest } from "../lib/api";
import { btnPrimaryClass, btnSecondaryClass, inputClass, inputMonoClass } from "../lib/styles";
import type { IVaultStatus } from "../types/api";
import { useUiStore } from "../stores/uiStore";

type Mode = "login" | "register";

export default function UnlockModal() {
  const queryClient = useQueryClient();
  const setVaultRole = useUiStore((s) => s.setVaultRole);
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    const handler = () => {
      void queryClient.invalidateQueries({ queryKey: ["vault-status"] });
    };
    window.addEventListener("pp:session-expired", handler);
    return () => window.removeEventListener("pp:session-expired", handler);
  }, [queryClient]);

  const { data: status } = useQuery({
    queryKey: ["vault-status"],
    queryFn: () => apiRequest<IVaultStatus>("/api/vault/status"),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    if (status?.role) {
      setVaultRole(status.role);
    }
  }, [status?.role, setVaultRole]);

  const unlockMutation = useMutation({
    mutationFn: (body: { username: string; master_password: string }) =>
      apiRequest<{ status: string; role: string }>("/api/vault/unlock", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      resetForm();
      setVaultRole(data.role as "admin" | "user");
      void queryClient.invalidateQueries({ queryKey: ["vault-status"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const registerMutation = useMutation({
    mutationFn: (body: { username: string; password: string }) =>
      apiRequest<{ id: string; username: string }>("/api/users/register", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      setSuccessMsg(`用户 "${data.username}" 注册成功！正在自动登录…`);
      setError(null);
      unlockMutation.mutate({
        username: data.username,
        master_password: password,
      });
    },
    onError: (err: Error) => setError(err.message),
  });

  const locked = status?.locked ?? true;
  const hasSession = status?.has_session ?? false;

  const autoSessionMutation = useMutation({
    mutationFn: () =>
      apiRequest<{ status: string; role: string }>("/api/vault/auto-session", {
        method: "POST",
      }),
    onSuccess: (data) => {
      setVaultRole(data.role as "admin" | "user" | "readonly");
      void queryClient.invalidateQueries({ queryKey: ["vault-status"] });
    },
  });

  useEffect(() => {
    if (!locked && !hasSession && !autoSessionMutation.isPending && !autoSessionMutation.isSuccess) {
      autoSessionMutation.mutate();
    }
  }, [locked, hasSession]);

  if (!locked && hasSession) return null;
  if (!locked && !hasSession && (autoSessionMutation.isPending || autoSessionMutation.isSuccess)) return null;

  const isSessionOnly = !locked && !hasSession;

  function resetForm() {
    setPassword("");
    setConfirmPassword("");
    setError(null);
    setSuccessMsg(null);
  }

  function switchMode(next: Mode) {
    setMode(next);
    setUsername(next === "login" ? "admin" : "");
    resetForm();
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);

    if (mode === "register") {
      if (password !== confirmPassword) {
        setError("两次输入的密码不一致");
        return;
      }
      registerMutation.mutate({ username: username.trim(), password });
    } else {
      unlockMutation.mutate({
        username: username.trim() || "admin",
        master_password: password,
      });
    }
  };

  const isPending = unlockMutation.isPending || registerMutation.isPending;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-labelledby="unlock-modal-title"
    >
      <div className="w-full max-w-md rounded-lg border border-neutral-200 bg-white p-6 shadow-lg">
        <h2 id="unlock-modal-title" className="text-lg font-semibold text-neutral-900">
          {mode === "register"
            ? "注册新用户"
            : isSessionOnly
              ? "身份验证"
              : "解锁保险库"}
        </h2>
        <p className="mt-1 text-sm text-neutral-600">
          {mode === "register"
            ? "注册后可使用保险库中的密钥（仅使用，不可查看原始值）。"
            : isSessionOnly
              ? "保险库已解锁，但此浏览器需要进行身份验证。"
              : "输入用户名和密码以继续。"}
        </p>

        <form onSubmit={onSubmit} className="mt-4 space-y-3">
          <div>
            <label htmlFor="unlock-username" className="block text-xs font-medium text-neutral-500">
              用户名
            </label>
            <input
              id="unlock-username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={`mt-1 ${inputClass}`}
              placeholder={mode === "register" ? "选择一个用户名" : "admin"}
            />
          </div>
          <div>
            <label htmlFor="unlock-password" className="block text-xs font-medium text-neutral-500">
              密码
            </label>
            <input
              id="unlock-password"
              type="password"
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`mt-1 ${inputMonoClass}`}
              placeholder={mode === "register" ? "至少 8 位" : "主密码"}
            />
          </div>

          {mode === "register" && (
            <div>
              <label htmlFor="unlock-confirm" className="block text-xs font-medium text-neutral-500">
                确认密码
              </label>
              <input
                id="unlock-confirm"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className={`mt-1 ${inputMonoClass}`}
                placeholder="再次输入密码"
              />
            </div>
          )}

          {successMsg && <p className="text-sm text-green-600">{successMsg}</p>}
          {error && <p role="alert" className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={isPending || !password.trim() || (mode === "register" && !username.trim())}
            className={btnPrimaryClass}
          >
            {isPending
              ? mode === "register" ? "注册中…" : "解锁中…"
              : mode === "register" ? "注册" : "解锁"}
          </button>
        </form>

        {/* 注册入口暂时隐藏 — admin 通过后台管理用户 */}
        <div className="mt-4 text-center hidden">
          {mode === "login" ? (
            <button
              type="button"
              className={`${btnSecondaryClass} text-xs`}
              onClick={() => switchMode("register")}
            >
              没有账户？注册新用户
            </button>
          ) : (
            <button
              type="button"
              className={`${btnSecondaryClass} text-xs`}
              onClick={() => switchMode("login")}
            >
              已有账户？返回登录
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
