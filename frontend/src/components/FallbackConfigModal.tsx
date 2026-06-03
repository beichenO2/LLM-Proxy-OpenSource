import { useEffect, useState } from "react";
import clsx from "clsx";
import {
  btnPrimaryClass,
  btnSecondaryClass,
  labelClass,
  selectClass,
} from "../lib/styles";
import { showApiError, toast } from "../lib/toast";
import Modal from "./Modal";
import FallbackChainEditor from "./FallbackChainEditor";
import {
  useBindingFallback,
  useBindingStatus,
  useSetFallbackConfig,
  useResetCooldown,
} from "../hooks/useBindingFallback";
import type { IBindingOut } from "../types/api";

interface FallbackConfigModalProps {
  open: boolean;
  binding: IBindingOut | null;
  allBindings: IBindingOut[];
  onClose: () => void;
}

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

export default function FallbackConfigModal({
  open,
  binding,
  allBindings,
  onClose,
}: FallbackConfigModalProps) {
  const [priority, setPriority] = useState(1);
  const [chain, setChain] = useState<string[]>([]);
  const [addError, setAddError] = useState<string | null>(null);
  const [selectedToAdd, setSelectedToAdd] = useState("");

  const fallbackQuery = useBindingFallback(open ? binding?.id ?? null : null);
  const statusQuery = useBindingStatus(open ? binding?.id ?? null : null);
  const setConfigMutation = useSetFallbackConfig();
  const resetCooldownMutation = useResetCooldown();

  useEffect(() => {
    if (fallbackQuery.data) {
      setPriority(fallbackQuery.data.priority ?? 1);
      setChain(fallbackQuery.data.fallback_chain ?? []);
    }
  }, [fallbackQuery.data]);

  useEffect(() => {
    setSelectedToAdd("");
    setAddError(null);
  }, [open]);

  const availableBindings = allBindings.filter(
    (b) =>
      b.id !== binding?.id &&
      !chain.includes(b.service_name)
  );

  const handleAddFallback = () => {
    if (!selectedToAdd) {
      setAddError("Please select a binding to add.");
      return;
    }
    setChain([...chain, selectedToAdd]);
    setSelectedToAdd("");
    setAddError(null);
  };

  const handleRemoveFromChain = (index: number) => {
    setChain(chain.filter((_, i) => i !== index));
  };

  const handleSave = () => {
    if (!binding) return;
    setConfigMutation.mutate(
      {
        bindingId: binding.id,
        config: {
          fallback_chain: chain.length > 0 ? chain : null,
          priority,
        },
      },
      {
        onSuccess: () => {
          toast.success("Fallback configuration saved.");
          onClose();
        },
        onError: (e: Error) => {
          showApiError(e);
        },
      }
    );
  };

  const handleResetCooldown = () => {
    if (!binding) return;
    resetCooldownMutation.mutate(binding.id, {
      onSuccess: () => {
        toast.success("Cooldown reset.");
      },
      onError: (e: Error) => {
        showApiError(e);
      },
    });
  };

  const status = statusQuery.data;
  const isCooling = status?.is_cooling_down ?? false;
  const cooldownRemaining = formatCooldownRemaining(status?.cooldown_until ?? null);
  const consecutiveFailures = status?.consecutive_failures ?? 0;

  const isLoading = fallbackQuery.isLoading;
  const isSaving = setConfigMutation.isPending;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Fallback Configuration"
      titleId="fallback-modal-title"
    >
      <div className="mt-4 space-y-4">
        {isLoading ? (
          <p className="text-sm text-neutral-500">Loading...</p>
        ) : (
          <>
            <div>
              <label htmlFor="fb-priority" className={labelClass}>
                Priority (Weight)
              </label>
              <div className="mt-1 flex items-center gap-3">
                <input
                  id="fb-priority"
                  type="range"
                  min={1}
                  max={100}
                  value={priority}
                  onChange={(e) => setPriority(Number(e.target.value))}
                  className="flex-1 h-2 bg-neutral-200 rounded-lg appearance-none cursor-pointer"
                />
                <span className="w-8 text-center font-mono text-sm">{priority}</span>
              </div>
            </div>

            <div>
              <label className={labelClass}>Fallback Chain (drag to reorder)</label>
              <div className="mt-2">
                <FallbackChainEditor
                  chain={chain}
                  onChange={setChain}
                  onRemove={handleRemoveFromChain}
                />
              </div>
            </div>

            <div>
              <label htmlFor="fb-add" className={labelClass}>
                Add Fallback
              </label>
              <div className="mt-1 flex gap-2">
                <select
                  id="fb-add"
                  value={selectedToAdd}
                  onChange={(e) => setSelectedToAdd(e.target.value)}
                  className={clsx(selectClass, "flex-1")}
                >
                  <option value="">Select a binding...</option>
                  {availableBindings.map((b) => (
                    <option key={b.id} value={b.service_name}>
                      {b.service_name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={handleAddFallback}
                  className={btnSecondaryClass}
                  disabled={availableBindings.length === 0}
                >
                  Add
                </button>
              </div>
              {addError ? (
                <p className="mt-1 text-xs text-red-600">{addError}</p>
              ) : null}
            </div>

            <div className="border-t border-neutral-200 pt-4">
              <label className={labelClass}>Runtime Status</label>
              <div className="mt-2 space-y-1 text-sm">
                <p>
                  <span className="text-neutral-500">Consecutive Failures:</span>{" "}
                  <span
                    className={clsx(
                      consecutiveFailures > 3 ? "text-red-600 font-medium" : ""
                    )}
                  >
                    {consecutiveFailures}
                  </span>
                </p>
                <p>
                  <span className="text-neutral-500">Cooldown:</span>{" "}
                  {isCooling ? (
                    <span className="text-amber-600 font-medium">
                      Cooling ({cooldownRemaining})
                    </span>
                  ) : (
                    <span className="text-emerald-600">Not in cooldown</span>
                  )}
                </p>
              </div>
              {isCooling && (
                <button
                  type="button"
                  onClick={handleResetCooldown}
                  disabled={resetCooldownMutation.isPending}
                  className={clsx(btnSecondaryClass, "mt-2")}
                >
                  {resetCooldownMutation.isPending ? "Resetting..." : "Reset Cooldown"}
                </button>
              )}
            </div>
          </>
        )}

        <div className="flex justify-end gap-2 pt-4 border-t border-neutral-200">
          <button type="button" onClick={onClose} className={btnSecondaryClass}>
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving || isLoading}
            className={btnPrimaryClass}
          >
            {isSaving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </Modal>
  );
}