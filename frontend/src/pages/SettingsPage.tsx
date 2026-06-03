import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getErrorMessage } from "../lib/api";
import { btnPrimaryClass, btnSecondaryClass, inputClass, labelClass, linkDangerClass, selectClass } from "../lib/styles";
import { showApiError, toast } from "../lib/toast";
import { useDocumentTitle } from "../lib/use-document-title";
import type { ISettingsGetResponse, IUserListResponse, IUserOut } from "../types/api";
import PageHeader from "../components/PageHeader";
import { Skeleton } from "../components/Skeleton";
import { useUiStore } from "../stores/uiStore";

export default function SettingsPage() {
  useDocumentTitle("设置");
  const queryClient = useQueryClient();
  const isAdmin = useUiStore((s) => s.vaultRole) === "admin";
  const settingsQuery = useQuery({
    queryKey: ["app-settings"],
    queryFn: () => apiRequest<ISettingsGetResponse>("/api/settings"),
  });

  const [apiPort, setApiPort] = useState<string>("");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [editorFontSize, setEditorFontSize] = useState<number>(14);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  useEffect(() => {
    const data = settingsQuery.data;
    if (!data) return;
    setApiPort(data.api_port != null ? String(data.api_port) : "");
    const p = data.preferences ?? {};
    if (p.theme === "light" || p.theme === "dark") setTheme(p.theme);
    if (typeof p.editorFontSize === "number" && !Number.isNaN(p.editorFontSize)) {
      setEditorFontSize(p.editorFontSize);
    }
  }, [settingsQuery.data]);

  const putSettingsMutation = useMutation({
    mutationFn: (body: { api_port?: number | null; preferences?: Record<string, unknown> }) =>
      apiRequest<ISettingsGetResponse>("/api/settings", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["app-settings"] });
      toast.success("设置已保存。");
    },
    onError: (e: Error) => showApiError(e),
  });

  const changePasswordMutation = useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      apiRequest<{ status: string }>("/api/vault/change-password", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      toast.success("主密码已更新。");
    },
    onError: (e: Error) => showApiError(e),
  });

  const onSavePort = (e: FormEvent) => {
    e.preventDefault();
    const n = parseInt(apiPort.trim(), 10);
    if (Number.isNaN(n) || n < 1024 || n > 65535) {
      toast.error("API 端口必须在 1024 到 65535 之间。");
      return;
    }
    putSettingsMutation.mutate({ api_port: n });
  };

  const onSavePreferences = (e: FormEvent) => {
    e.preventDefault();
    const base = { ...(settingsQuery.data?.preferences ?? {}) };
    const merged: Record<string, unknown> = {
      ...base,
      theme,
      editorFontSize,
    };
    putSettingsMutation.mutate({ preferences: merged });
    window.dispatchEvent(new CustomEvent("pp:theme-change", { detail: theme }));
  };

  const onChangePassword = (e: FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 8) {
      toast.error("新密码至少需要 8 个字符。");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("新密码和确认密码不一致。");
      return;
    }
    changePasswordMutation.mutate({
      current_password: currentPassword,
      new_password: newPassword,
    });
  };

  const backupMutation = useMutation({
    mutationFn: () =>
      apiRequest<{ version: number; created_at: string; salt: string; payload: string }>(
        "/api/vault/backup",
        { method: "POST" },
      ),
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const ts = new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-");
      a.download = `privportal-backup-${ts}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("加密备份已下载。");
    },
    onError: (e: Error) => showApiError(e),
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [restoreStrategy, setRestoreStrategy] = useState<"merge" | "replace">("merge");
  const [restorePassword, setRestorePassword] = useState("");
  const [pendingFile, setPendingFile] = useState<{ payload: string; salt: string } | null>(null);

  const onSelectRestoreFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const parsed = JSON.parse(text);
        if (!parsed.payload || !parsed.salt) {
          toast.error("备份文件无效 — 缺少 payload 或 salt。");
          return;
        }
        setPendingFile({ payload: parsed.payload, salt: parsed.salt });
        toast.success("备份文件已加载。请输入源设备的主密码以导入。");
      } catch {
        toast.error("无法读取备份文件。");
      }
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [],
  );

  const onConfirmRestore = useCallback(async () => {
    if (!pendingFile) return;
    if (restorePassword.length < 8) {
      toast.error("主密码至少需要 8 个字符。");
      return;
    }
    try {
      const result = await apiRequest<{
        projects: number;
        identities: number;
        secrets: number;
        bindings: number;
        skipped: number;
      }>("/api/vault/restore", {
        method: "POST",
        body: JSON.stringify({
          payload: pendingFile.payload,
          salt: pendingFile.salt,
          master_password: restorePassword,
          strategy: restoreStrategy,
        }),
      });
      toast.success(
        `已恢复：${result.projects} 个项目、${result.secrets} 个密钥、${result.identities} 个身份、${result.bindings} 个绑定（跳过 ${result.skipped} 个）。`,
      );
      void queryClient.invalidateQueries();
      setPendingFile(null);
      setRestorePassword("");
    } catch (err) {
      showApiError(err as Error);
    }
  }, [pendingFile, restorePassword, restoreStrategy, queryClient]);

  const busy =
    putSettingsMutation.isPending ||
    changePasswordMutation.isPending ||
    backupMutation.isPending;

  return (
    <div className="p-8">
      <PageHeader
        title="设置"
        description="API 端口、偏好设置和主密码。"
      />

      {settingsQuery.isLoading ? (
        <div className="mt-8 max-w-xl space-y-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-lg border border-neutral-200 bg-white p-6 space-y-3">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-4 w-64" />
              <Skeleton className="h-9 w-full max-w-xs" />
              <Skeleton className="h-9 w-24" />
            </div>
          ))}
        </div>
      ) : settingsQuery.error ? (
        <p role="alert" className="mt-6 text-sm text-red-600">
          {getErrorMessage(settingsQuery.error)}
        </p>
      ) : (
        <div className="mt-8 max-w-xl space-y-6">
          <section className="rounded-lg border border-neutral-200 bg-white p-6">
            <h2 className="mb-2 text-lg font-semibold text-neutral-900">代理 / API 端口</h2>
            <p className="mb-4 text-sm text-neutral-600">
              管理 API 的监听端口。修改后需重启服务器生效。
            </p>
            <form onSubmit={onSavePort} className="space-y-3">
              <div>
                <label htmlFor="api-port" className={labelClass}>端口 (1024–65535)</label>
                <input
                  id="api-port"
                  type="number"
                  min={1024}
                  max={65535}
                  value={apiPort}
                  onChange={(e) => setApiPort(e.target.value)}
                  className={`mt-1 max-w-xs ${inputClass}`}
                />
              </div>
              <button type="submit" disabled={busy} className={btnPrimaryClass}>
                保存端口
              </button>
            </form>
          </section>

          <section className="rounded-lg border border-neutral-200 bg-white p-6">
            <h2 className="mb-2 text-lg font-semibold text-neutral-900">偏好设置</h2>
            <p className="mb-4 text-sm text-neutral-600">
              主题和编辑器字号设置。
            </p>
            <form onSubmit={onSavePreferences} className="space-y-3">
              <div>
                <label htmlFor="pref-theme" className={labelClass}>主题</label>
                <select
                  id="pref-theme"
                  value={theme}
                  onChange={(e) => setTheme(e.target.value as "light" | "dark")}
                  className={`mt-1 max-w-xs ${selectClass}`}
                >
                  <option value="light">浅色</option>
                  <option value="dark">深色</option>
                </select>
              </div>
              <div>
                <label htmlFor="pref-fs" className={labelClass}>编辑器字号 (px)</label>
                <input
                  id="pref-fs"
                  type="number"
                  min={10}
                  max={32}
                  value={editorFontSize}
                  onChange={(e) => setEditorFontSize(Number(e.target.value))}
                  className={`mt-1 max-w-xs ${inputClass}`}
                />
              </div>
              <button type="submit" disabled={busy} className={btnPrimaryClass}>
                保存偏好
              </button>
            </form>
          </section>

          <section className="rounded-lg border border-neutral-200 bg-white p-6">
            <h2 className="mb-2 text-lg font-semibold text-neutral-900">主密码</h2>
            <p className="mb-4 text-sm text-neutral-600">
              更改保险库主密码。需先解锁保险库。
            </p>
            <form onSubmit={onChangePassword} className="space-y-3">
              <div>
                <label htmlFor="pw-current" className={labelClass}>当前密码</label>
                <input
                  id="pw-current"
                  type="password"
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  className={`mt-1 ${inputClass}`}
                />
              </div>
              <div>
                <label htmlFor="pw-new" className={labelClass}>新密码（至少 8 个字符）</label>
                <input
                  id="pw-new"
                  type="password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className={`mt-1 ${inputClass}`}
                />
              </div>
              <div>
                <label htmlFor="pw-confirm" className={labelClass}>确认新密码</label>
                <input
                  id="pw-confirm"
                  type="password"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className={`mt-1 ${inputClass}`}
                />
              </div>
              <button type="submit" disabled={busy} className={btnPrimaryClass}>
                修改密码
              </button>
            </form>
          </section>

          <section className="rounded-lg border border-neutral-200 bg-white p-6">
            <h2 className="mb-2 text-lg font-semibold text-neutral-900">保险库同步</h2>
            <p className="mb-4 text-sm text-neutral-600">
              通过 Git 跨设备同步加密数据，或手动导出/导入备份文件。
            </p>
            {isAdmin ? <GitSyncControls /> : null}
            <div className="space-y-4">
              <div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => backupMutation.mutate()}
                  className={btnSecondaryClass}
                >
                  下载加密备份
                </button>
              </div>
              <hr className="border-neutral-200" />
              <div className="space-y-3">
                <div>
                  <label htmlFor="restore-strategy" className={labelClass}>
                    导入策略
                  </label>
                  <select
                    id="restore-strategy"
                    value={restoreStrategy}
                    onChange={(e) => setRestoreStrategy(e.target.value as "merge" | "replace")}
                    className={`mt-1 max-w-xs ${selectClass}`}
                  >
                    <option value="merge">合并（跳过已有）</option>
                    <option value="replace">替换（覆盖全部）</option>
                  </select>
                </div>
                <div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".json"
                    onChange={onSelectRestoreFile}
                    className="hidden"
                    id="restore-file"
                  />
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => fileInputRef.current?.click()}
                    className={btnSecondaryClass}
                  >
                    {pendingFile ? "更换备份文件…" : "选择备份文件…"}
                  </button>
                </div>
                {pendingFile && (
                  <div className="rounded-md border border-blue-200 bg-blue-50 p-4 space-y-3">
                    <p className="text-sm text-blue-800">
                      备份已加载。请输入<strong>源设备</strong>的主密码以解密并导入。
                    </p>
                    <div>
                      <label htmlFor="restore-pw" className={labelClass}>
                        源设备主密码
                      </label>
                      <input
                        id="restore-pw"
                        type="password"
                        autoComplete="off"
                        value={restorePassword}
                        onChange={(e) => setRestorePassword(e.target.value)}
                        className={`mt-1 max-w-xs ${inputClass}`}
                        placeholder="输入源设备上使用的密码"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={busy || restorePassword.length < 8}
                        onClick={onConfirmRestore}
                        className={btnPrimaryClass}
                      >
                        立即导入
                      </button>
                      <button
                        type="button"
                        onClick={() => { setPendingFile(null); setRestorePassword(""); }}
                        className={btnSecondaryClass}
                      >
                        取消
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>

          {isAdmin ? <UserManagementSection /> : null}
        </div>
      )}
    </div>
  );
}


function UserManagementSection() {
  const queryClient = useQueryClient();
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const usersQuery = useQuery({
    queryKey: ["user-accounts"],
    queryFn: () => apiRequest<IUserListResponse>("/api/users"),
  });

  const createMutation = useMutation({
    mutationFn: (body: { username: string; password: string }) =>
      apiRequest<IUserOut>("/api/users", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setNewUsername("");
      setNewPassword("");
      toast.success("用户已创建。");
      void queryClient.invalidateQueries({ queryKey: ["user-accounts"] });
    },
    onError: (e: Error) => showApiError(e),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/api/users/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("用户已删除。");
      void queryClient.invalidateQueries({ queryKey: ["user-accounts"] });
    },
    onError: (e: Error) => showApiError(e),
  });

  const onCreateUser = (e: FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || newPassword.length < 8) return;
    createMutation.mutate({ username: newUsername.trim(), password: newPassword });
  };

  const users = usersQuery.data?.items ?? [];

  return (
    <section className="rounded-lg border border-neutral-200 bg-white p-6">
      <h2 className="mb-2 text-lg font-semibold text-neutral-900">用户管理</h2>
      <p className="mb-4 text-sm text-neutral-600">
        注册的用户可以通过代理使用密钥，但无法查看或修改。
      </p>

      {users.length > 0 ? (
        <div className="mb-4 overflow-hidden rounded-md border border-neutral-200">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-neutral-200 bg-neutral-50">
              <tr>
                <th className="px-3 py-2 text-xs font-medium uppercase text-neutral-500">用户名</th>
                <th className="px-3 py-2 text-xs font-medium uppercase text-neutral-500">角色</th>
                <th className="px-3 py-2 text-xs font-medium uppercase text-neutral-500">创建时间</th>
                <th className="px-3 py-2 text-right text-xs font-medium uppercase text-neutral-500">操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-neutral-100 last:border-0">
                  <td className="px-3 py-2 font-medium text-neutral-900">{u.username}</td>
                  <td className="px-3 py-2 text-neutral-600">{u.role}</td>
                  <td className="px-3 py-2 text-neutral-600">
                    {new Date(u.created_at).toLocaleDateString("zh-CN")}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      className={linkDangerClass}
                      disabled={deleteMutation.isPending}
                      onClick={() => deleteMutation.mutate(u.id)}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mb-4 text-sm text-neutral-500">暂无注册用户。</p>
      )}

      <form onSubmit={onCreateUser} className="space-y-3 border-t border-neutral-200 pt-4">
        <h3 className="text-sm font-medium text-neutral-800">注册新用户</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="new-user-name" className={labelClass}>用户名</label>
            <input
              id="new-user-name"
              type="text"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              className={`mt-1 ${inputClass}`}
              placeholder="输入用户名"
            />
          </div>
          <div>
            <label htmlFor="new-user-pw" className={labelClass}>密码（至少 8 位）</label>
            <input
              id="new-user-pw"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className={`mt-1 ${inputClass}`}
              placeholder="输入密码"
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={createMutation.isPending || !newUsername.trim() || newPassword.length < 8}
          className={btnPrimaryClass}
        >
          注册用户
        </button>
      </form>
    </section>
  );
}


function GitSyncControls() {
  const [pullPassword, setPullPassword] = useState("");
  const [showPull, setShowPull] = useState(false);

  const pushMutation = useMutation({
    mutationFn: () =>
      apiRequest<{ backup_chars: number; git_pushed: boolean; message: string }>("/api/vault/sync-push", {
        method: "POST",
      }),
    onSuccess: (data) => {
      if (data.git_pushed) {
        toast.success(data.message);
      } else {
        toast.info(data.message);
      }
    },
    onError: (e: Error) => showApiError(e),
  });

  const pullMutation = useMutation({
    mutationFn: (body: { master_password: string; strategy: string }) =>
      apiRequest<{
        git_pulled: boolean;
        restored: boolean;
        message: string;
        projects: number;
        secrets: number;
        identities: number;
        bindings: number;
        skipped: number;
      }>("/api/vault/sync-pull", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      setPullPassword("");
      setShowPull(false);
      if (data.restored) {
        toast.success(`${data.message}（项目 ${data.projects}、密钥 ${data.secrets}、身份 ${data.identities}、绑定 ${data.bindings}，跳过 ${data.skipped}）`);
      } else {
        toast.error(data.message);
      }
    },
    onError: (e: Error) => showApiError(e),
  });

  const busy = pushMutation.isPending || pullMutation.isPending;

  return (
    <div className="mb-4 flex flex-wrap gap-3 rounded-md border border-blue-200 bg-blue-50/50 p-4">
      <button
        type="button"
        disabled={busy}
        onClick={() => pushMutation.mutate()}
        className={btnPrimaryClass}
      >
        {pushMutation.isPending ? "推送中…" : "备份并推送到 Git"}
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => setShowPull(!showPull)}
        className={btnSecondaryClass}
      >
        从 Git 拉取并恢复
      </button>
      {showPull && (
        <div className="mt-2 flex w-full items-end gap-2">
          <div className="flex-1">
            <label htmlFor="sync-pull-pw" className={labelClass}>主密码</label>
            <input
              id="sync-pull-pw"
              type="password"
              autoComplete="off"
              value={pullPassword}
              onChange={(e) => setPullPassword(e.target.value)}
              className={`mt-1 ${inputClass}`}
              placeholder="输入备份的主密码"
            />
          </div>
          <button
            type="button"
            disabled={busy || pullPassword.length < 8}
            onClick={() => pullMutation.mutate({ master_password: pullPassword, strategy: "merge" })}
            className={btnPrimaryClass}
          >
            {pullMutation.isPending ? "恢复中…" : "确认恢复"}
          </button>
        </div>
      )}
    </div>
  );
}
