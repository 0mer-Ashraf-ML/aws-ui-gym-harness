/**
 * Hook for fetching action timeline via REST API
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { timelineApi } from "../services/api";
import type { TimelineResponse, ActionEntry } from "../types";

interface UseTimelineOptions {
  enabled?: boolean;
  refetchInterval?: number;
  live?: boolean;
}

interface UseTimelineReturn {
  timeline: TimelineResponse | undefined;
  entries: TimelineResponse["entries"];
  actions: ActionEntry[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}

export const useTimeline = (
  executionId: string | undefined,
  iterationId: string | undefined,
  options: UseTimelineOptions = {}
): UseTimelineReturn => {
  const { enabled = true, refetchInterval, live = false } = options;

  const {
    data,
    isLoading,
    error,
    refetch,
  }: UseQueryResult<TimelineResponse, Error> = useQuery({
    queryKey: ["timeline", executionId, iterationId, live],
    queryFn: () => {
      if (!executionId || !iterationId) {
        throw new Error("Execution ID and Iteration ID are required");
      }
      return timelineApi.getTimeline(executionId, iterationId, live);
    },
    enabled: enabled && !!executionId && !!iterationId,
    refetchInterval,
    staleTime: live ? 0 : 30000, // 30 seconds for non-live, always fresh for live
  });

  // Filter out only action entries for playback
  const actions = data?.entries.filter(
    (entry): entry is ActionEntry => entry.entry_type === "action"
  ) ?? [];

  return {
    timeline: data,
    entries: data?.entries ?? [],
    actions,
    isLoading,
    error: error as Error | null,
    refetch,
  };
};

