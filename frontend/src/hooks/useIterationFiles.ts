import { useQuery } from "@tanstack/react-query";
import { fileApi } from "../services/api";
import type { ExecutionFilesResponse } from "../types";

/**
 * Hook for fetching files for a specific iteration
 */
export const useIterationFiles = (
  executionId: string | undefined,
  iterationId: string | undefined,
  format: "hierarchical" | "flat" = "hierarchical",
  options?: {
    enabled?: boolean;
    refetchIntervalMs?: number;
  },
) => {
  const { enabled = true, refetchIntervalMs } = options || {};

  return useQuery<ExecutionFilesResponse>({
    queryKey: ["iteration-files", executionId, iterationId, format],
    queryFn: () => fileApi.getIterationFiles(executionId!, iterationId!, format),
    enabled: !!executionId && !!iterationId && enabled,
    staleTime: 0,
    refetchInterval: enabled && refetchIntervalMs ? refetchIntervalMs : false,
    refetchOnWindowFocus: false,
    retry: (failureCount, error: any) => {
      // Don't retry on 404 errors (iteration folder not found)
      if (error?.status === 404 || error?.statusCode === 404) {
        return false;
      }
      // Retry up to 3 times for other errors
      return failureCount < 3;
    },
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
  });
};
