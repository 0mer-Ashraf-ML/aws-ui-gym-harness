/**
 * Composite hook for timeline monitoring
 * 
 * ⚠️ WEBSOCKET DISABLED DUE TO SERVER OVERLOAD ⚠️
 * Using REST polling for live iterations until WebSocket is fixed
 */

import { useTimeline } from "./useTimeline";
import type { TimelineEntryUnion, ActionEntry, ConnectionState } from "../types";

interface UseTimelineMonitoringOptions {
  enabled?: boolean;
  iterationStatus?: string;
}

interface UseTimelineMonitoringReturn {
  entries: TimelineEntryUnion[];
  actions: ActionEntry[];
  isLoading: boolean;
  error: Error | null;
  isLive: boolean;
  connectionState: ConnectionState;
  refetch: () => void;
}

export const useTimelineMonitoring = (
  executionId: string | undefined,
  iterationId: string | undefined,
  options: UseTimelineMonitoringOptions = {}
): UseTimelineMonitoringReturn => {
  const { enabled = true, iterationStatus } = options;

  // Determine if iteration is still executing
  const isExecuting = iterationStatus === "executing" || iterationStatus === "pending";
  
  // Fetch timeline via REST with polling for executing iterations
  const {
    entries: restEntries,
    isLoading,
    error,
    refetch,
  } = useTimeline(executionId, iterationId, {
    enabled,
    // Poll every 3 seconds for executing iterations, no polling for completed
    refetchInterval: isExecuting ? 3000 : undefined,
  });

  // Mock connection state (no WebSocket)
  const connectionState: ConnectionState = {
    status: isExecuting ? "connected" : "disconnected",
    error: undefined,
  };

  // Filter actions for playback
  const actions = restEntries.filter(
    (entry): entry is ActionEntry => entry.entry_type === "action"
  );

  return {
    entries: restEntries,
    actions,
    isLoading,
    error,
    isLive: isExecuting,
    connectionState,
    refetch,
  };
};

