import clsx from "clsx";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useMemo, useState } from "react";
import { apiRequest, getErrorMessage } from "../lib/api";
import {
  btnPrimaryClass,
  btnSecondaryClass,
  inputClass,
  inputMonoClass,
  labelClass,
  linkActionClass,
  linkDangerClass,
  selectClass,
  tdClass,
  thClass,
  thRightClass,
} from "../lib/styles";
import { showApiError, toast } from "../lib/toast";
import { buildListUrl } from "../lib/url";
import { useDocumentTitle } from "../lib/use-document-title";
import { useUiStore } from "../stores/uiStore";
import type { IBindingListResponse, IBindingOut, IProjectListResponse } from "../types/api";
import ConfirmDialog from "../components/ConfirmDialog";
import EmptyState from "../components/EmptyState";
import FallbackConfigModal from "../components/FallbackConfigModal";
import Modal from "../components/Modal";
import PageHeader from "../components/PageHeader";
import { SkeletonTableRows } from "../components/Skeleton";

type ModalMode = { type: "create" } | { type: "edit"; row: IBindingOut };

function formatCooldownRemaining(cooldownUntil: string | null): string {
  if (!cooldownUntil) return "";
  const remaining = new Date(cooldownUntil).getTime() - Date.now();
  if (remaining <= 0) return "";
  const seconds = Math.ceil(remaining / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m ${secs}s`;
}

function BindingStatusBadge({ row }: { row: IBindingOut }) {
  const isCooling = row.cooldown_until && new Date(row.cooldown_until) > new Date();
  const hasFailures = row.consecutive_failures > 3;

  if (hasFailures) {
    return (
      <span className="rounded-md px-2 py-0.5 text-xs font-medium bg-red-100 text-red-900">
        Failed ({row.consecutive_failures})
      </span>
    );
  }
  if (isCooling) {
    const remaining = formatCooldownRemaining(row.cooldown_until);
    return (
      <span className="rounded-md px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-900">
        Cooling ({remaining})
      </span>
    );
  }
  return (
    <span className="rounded-md px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-900">
      Active
    </span>
  );
}

function FallbackChainBadge({ chain }: { chain: string[] | null }) {
  if (!chain || chain.length === 0) {
    return <span className="text-neutral-400">—</span>;
  }
  const display = chain.slice(0, 2);
  const extra = chain.length > 2 ? ` +${chain.length - 2}` : "";
  return (
    <span className="font-mono text-xs text-neutral-700">
      [{display.join(", ")}{extra}]
    </span>
  );
}


export default function BindingsPage() {
  useDocumentTitle("绑定关系");
  const queryClient = useQueryClient();
  const activeProjectId = useUiStore((s) => s.activeProjectId);
  const isAdmin = useUiStore((s) => s.vaultRole) === "admin";

  const listUrl = useMemo(() => buildListUrl("/api/bindings", { projectId: activeProjectId }), [activeProjectId]);

  const listQuery = useQuery({
    queryKey: ["bindings", listUrl],
    queryFn: () => apiRequest<IBindingListResponse>(listUrl),
  });

  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => apiRequest<IProjectListResponse>("/api/projects?limit=200"),
  });

  const [modal, setModal] = useState<ModalMode | null>(null);
  const [formService, setFormService] = useState("");
  const [formRefKey, setFormRefKey] = useState("");
  const [formAuthHeader, setFormAuthHeader] = useState("");
  const [formProjectId, setFormProjectId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<IBindingOut | null>(null);
  const [fallbackTarget, setFallbackTarget] = useState<IBindingOut | null>(null);

  const createMutation = useMutation({
    mutationFn: (body: {
      service_name: string;
      secret_ref_key: string;
      project_id: string | null;
      auth_header: string | null;
    }) =>
      apiRequest<IBindingOut>("/api/bindings", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bindings"] });
      closeModal();
      toast.success("绑定已创建。");
    },
    onError: (e: Error) => {
      setFormError(e.message);
      showApiError(e);
    },
  });

  const patchMutation = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: {
        service_name?: string;
        secret_ref_key?: string;
        project_id?: string | null;
        auth_header?: string | null;
      };
    }) =>
      apiRequest<IBindingOut>(`/api/bindings/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bindings"] });
      closeModal();
      toast.success("绑定已更新。");
    },
    onError: (e: Error) => {
      setFormError(e.message);
      showApiError(e);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/api/bindings/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bindings"] });
      setDeleteTarget(null);
      toast.success("绑定已删除。");
    },
    onError: (e: Error) => showApiError(e),
  });

  const openCreate = () => {
    setFormService("");
    setFormRefKey("");
    setFormAuthHeader("");
    setFormProjectId(activeProjectId);
    setFormError(null);
    setModal({ type: "create" });
  };

  const openEdit = (row: IBindingOut) => {
    setFormService(row.service_name);
    setFormRefKey(row.secret_ref_key);
    setFormAuthHeader(row.auth_header ?? "");
    setFormProjectId(row.project_id);
    setFormError(null);
    setModal({ type: "edit", row });
  };

  const closeModal = () => {
    setModal(null);
    setFormError(null);
  };

  const onSubmitModal = (e: FormEvent) => {
    e.preventDefault();
    const service_name = formService.trim();
    const secret_ref_key = formRefKey.trim();
    if (!service_name || !secret_ref_key) {
      setFormError("服务名称和密钥引用键为必填项。");
      return;
    }
    const auth_raw = formAuthHeader.trim();
    const auth_header = auth_raw || null;
    const project_id = formProjectId;

    if (modal?.type === "create") {
      createMutation.mutate({ service_name, secret_ref_key, project_id, auth_header });
    } else if (modal?.type === "edit") {
      patchMutation.mutate({
        id: modal.row.id,
        body: { service_name, secret_ref_key, project_id, auth_header },
      });
    }
  };

  const items = listQuery.data?.items ?? [];
  const projectOptions = projectsQuery.data?.items ?? [];
  const busy = createMutation.isPending || patchMutation.isPending;

  return (
    <div className="p-8">
      <PageHeader
        title="绑定关系"
        description="将服务名称映射到密钥引用。「已解析」表示存在匹配的已启用密钥。"
        action={isAdmin ? (
          <button type="button" onClick={openCreate} className={btnPrimaryClass}>
            添加绑定
          </button>
        ) : undefined}
      />

      {listQuery.error ? (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {getErrorMessage(listQuery.error)}
        </p>
      ) : null}

      {!listQuery.isLoading && items.length > 0 ? (
        <p className="mt-6 text-xs text-neutral-500">共 {listQuery.data?.total ?? items.length} 条</p>
      ) : null}
      <div className={`${items.length > 0 ? "mt-2" : "mt-6"} overflow-x-auto`}>
        <table className="w-full border-collapse text-sm">
          <thead className="bg-neutral-100">
            <tr>
              <th className={thClass}>
                服务
              </th>
              <th className={thClass}>
                密钥引用
              </th>
              <th className={thClass}>
                已解析
              </th>
              <th className={thClass}>
                认证头
              </th>
              <th className={thClass}>
                Fallback
              </th>
              <th className={thClass}>
                状态
              </th>
              <th className={thRightClass}>
                操作
              </th>
            </tr>
          </thead>
          <tbody>
            {listQuery.isLoading ? (
              <SkeletonTableRows cols={7} rows={3} />
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={7} className="border border-neutral-200 p-0">
                  <EmptyState
                    title="未找到绑定"
                    description="当前项目下没有绑定。创建一个来映射服务到密钥。"
                    action={isAdmin ? (
                      <button type="button" onClick={openCreate} className={btnPrimaryClass}>
                        添加绑定
                      </button>
                    ) : undefined}
                  />
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr key={row.id} className="transition-colors hover:bg-neutral-50">
                  <td className={`${tdClass} font-medium text-neutral-900`}>
                    {row.service_name}
                  </td>
                  <td className={`${tdClass} font-mono text-neutral-800`}>
                    {row.secret_ref_key}
                  </td>
                  <td className={tdClass}>
                    <span
                      className={clsx(
                        "rounded-md px-2 py-0.5 text-xs font-medium",
                        row.resolved
                          ? "bg-emerald-100 text-emerald-900"
                          : "bg-red-100 text-red-900",
                      )}
                    >
                      {row.resolved ? "是" : "否"}
                    </span>
                  </td>
                  <td className={`${tdClass} font-mono text-xs text-neutral-700`}>
                    {row.auth_header ?? "\u2014"}
                  </td>
                  <td className={tdClass}>
                    <button
                      type="button"
                      onClick={() => setFallbackTarget(row)}
                      className="hover:underline"
                    >
                      <FallbackChainBadge chain={row.fallback_chain} />
                    </button>
                  </td>
                  <td className={tdClass}>
                    <BindingStatusBadge row={row} />
                  </td>
                  <td className={`${tdClass} text-right`}>
                    {isAdmin ? (
                      <>
                        <button type="button" onClick={() => openEdit(row)} className={linkActionClass}>
                          编辑
                        </button>
                        <span className="mx-2 text-neutral-300">|</span>
                        <button type="button" onClick={() => setDeleteTarget(row)} disabled={deleteMutation.isPending} className={linkDangerClass}>
                          删除
                        </button>
                      </>
                    ) : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Modal
        open={modal !== null}
        onClose={closeModal}
        title={modal?.type === "create" ? "新建绑定" : "编辑绑定"}
        titleId="binding-modal-title"
      >
        <form onSubmit={onSubmitModal} className="mt-4 space-y-3">
          <div>
            <label htmlFor="b-svc" className={labelClass}>服务名称</label>
            <input id="b-svc" value={formService} onChange={(e) => setFormService(e.target.value)} className={`mt-1 ${inputClass}`} />
          </div>
          <div>
            <label htmlFor="b-ref" className={labelClass}>密钥引用键（点分命名法）</label>
            <input id="b-ref" value={formRefKey} onChange={(e) => setFormRefKey(e.target.value)} className={`mt-1 ${inputMonoClass}`} />
          </div>
          <div>
            <label htmlFor="b-auth" className={labelClass}>认证头名称（可选）</label>
            <input id="b-auth" value={formAuthHeader} onChange={(e) => setFormAuthHeader(e.target.value)} placeholder="Authorization" className={`mt-1 ${inputMonoClass}`} />
          </div>
          <div>
            <label htmlFor="b-pid" className={labelClass}>项目</label>
            <select id="b-pid" value={formProjectId ?? ""} onChange={(e) => setFormProjectId(e.target.value === "" ? null : e.target.value)} className={`mt-1 ${selectClass}`}>
              <option value="">全局（无项目）</option>
              {projectOptions.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          {formError ? <p role="alert" className="text-sm text-red-600">{formError}</p> : null}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={closeModal} className={btnSecondaryClass}>取消</button>
            <button type="submit" disabled={busy} className={btnPrimaryClass}>{busy ? "保存中…" : "保存"}</button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        title="删除绑定"
        message={`确定要删除绑定「${deleteTarget?.service_name}」吗？此操作不可撤销。`}
        confirmLabel="删除"
        isDestructive
        isPending={deleteMutation.isPending}
      />

      <FallbackConfigModal
        open={fallbackTarget !== null}
        binding={fallbackTarget}
        allBindings={items}
        onClose={() => setFallbackTarget(null)}
      />
    </div>
  );
}
