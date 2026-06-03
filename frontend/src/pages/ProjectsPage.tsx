import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { apiRequest, getErrorMessage } from "../lib/api";
import { showApiError, toast } from "../lib/toast";
import {
  btnPrimaryClass,
  btnSecondaryClass,
  inputClass,
  labelClass,
  linkActionClass,
  linkDangerClass,
  tdClass,
  thClass,
  thRightClass,
} from "../lib/styles";
import { useDocumentTitle } from "../lib/use-document-title";
import type { IProjectListResponse, IProjectOut } from "../types/api";
import ConfirmDialog from "../components/ConfirmDialog";
import EmptyState from "../components/EmptyState";
import Modal from "../components/Modal";
import PageHeader from "../components/PageHeader";
import { SkeletonTableRows } from "../components/Skeleton";
import { useUiStore } from "../stores/uiStore";

type ModalMode = { type: "create" } | { type: "edit"; project: IProjectOut };

export default function ProjectsPage() {
  useDocumentTitle("项目");
  const queryClient = useQueryClient();
  const isAdmin = useUiStore((s) => s.vaultRole) === "admin";
  const [modal, setModal] = useState<ModalMode | null>(null);
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<IProjectOut | null>(null);

  const listQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => apiRequest<IProjectListResponse>("/api/projects?limit=200"),
  });

  const createMutation = useMutation({
    mutationFn: (body: { name: string; description: string | null }) =>
      apiRequest<IProjectOut>("/api/projects", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      closeModal();
      toast.success("项目已创建。");
    },
    onError: (e: Error) => {
      setFormError(e.message);
      showApiError(e);
    },
  });

  const patchMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { name: string; description: string | null } }) =>
      apiRequest<IProjectOut>(`/api/projects/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      closeModal();
      toast.success("项目已更新。");
    },
    onError: (e: Error) => {
      setFormError(e.message);
      showApiError(e);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/api/projects/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      setDeleteTarget(null);
      toast.success("项目已删除。");
    },
    onError: (e: Error) => showApiError(e),
  });

  const openCreate = () => {
    setFormName("");
    setFormDescription("");
    setFormError(null);
    setModal({ type: "create" });
  };

  const openEdit = (project: IProjectOut) => {
    setFormName(project.name);
    setFormDescription(project.description ?? "");
    setFormError(null);
    setModal({ type: "edit", project });
  };

  const closeModal = () => {
    setModal(null);
    setFormError(null);
  };

  const onSubmitModal = (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const name = formName.trim();
    if (!name) {
      setFormError("名称为必填项。");
      return;
    }
    const description = formDescription.trim() || null;
    if (modal?.type === "create") {
      createMutation.mutate({ name, description });
    } else if (modal?.type === "edit") {
      patchMutation.mutate({
        id: modal.project.id,
        body: { name, description },
      });
    }
  };

  const items = listQuery.data?.items ?? [];
  const busy = createMutation.isPending || patchMutation.isPending;

  return (
    <div className="p-8">
      <PageHeader
        title="项目"
        description="创建和管理项目。"
        action={isAdmin ? (
          <button type="button" onClick={openCreate} className={btnPrimaryClass}>
            新建项目
          </button>
        ) : undefined}
      />

      {listQuery.error ? (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {getErrorMessage(listQuery.error)}
        </p>
      ) : null}

      {!listQuery.isLoading && items.length > 0 ? (
        <p className="mt-6 text-xs text-neutral-500">共 {items.length} 个项目</p>
      ) : null}
      <div className={`${items.length > 0 ? "mt-2" : "mt-6"} overflow-x-auto`}>
        <table className="w-full border-collapse text-sm">
          <thead className="bg-neutral-100">
            <tr>
              <th className={thClass}>
                名称
              </th>
              <th className={thClass}>
                描述
              </th>
              <th className={thClass}>
                更新时间
              </th>
              <th className={thRightClass}>
                操作
              </th>
            </tr>
          </thead>
          <tbody>
            {listQuery.isLoading ? (
              <SkeletonTableRows cols={4} rows={3} />
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={4} className="border border-neutral-200 p-0">
                  <EmptyState
                    title="暂无项目"
                    description="创建项目来组织你的身份信息、密钥和绑定关系。"
                    action={isAdmin ? (
                      <button type="button" onClick={openCreate} className={btnPrimaryClass}>
                        创建第一个项目
                      </button>
                    ) : undefined}
                  />
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr key={row.id} className="transition-colors hover:bg-neutral-50">
                  <td className={`${tdClass} font-medium text-neutral-900`}>
                    {row.name}
                  </td>
                  <td className={`${tdClass} max-w-md truncate text-neutral-700`}>
                    {row.description ?? "\u2014"}
                  </td>
                  <td className={`${tdClass} whitespace-nowrap text-neutral-600`}>
                    {new Date(row.updated_at).toLocaleString()}
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
        title={modal?.type === "create" ? "新建项目" : "编辑项目"}
        titleId="project-modal-title"
        maxWidth="max-w-md"
      >
        <form onSubmit={onSubmitModal} className="mt-4 space-y-3">
          <div>
            <label htmlFor="project-name" className={labelClass}>名称</label>
            <input id="project-name" value={formName} onChange={(e) => setFormName(e.target.value)} className={`mt-1 ${inputClass}`} autoComplete="off" />
          </div>
          <div>
            <label htmlFor="project-description" className={labelClass}>描述</label>
            <textarea id="project-description" value={formDescription} onChange={(e) => setFormDescription(e.target.value)} rows={3} className={`mt-1 ${inputClass}`} />
          </div>
          {formError ? (
            <p role="alert" className="text-sm text-red-600">{formError}</p>
          ) : null}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={closeModal} className={btnSecondaryClass}>取消</button>
            <button type="submit" disabled={busy} className={btnPrimaryClass}>
              {busy ? "保存中…" : "保存"}
            </button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        title="删除项目"
        message={`确定要删除「${deleteTarget?.name}」吗？此操作不可撤销。`}
        confirmLabel="删除"
        isDestructive
        isPending={deleteMutation.isPending}
      />
    </div>
  );
}
