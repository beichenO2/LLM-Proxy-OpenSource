import { toast as sonnerToast } from "sonner";

export const toast = sonnerToast;

export function showApiError(err: unknown): void {
  const message = err instanceof Error ? err.message : String(err);
  sonnerToast.error(message);
}
