import { useQuery } from "@tanstack/react-query";
import { executionApi } from "../services/api";
import type { ExecutionProgress } from "../types";

/**
 * Polls execution progress (per-iteration status) for a given executionId.
 * Polling is active only when enabled.
 */
export const useExecutionProgress = (
  executionId: string | undefined,
  options?: {
    enabled?: boolean;
    refetchIntervalMs?: number;
  },
) => {
  const { enabled = true, refetchIntervalMs } = options || {};

  return useQuery<ExecutionProgress>({
    queryKey: ["execution-progress", executionId],
    queryFn: () => executionApi.getProgress(executionId!),
    enabled: !!executionId && enabled,
    staleTime: 0,
    gcTime: 0, // Don't cache - always fetch fresh
    refetchInterval: refetchIntervalMs || false,
    refetchOnWindowFocus: true, // Refetch when window regains focus
    refetchOnMount: true, // Always refetch on mount
    // Retry transient network errors with exponential backoff
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
  });
};
