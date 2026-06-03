import { btnSecondaryClass } from "../lib/styles";
import Modal from "./Modal";

interface IConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isDestructive?: boolean;
  isPending?: boolean;
}

export default function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = "确认",
  cancelLabel = "取消",
  isDestructive = false,
  isPending = false,
}: IConfirmDialogProps) {
  return (
    <Modal open={open} onClose={onClose} title={title} maxWidth="max-w-sm">
      <p className="mt-2 text-sm text-neutral-600">{message}</p>
      <div className="mt-5 flex justify-end gap-2">
        <button type="button" onClick={onClose} className={btnSecondaryClass}>
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={isPending}
          className={`rounded-md px-3 py-2 text-sm font-medium text-white disabled:opacity-50 ${
            isDestructive
              ? "bg-red-600 hover:bg-red-700"
              : "bg-neutral-900 hover:bg-neutral-800"
          }`}
        >
          {isPending ? "删除中…" : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
