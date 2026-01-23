import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { executionApi } from "../services/api";
import type {
  Execution,
  ExecutionListResponse,
  ExecutionWithStatus,
  ExecutionCreateRequest,
  ExecutionUpdateRequest,
  ModelType,
} from "../types";

/**
 * Hook to fetch all executions (runs)
 */
export const useRuns = (
  params?: {
    skip?: number;
    limit?: number;
    gym_id?: string;
    task_id?: string;
    model?: ModelType | ModelType[];
    status?: Execution["status"] | Execution["status"][];
    execution_type?: "batch" | "playground";
    search?: string;
    sort_by?: string;
    sort_order?: "asc" | "desc";
  },
  options?: {
    enableRealTimeSync?: boolean;
  },
) => {
  const { enableRealTimeSync = true } = options || {};

  return useQuery<ExecutionListResponse>({
    queryKey: ["runs", params],
    queryFn: async () => {
      console.log("🔄 Fetching runs from API with params:", params);
      try {
        const response = await executionApi.getAll(params);
        console.log("✅ API Response received:", {
          totalRuns: response.total,
          limit: response.limit,
          skip: response.skip,
          firstRun: response.executions?.[0],
        });
        return response;
      } catch (error) {
        console.error("❌ API Error in useRuns:", error);
        throw error;
      }
    },
    staleTime: 0, // Always fetch fresh data
    refetchInterval: enableRealTimeSync ? 3000 : false, // Simple 3-second polling
    refetchOnMount: true,
    refetchOnWindowFocus: true,
    placeholderData: (previousData) => previousData,
  });
};

/**
 * Hook to fetch a single execution (run) by UUID with enhanced status information
 */
export const useRun = (
  uuid: string,
  options?: {
    enableRealTimeSync?: boolean;
  },
) => {
  const { enableRealTimeSync = false } = options || {};

  return useQuery<ExecutionWithStatus>({
    queryKey: ["runs", uuid],
    queryFn: () => executionApi.getById(uuid),
    enabled: !!uuid,
    staleTime: enableRealTimeSync ? 0 : 1000 * 60 * 2, // 0 for real-time, 2 minutes for normal
    refetchInterval: enableRealTimeSync ? 2000 : false, // Poll every 2 seconds for real-time
    refetchOnMount: true,
    refetchOnWindowFocus: enableRealTimeSync,
  });
};

/**
 * Hook to create a new execution (run)
 */
export const useCreateRun = (options?: {
  onSuccess?: (run: Execution) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (executionData: ExecutionCreateRequest) => {
      console.log("🚀 Creating new run with data:", executionData);
      try {
        const result = await executionApi.create(executionData);
        console.log("✅ Create API response:", result);
        return result;
      } catch (error) {
        console.error("❌ Create API error:", error);
        throw error;
      }
    },
    onSuccess: (data) => {
      console.log("✅ Run created successfully:", {
        uuid: data.uuid,
        status: data.status,
        fullData: data,
      });

      // Check current cache before update
      const currentCache = queryClient.getQueryData(["runs", undefined]);
      console.log("📊 Current cache before invalidation:", {
        isArray: Array.isArray(currentCache),
        length: Array.isArray(currentCache) ? currentCache.length : 0,
      });

      // Update specific run cache
      queryClient.setQueryData(["runs", data.uuid], data);
      console.log("💾 Updated specific run cache for:", data.uuid);

      // Immediately invalidate and refetch runs to show new run
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      console.log("🔄 Invalidated runs queries - triggering refetch");

      // Verify invalidation worked
      setTimeout(() => {
        const newCache = queryClient.getQueryData(["runs", undefined]);
        console.log("🔍 Cache after invalidation:", {
          isArray: Array.isArray(newCache),
          length: Array.isArray(newCache) ? newCache.length : 0,
          hasNewRun: Array.isArray(newCache)
            ? newCache.some((run: any) => run.uuid === data.uuid)
            : false,
        });
      }, 1000);

      // Call the success callback if provided
      options?.onSuccess?.(data);
    },
    onError: (error) => {
      console.error("❌ Failed to create run:", error);
      // Call the error callback if provided
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to update an existing execution (run)
 */
export const useUpdateRun = (options?: {
  onSuccess?: (run: Execution) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      uuid,
      ...executionData
    }: { uuid: string } & ExecutionUpdateRequest) => {
      console.log("🚀 Updating run:", { uuid, executionData });
      try {
        const result = await executionApi.update(uuid, executionData);
        console.log("✅ Update API response:", result);
        return result;
      } catch (error) {
        console.error("❌ Update API error:", error);
        throw error;
      }
    },
    onSuccess: (data) => {
      console.log("✅ Run updated successfully:", {
        uuid: data.uuid,
        status: data.status,
        fullData: data,
      });

      // Update specific run cache
      queryClient.setQueryData(["runs", data.uuid], data);
      console.log("💾 Updated specific run cache for:", data.uuid);

      // Invalidate runs queries to refetch
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      console.log("🔄 Invalidated runs queries after update");

      // Call the success callback if provided
      options?.onSuccess?.(data);
    },
    onError: (error) => {
      console.error("❌ Failed to update run:", error);
      // Call the error callback if provided
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to delete an execution (run)
 */
export const useDeleteRun = (options?: {
  onSuccess?: (deletedUuid: string) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (uuid: string) => executionApi.delete(uuid),
    onSuccess: (_, deletedUuid) => {
      // Remove the execution from specific cache
      queryClient.removeQueries({ queryKey: ["runs", deletedUuid] });

      // Invalidate all runs queries to refetch fresh data
      queryClient.invalidateQueries({ queryKey: ["runs"] });

      // Call the success callback if provided
      options?.onSuccess?.(deletedUuid);
    },
    onError: (error) => {
      console.error("Failed to delete execution:", error);
      // Call the error callback if provided
      options?.onError?.(error as Error);
    },
    onSettled: (data, error, variables) => {
      console.log("🏁 Delete run mutation settled:", {
        success: !error,
        hasData: !!data,
        errorExists: !!error,
        deletedUuid: variables,
      });
    },
  });
};

/**
 * Hook to get executions count
 */
export const useRunsCount = (filters?: {
  gym_id?: string;
  task_id?: string;
  model?: ModelType;
    status?: "pending" | "executing" | "passed" | "failed" | "crashed" | "timeout";
}) => {
  return useQuery({
    queryKey: ["runs", "count", filters],
    queryFn: async () => {
      const params = { limit: 1, ...filters };
      const response = await executionApi.getAll(params);
      return response.total;
    },
    staleTime: 1000 * 60 * 1, // 1 minute
  });
};

/**
 * Hook to get executions by gym
 */
export const useRunsByGym = (gym_id: string) => {
  return useQuery({
    queryKey: ["runs", "gym", gym_id],
    queryFn: () => executionApi.getAll({ gym_id }),
    select: (data) => data.executions,
    enabled: !!gym_id,
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
};

/**
 * Hook to get executions by task
 */
export const useRunsByTask = (task_id: string) => {
  return useQuery({
    queryKey: ["runs", "task", task_id],
    queryFn: () => executionApi.getAll({ task_id }),
    select: (data) => data.executions,
    enabled: !!task_id,
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
};

/**
 * Hook to get executions by model
 */
export const useRunsByModel = (model: ModelType) => {
  return useQuery({
    queryKey: ["runs", "model", model],
    queryFn: () => executionApi.getAll({ model }),
    select: (data) => data.executions,
    enabled: !!model,
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
};

/**
 * Hook to get executions by status
 */
export const useRunsByStatus = (
  status: "pending" | "executing" | "passed" | "failed" | "crashed" | "timeout",
) => {
  return useQuery({
    queryKey: ["runs", "status", status],
    queryFn: () => executionApi.getAll({ status }),
    select: (data) => data.executions,
    enabled: !!status,
    staleTime: 1000 * 60 * 1, // 1 minute for real-time updates
  });
};

/**
 * Hook to search executions
 */
export const useSearchRuns = (
  searchTerm: string,
  filters?: {
    gym_id?: string;
    model?: ModelType;
    status?: "pending" | "executing" | "passed" | "failed" | "crashed" | "timeout";
  },
) => {
  return useQuery({
    queryKey: ["runs", "search", searchTerm, filters],
    queryFn: () => executionApi.getAll(filters),
    select: (data) => {
      if (!searchTerm.trim()) return data.executions;

      const term = searchTerm.toLowerCase().trim();
      return data.executions.filter(
        (execution) =>
          execution.uuid.toLowerCase().includes(term) ||
          execution.model.toLowerCase().includes(term) ||
          execution.status.toLowerCase().includes(term),
      );
    },
    enabled: searchTerm.length >= 2, // Only search when we have at least 2 characters
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
};

/**
 * Hook to get execution statistics
 */
export const useRunStatistics = (gym_id?: string) => {
  return useQuery({
    queryKey: ["runs", "statistics", gym_id],
    queryFn: async () => {
      const params = gym_id ? { gym_id } : undefined;
      const response = await executionApi.getAll(params);
      const executions = response.executions;

      return {
        total: response.total,
        byStatus: {
          pending: executions.filter((e) => e.status === "pending").length,
          executing: executions.filter((e) => e.status === "executing").length,
          passed: executions.filter((e) => e.status === "passed").length,
          failed: executions.filter((e) => e.status === "failed").length,
          crashed: executions.filter((e) => e.status === "crashed").length,
          timeout: executions.filter((e) => e.status === "timeout").length,
        },
        byModel: {
          openai: executions.filter((e) => e.model === "openai").length,
          anthropic: executions.filter((e) => e.model === "anthropic").length,
        },
        recentExecutions: executions
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime(),
          )
          .slice(0, 5),
      };
    },
    staleTime: 1000 * 60 * 1, // 1 minute
  });
};

/**
 * Hook to prefetch an execution (useful for hover effects)
 */
export const usePrefetchRun = () => {
  const queryClient = useQueryClient();

  return (uuid: string) => {
    queryClient.prefetchQuery({
      queryKey: ["runs", uuid],
      queryFn: () => executionApi.getById(uuid),
      staleTime: 1000 * 60 * 2, // 2 minutes
    });
  };
};

/**
 * WebSocket hook for real-time run status updates
 */
export const useRunsWebSocket = (enabled: boolean = true) => {
  return useQuery({
    queryKey: ["runs", "websocket"],
    queryFn: () => Promise.resolve(null),
    enabled,
    staleTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
};

// WebSocket connection hook (separated from useQuery)
export const useRunsWebSocketConnection = (enabled: boolean = true) => {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!enabled) return;

    let ws: WebSocket | null = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    const reconnectDelay = 3000;

    const connect = () => {
      try {
        // Replace with your actual WebSocket endpoint
        const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
        const wsUrl =
          import.meta.env.MODE === "production"
            ? `wss://${window.location.host}/ws/runs`
            : apiUrl.replace("http://", "ws://").replace("https://", "wss://") +
              "/ws/runs";

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          console.log("WebSocket connected for runs updates");
          reconnectAttempts = 0;
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            if (data.type === "run_status_update") {
              const updatedRun: Execution = data.run;

              // Update specific run cache
              queryClient.setQueryData(["runs", updatedRun.uuid], updatedRun);

              // Update main runs list cache
              queryClient.setQueryData<Execution[]>(
                ["runs", undefined],
                (oldData) => {
                  if (!oldData) return oldData;
                  return oldData.map((run) =>
                    run.uuid === updatedRun.uuid ? updatedRun : run,
                  );
                },
              );

              // Invalidate related queries for consistency
              queryClient.invalidateQueries({
                queryKey: ["runs", "status", updatedRun.status],
              });
            }
          } catch (error) {
            console.error("Error processing WebSocket message:", error);
          }
        };

        ws.onclose = (event) => {
          console.log("WebSocket disconnected:", event.code, event.reason);

          // Attempt to reconnect if not a normal closure
          if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            console.log(
              `Attempting to reconnect... (${reconnectAttempts}/${maxReconnectAttempts})`,
            );
            setTimeout(connect, reconnectDelay);
          }
        };

        ws.onerror = (error) => {
          console.error("WebSocket error:", error);
        };
      } catch (error) {
        console.error("Failed to establish WebSocket connection:", error);
      }
    };

    connect();

    // Cleanup function
    return () => {
      if (ws) {
        ws.close(1000, "Component unmounting");
      }
    };
  }, [enabled, queryClient]);
};

/**
 * Hook to manage run execution with WebSocket updates
 */
export const useRunExecution = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (execution: Execution) => {
      console.log(
        "🚀 Processing execution request:",
        execution.uuid,
        "Status:",
        execution.status,
      );

      try {
        // For completed executions, create new execution and delete old one (rerun)
        if (execution.status === "passed") {
          console.log(
            "🔄 Creating rerun for completed execution:",
            execution.uuid,
          );

          const rerunRequest: ExecutionCreateRequest = {
            gym_id: execution.gym_id,
            task_id: execution.task_id || undefined,
            number_of_iterations: execution.number_of_iterations,
            model: execution.model,
          };

          const result = await executionApi.create(rerunRequest);
          console.log("✅ Rerun created:", result.uuid);

          // Delete the old execution to maintain single-card UX
          try {
            await executionApi.delete(execution.uuid);
            console.log("✅ Old execution deleted:", execution.uuid);
          } catch (deleteError) {
            console.warn("⚠️ Failed to delete old execution:", deleteError);
            // Continue anyway - the rerun was successful
          }

          return result;
        }

        // For pending/failed/crashed executions, use execute endpoint directly
        else {
          console.log("▶️ Executing existing run:", execution.uuid);
          const result = await executionApi.execute(execution.uuid);
          console.log("✅ Execute API response:", result);
          return result;
        }
      } catch (error) {
        console.error("❌ Execute/Rerun API error:", error);

        // Enhanced error handling
        if (error instanceof Error) {
          const errorMessage = error.message.toLowerCase();

          if (errorMessage.includes("already executing")) {
            const friendlyError = new Error(
              "This execution is currently running. Please wait for it to complete before trying again.",
            );
            friendlyError.name = "AlreadyExecuting";
            throw friendlyError;
          }

          if (errorMessage.includes("not found")) {
            const friendlyError = new Error(
              "The execution could not be found. It may have been deleted.",
            );
            friendlyError.name = "ExecutionNotFound";
            throw friendlyError;
          }
        }

        throw error;
      }
    },
    onSettled: (data, error, originalExecution) => {
      if (error) {
        console.error("❌ Failed to start run execution:", error);
        return;
      }

      if (data && originalExecution) {
        const isRerun = originalExecution.status === "passed";
        console.log(
          `✅ ${isRerun ? "Rerun created" : "Execution started"}:`,
          data.uuid,
        );

        // Invalidate relevant queries to ensure fresh data
        queryClient.invalidateQueries({ queryKey: ["runs"] });
        console.log(
          `🔄 Invalidated runs queries after ${isRerun ? "rerun" : "execution"}`,
        );
      }
    },
  });
};

/**
 * Hook to poll for active executions (real-time updates)
 */
export const useActiveRuns = (enabled: boolean = true) => {
  return useQuery({
    queryKey: ["runs", "active"],
    queryFn: () => executionApi.getAll({ status: "executing" }),
    select: (data) => data.executions,
    enabled,
    refetchInterval: 2000, // Poll every 2 seconds for faster updates
    staleTime: 0, // Always fresh for real-time updates
  });
};

/**
 * Hook to sync executing runs status with main runs cache
 */
export const useRunsStatusSync = () => {
  return useQuery({
    queryKey: ["runs", "status-sync"],
    queryFn: () => executionApi.getAll({ status: "executing" }),
    select: (data: any) => data.executions,
    refetchInterval: 3000, // Poll every 3 seconds
    staleTime: 0,
    // Note: onSuccess is deprecated in React Query v5, using onSettled instead
  });
};

/**
 * Hook for comprehensive status tracking of all runs
 */
export const useRunsRealTimeSync = (enabled: boolean = true) => {
  return useQuery({
    queryKey: ["runs", "realtime-sync"],
    queryFn: async () => {
      // Get all runs to check for status changes
      const allRuns = await executionApi.getAll();
      return allRuns.executions;
    },
    enabled,
    refetchInterval: 5000, // Poll every 5 seconds for all runs
    staleTime: 0,
    // Note: onSuccess is deprecated in React Query v5, using onSettled instead
  });
};

/**
 * Hook to fetch unified progress for all playground executions
 * Similar to batch iteration summary but for playground executions
 */
type PlaygroundProgressParams = {
  skip?: number;
  limit?: number;
  search?: string;
  status?: Execution["status"][];
  model?: ModelType[];
  sort_by?: string;
  sort_order?: "asc" | "desc";
};

export const usePlaygroundProgress = (
  params?: PlaygroundProgressParams,
  options?: { enableRealTimeSync?: boolean }
) => {
  const { enableRealTimeSync = true } = options || {};

  return useQuery({
    queryKey: ["playground-progress", params],
    queryFn: async () => {
      console.log("🔄 Fetching playground progress from API with params:", params);
      try {
        const response = await executionApi.getPlaygroundProgress(params);
        console.log("✅ Playground progress API Response received:", {
          totalExecutions: response.total_executions,
          executionIds: Object.keys(response.execution_progress),
        });
        return response;
      } catch (error) {
        console.error("❌ API Error in usePlaygroundProgress:", error);
        throw error;
      }
    },
    staleTime: 0, // Always fetch fresh data
    refetchInterval: enableRealTimeSync ? 5000 : false, // Poll every 5 seconds if enabled
    refetchOnMount: true,
    refetchOnWindowFocus: true,
  });
};
