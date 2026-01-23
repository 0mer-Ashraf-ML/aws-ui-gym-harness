/**
 * Hook for managing batch reports that are ready for download
 */

import { useQuery } from "@tanstack/react-query";
import type { UseQueryOptions } from "@tanstack/react-query";
import { batchApi } from "../services/api";

interface ReadyBatch {
  batch_id: string;
  batch_name: string;
  gym_id: string;
  number_of_iterations: number;
  is_read: boolean;
  created_at: string;
  updated_at: string;
}

interface ReadyReportsResponse {
  ready_batches: ReadyBatch[];
  count: number;
  unread_count: number;
}

/**
 * Hook to fetch all batches with ready reports
 * @param options Optional query options
 * @param refetchInterval Optional auto-refetch interval in milliseconds (default: 30000 = 30s)
 */
export function useReadyReports(
  options?: Omit<UseQueryOptions<ReadyReportsResponse, Error>, "queryKey" | "queryFn">,
  refetchInterval: number = 30000 // Auto-refresh every 30 seconds by default
) {
  return useQuery<ReadyReportsResponse, Error>({
    queryKey: ["ready-reports"],
    queryFn: () => batchApi.getReadyReports(),
    refetchInterval, // Automatically refetch to keep notifications up to date
    refetchIntervalInBackground: false, // Only refetch when tab is active
    staleTime: 15000, // Consider data stale after 15 seconds
    ...options,
  });
}

export type { ReadyBatch, ReadyReportsResponse };

