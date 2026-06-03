import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../lib/api";
import type { IBindingOut, IFallbackConfig, IBindingStatus } from "../types/api";

export function useBindingFallback(bindingId: string | null) {
  return useQuery({
    queryKey: ["binding-fallback", bindingId],
    queryFn: () => apiRequest<IFallbackConfig>(`/api/bindings/${bindingId}/fallback`),
    enabled: bindingId !== null,
  });
}

export function useBindingStatus(bindingId: string | null) {
  return useQuery({
    queryKey: ["binding-status", bindingId],
    queryFn: () => apiRequest<IBindingStatus>(`/api/bindings/${bindingId}/status`),
    enabled: bindingId !== null,
    refetchInterval: 5000,
  });
}

export function useSetFallbackConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      bindingId,
      config,
    }: {
      bindingId: string;
      config: IFallbackConfig;
    }) =>
      apiRequest<IBindingOut>(`/api/bindings/${bindingId}/fallback`, {
        method: "PUT",
        body: JSON.stringify(config),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["bindings"] });
      void queryClient.invalidateQueries({ queryKey: ["binding-fallback"] });
      void queryClient.invalidateQueries({ queryKey: ["binding-status"] });
    },
  });
}

export function useResetCooldown() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (bindingId: string) =>
      apiRequest<{ ok: boolean; binding_id: string }>(
        `/api/bindings/${bindingId}/reset-cooldown`,
        { method: "POST" }
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["binding-status"] });
      void queryClient.invalidateQueries({ queryKey: ["bindings"] });
    },
  });
}
