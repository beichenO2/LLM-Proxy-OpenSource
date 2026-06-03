import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiRequest } from "../lib/api";
import { btnPrimaryClass, inputClass, inputMonoClass, thClass, tdClass } from "../lib/styles";
import PageHeader from "../components/PageHeader";
import ConfirmDialog from "../components/ConfirmDialog";
import type { IUserOut, IUserListResponse } from "../types/api";

type IUser = IUserOut;
type IUsersResponse = IUserListResponse;

export default function UsersPage() {
  const queryClient = useQueryClient();
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<IUser | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => apiRequest<IUsersResponse>("/api/users"),
  });

  const createMutation = useMutation({
    mutationFn: (body: { username: string; password: string }) =>
      apiRequest<IUser>("/api/users", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setNewUsername("");
      setNewPassword("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/api/users/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setDeleteTarget(null);
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const onCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    createMutation.mutate({ username: newUsername.trim(), password: newPassword });
  };

  return (
    <div className="space-y-6">
      <PageHeader title="用户管理" description="管理非 admin 用户账户。用户可以使用保险库中的密钥，但无法查看原始值。" />

      {/* 创建用户 */}
      <div className="rounded-lg border border-neutral-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-neutral-900">创建新用户</h3>
        <form onSubmit={onCreateSubmit} className="mt-3 flex items-end gap-3">
          <div className="flex-1">
            <label htmlFor="new-username" className="block text-xs font-medium text-neutral-500">
              用户名
            </label>
            <input
              id="new-username"
              type="text"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              className={`mt-1 ${inputClass}`}
              placeholder="用户名"
            />
          </div>
          <div className="flex-1">
            <label htmlFor="new-password" className="block text-xs font-medium text-neutral-500">
              密码
            </label>
            <input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className={`mt-1 ${inputMonoClass}`}
              placeholder="至少 8 位"
            />
          </div>
          <button
            type="submit"
            disabled={createMutation.isPending || !newUsername.trim() || newPassword.length < 8}
            className={btnPrimaryClass}
          >
            {createMutation.isPending ? "创建中…" : "创建"}
          </button>
        </form>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      </div>

      {/* 用户列表 */}
      <div className="rounded-lg border border-neutral-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-neutral-900">
          已注册用户 {data ? `(${data.total})` : ""}
        </h3>
        {isLoading ? (
          <p className="mt-3 text-sm text-neutral-500">加载中…</p>
        ) : !data?.items?.length ? (
          <p className="mt-3 text-sm text-neutral-500">暂无注册用户。</p>
        ) : (
          <table className="mt-3 w-full border-collapse text-sm">
            <thead>
              <tr>
                <th className={thClass}>用户名</th>
                <th className={thClass}>角色</th>
                <th className={thClass}>注册时间</th>
                <th className={thClass}>操作</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((user) => (
                <tr key={user.id}>
                  <td className={tdClass}>{user.username}</td>
                  <td className={tdClass}>
                    <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs font-medium text-neutral-700">
                      {user.role}
                    </span>
                  </td>
                  <td className={`${tdClass} text-neutral-500`}>
                    {new Date(user.created_at).toLocaleString("zh-CN")}
                  </td>
                  <td className={tdClass}>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(user)}
                      className="text-sm text-red-600 hover:text-red-800"
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title="删除用户"
        message={deleteTarget ? `确定要删除用户 "${deleteTarget.username}" 吗？此操作不可撤销。` : ""}
        onConfirm={() => { if (deleteTarget) deleteMutation.mutate(deleteTarget.id); }}
        isDestructive
        isPending={deleteMutation.isPending}
        confirmLabel="删除"
      />
    </div>
  );
}
