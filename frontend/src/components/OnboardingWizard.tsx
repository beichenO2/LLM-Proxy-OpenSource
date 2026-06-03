import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { apiRequest } from "../lib/api";
import { btnPrimaryClass, btnSecondaryClass, inputMonoClass } from "../lib/styles";
import { showApiError, toast } from "../lib/toast";
import type { IOnboardingStatus } from "../types/api";

type Step = "welcome" | "password" | "demo" | "done";

export default function OnboardingWizard() {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>("welcome");
  const [initError, setInitError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [unlockError, setUnlockError] = useState<string | null>(null);
  /** Default ON per D-109 — user can turn off before choosing Import vs Skip */
  const [includeDemo, setIncludeDemo] = useState(true);

  const { data: status, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["onboarding-status"],
    queryFn: () => apiRequest<IOnboardingStatus>("/api/onboarding/status"),
    staleTime: 0,
  });

  const initDbMutation = useMutation({
    mutationFn: () => apiRequest<{ ok: boolean }>("/api/onboarding/init-db", { method: "POST" }),
  });

  const initVaultMutation = useMutation({
    mutationFn: (masterPassword: string) =>
      apiRequest<{ status: string }>("/api/vault/init", {
        method: "POST",
        body: JSON.stringify({ master_password: masterPassword }),
      }),
    onSuccess: () => {
      setUnlockError(null);
      void queryClient.invalidateQueries({ queryKey: ["vault-status"] });
      void queryClient.invalidateQueries({ queryKey: ["onboarding-status"] });
      setStep("demo");
      setPassword("");
      setPasswordConfirm("");
    },
    onError: (err: Error) => {
      setUnlockError(err.message);
    },
  });

  const unlockMutation = useMutation({
    mutationFn: (masterPassword: string) =>
      apiRequest<{ status: string }>("/api/vault/unlock", {
        method: "POST",
        body: JSON.stringify({ master_password: masterPassword }),
      }),
    onSuccess: () => {
      setUnlockError(null);
      void queryClient.invalidateQueries({ queryKey: ["vault-status"] });
      setStep("demo");
      setPassword("");
      setPasswordConfirm("");
    },
    onError: (err: Error) => {
      setUnlockError(err.message);
    },
  });

  const importDemoMutation = useMutation({
    mutationFn: () =>
      apiRequest<Record<string, unknown>>("/api/onboarding/import-demo", { method: "POST" }),
    onSuccess: () => {
      toast.success("演示数据已导入");
      setStep("done");
    },
    onError: (err: Error) => {
      showApiError(err);
    },
  });

  const completeMutation = useMutation({
    mutationFn: () => apiRequest<{ ok: boolean }>("/api/onboarding/complete", { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["onboarding-status"] });
    },
  });

  if (isLoading) {
    return (
      <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40">
        <div className="rounded-lg bg-white px-6 py-4 text-sm text-neutral-600 shadow-lg">加载中…</div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4">
        <div className="w-full max-w-md rounded-lg border border-neutral-200 bg-white p-6 shadow-lg">
          <p className="text-sm text-red-600">
            {error instanceof Error ? error.message : "加载初始化状态失败"}
          </p>
          <button
            type="button"
            className={`mt-4 ${btnPrimaryClass}`}
            onClick={() => void refetch()}
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  if (!status || status.completed) {
    return null;
  }

  const onWelcomeNext = () => {
    setInitError(null);
    if (!status.has_db) {
      initDbMutation.mutate(undefined, {
        onSuccess: async () => {
          const { data } = await refetch();
          if (data?.has_db) {
            setStep("password");
          } else {
            setInitError(
              "Database was not initialized. Try again or run `privportal init-db` in a terminal.",
            );
          }
        },
        onError: (err: Error) => {
          setInitError(err.message);
        },
      });
    } else {
      setStep("password");
    }
  };

  const needsInit = status && !status.has_vault;

  const onPasswordSubmit = (e: FormEvent) => {
    e.preventDefault();
    setUnlockError(null);
    if (!password.trim()) {
      setUnlockError("请输入主密码。");
      return;
    }
    if (needsInit && password.length < 8) {
      setUnlockError("密码至少需要 8 个字符。");
      return;
    }
    if (needsInit && password !== passwordConfirm) {
      setUnlockError("两次输入的密码不一致。");
      return;
    }
    if (needsInit) {
      initVaultMutation.mutate(password);
    } else {
      unlockMutation.mutate(password);
    }
  };

  const goToDoneSkipImport = () => {
    setStep("done");
  };

  const onImportDemo = () => {
    importDemoMutation.mutate();
  };

  const onFinish = () => {
    completeMutation.mutate();
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="onboarding-title"
    >
      <div className="w-full max-w-lg rounded-lg border border-neutral-200 bg-white p-6 shadow-lg">
        {step === "welcome" ? (
          <>
            <h2 id="onboarding-title" className="text-lg font-semibold text-neutral-900">
              欢迎使用 PolarPrivate
            </h2>
            <p className="mt-2 text-sm text-neutral-600">
              PolarPrivate 是一个本地隐私代理和保险库：在一处管理身份信息和加密密钥，运行时注入密钥而不暴露明文，
              并使用安全占位符导出文档。此向导将帮助你设置加密保险库和可选的演示数据。
            </p>
            {initError ? <p role="alert" className="mt-3 text-sm text-red-600">{initError}</p> : null}
            {!status.has_db ? (
              <p className="mt-3 text-xs text-neutral-500">
                下一步将创建数据库。如果失败，请手动运行{" "}
                <code className="rounded bg-neutral-100 px-1">privportal init-db</code>。
              </p>
            ) : null}
            <button
              type="button"
              disabled={initDbMutation.isPending}
              className={`mt-6 ${btnPrimaryClass}`}
              onClick={onWelcomeNext}
            >
              {initDbMutation.isPending ? "准备中…" : "下一步"}
            </button>
          </>
        ) : null}

        {step === "password" ? (
          <>
            <h2 className="text-lg font-semibold text-neutral-900">
              {needsInit ? "设置主密码" : "解锁保险库"}
            </h2>
            <p className="mt-1 text-sm text-neutral-600">
              {needsInit
                ? "请设置一个强密码（8 位以上）。密码通过 PBKDF2 + Fernet 加密保险库，丢失后无法恢复。密钥仅在解锁期间存在于内存中。"
                : "输入主密码以解锁保险库。"}
            </p>
            <form onSubmit={onPasswordSubmit} className="mt-4 space-y-3">
              <input
                type="password"
                autoComplete={needsInit ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputMonoClass}
                placeholder="主密码"
              />
              {needsInit ? (
                <input
                  type="password"
                  autoComplete="new-password"
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  className={inputMonoClass}
                  placeholder="确认主密码"
                />
              ) : null}
              {unlockError ? <p role="alert" className="text-sm text-red-600">{unlockError}</p> : null}
              <button
                type="submit"
                disabled={(initVaultMutation.isPending || unlockMutation.isPending) || !password.trim()}
                className={btnPrimaryClass}
              >
                {(initVaultMutation.isPending || unlockMutation.isPending)
                  ? (needsInit ? "创建保险库…" : "解锁中…")
                  : "继续"}
              </button>
            </form>
          </>
        ) : null}

        {step === "demo" ? (
          <>
            <h2 className="text-lg font-semibold text-neutral-900">演示数据</h2>
            <p className="mt-1 text-sm text-neutral-600">
              导入示例项目（含身份信息、密钥和绑定关系），快速体验 PolarPrivate 的功能。
            </p>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-neutral-800">
              <input
                type="checkbox"
                checked={includeDemo}
                onChange={(e) => setIncludeDemo(e.target.checked)}
                className="h-4 w-4 rounded border-neutral-300"
              />
              建议导入演示项目（推荐）
            </label>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                disabled={importDemoMutation.isPending}
                className={btnPrimaryClass}
                onClick={onImportDemo}
              >
                {importDemoMutation.isPending ? "导入中…" : "导入演示数据"}
              </button>
              <button
                type="button"
                className={btnSecondaryClass}
                onClick={goToDoneSkipImport}
              >
                跳过
              </button>
            </div>
          </>
        ) : null}

        {step === "done" ? (
          <>
            <h2 className="text-lg font-semibold text-neutral-900">准备就绪</h2>
            <p className="mt-1 text-sm text-neutral-600">
              完成设置后即可开始使用。随时可以在侧边栏中更改设置。
            </p>
            <button
              type="button"
              disabled={completeMutation.isPending}
              className={`mt-6 ${btnPrimaryClass}`}
              onClick={onFinish}
            >
              {completeMutation.isPending ? "保存中…" : "开始使用"}
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
}
