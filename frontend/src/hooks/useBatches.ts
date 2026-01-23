import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { batchApi } from "../services/api";
import type {
  Batch,
  BatchCreateRequest,
  BatchUpdateRequest,
  BatchIterationSummary,
} from "../types";

/**
 * Hook to fetch all batches
 */
export const useBatches = (
  params?: {
    page?: number;
    size?: number;
    gym_id?: string;
  },
  options?: {
    enableRealTimeSync?: boolean;
  },
) => {
  const { enableRealTimeSync = true } = options || {};

  return useQuery({
    queryKey: ["batches", params],
    queryFn: async () => {
      console.log("🔄 Fetching batches from API with params:", params);
      try {
        const response = await batchApi.getAll(params);
        console.log("✅ API Response received:", {
          totalBatches: response.batches?.length || 0,
          response: response,
          firstBatch: response.batches?.[0],
        });
        return response;
      } catch (error) {
        console.error("❌ API Error in useBatches:", error);
        throw error;
      }
    },
    staleTime: 0, // Always fetch fresh data
    refetchInterval: enableRealTimeSync ? 3000 : false, // Simple 3-second polling
    refetchOnMount: true,
    refetchOnWindowFocus: true,
  });
};

/**
 * Hook to fetch a single batch by ID
 */
export const useBatch = (batchId: string) => {
  return useQuery({
    queryKey: ["batch", batchId],
    queryFn: async () => {
      console.log("🔄 Fetching batch from API:", batchId);
      try {
        const batch = await batchApi.getById(batchId);
        console.log("✅ Batch API Response received:", batch);
        return batch;
      } catch (error) {
        console.error("❌ API Error in useBatch:", error);
        throw error;
      }
    },
    enabled: !!batchId,
    staleTime: 0,
    refetchInterval: 3000, // 3-second polling for real-time updates
    refetchOnMount: true,
    refetchOnWindowFocus: true,
  });
};

/**
 * Hook to fetch executions for a specific batch
 */
export const useBatchExecutions = (batchId: string) => {
  const queryClient = useQueryClient();

  return useQuery({
    queryKey: ["batch-executions", batchId],
    queryFn: async () => {
      console.log("🔄 Fetching batch executions from API:", batchId);
      try {
        const executions = await batchApi.getExecutions(batchId);
        console.log("✅ Batch Executions API Response received:", executions);
        queryClient.invalidateQueries({ queryKey: ["batch-iteration-summary", batchId] });
        return executions;
      } catch (error) {
        console.error("❌ API Error in useBatchExecutions:", error);
        throw error;
      }
    },
    enabled: !!batchId,
    staleTime: 0,
    refetchInterval: 3000, // 3-second polling for real-time updates
    refetchOnMount: true,
    refetchOnWindowFocus: true,
  });
};

/**
 * Hook to create a new batch
 */
export const useCreateBatch = (options?: {
  onSuccess?: (batch: Batch) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: BatchCreateRequest) => {
      console.log("🔄 Creating batch:", data);
      const batch = await batchApi.create(data);
      console.log("✅ Batch created:", batch);
      return batch;
    },
    onSuccess: (batch) => {
      // Invalidate and refetch batches
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      options?.onSuccess?.(batch);
    },
    onError: (error) => {
      console.error("❌ Error creating batch:", error);
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to update an existing batch
 */
export const useUpdateBatch = (options?: {
  onSuccess?: (batch: Batch) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { uuid: string } & BatchUpdateRequest) => {
      console.log("🔄 Updating batch:", data);
      const batch = await batchApi.update(data.uuid, data);
      console.log("✅ Batch updated:", batch);
      return batch;
    },
    onSuccess: (batch) => {
      // Invalidate and refetch batches
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      queryClient.invalidateQueries({ queryKey: ["batch", batch.uuid] });
      options?.onSuccess?.(batch);
    },
    onError: (error) => {
      console.error("❌ Error updating batch:", error);
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to execute a batch
 */
export const useExecuteBatch = (options?: {
  onSuccess?: (result: { message: string; batch_id: string; executions_count: number }) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (batchId: string) => {
      console.log("🔄 Executing batch:", batchId);
      const result = await batchApi.execute(batchId);
      console.log("✅ Batch executed:", result);
      return result;
    },
    onSuccess: (result) => {
      // Invalidate and refetch batches and batch executions
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      queryClient.invalidateQueries({ queryKey: ["batch", result.batch_id] });
      queryClient.invalidateQueries({ queryKey: ["batch-executions", result.batch_id] });
      options?.onSuccess?.(result);
    },
    onError: (error) => {
      console.error("❌ Error executing batch:", error);
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to delete a batch
 */
export const useDeleteBatch = (options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (batchId: string) => batchApi.delete(batchId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      console.error("Error deleting batch:", error);
      options?.onError?.(error);
    },
  });
};

/**
 * Hook to delete all batches (admin only)
 */
export const useDeleteAllBatches = (options?: {
  onSuccess?: (result: { message: string; deleted_count: number }) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => batchApi.deleteAll(),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      options?.onSuccess?.(result);
    },
    onError: (error: Error) => {
      console.error("Error deleting all batches:", error);
      options?.onError?.(error);
    },
  });
};

/**
 * Hook to fetch batch iteration summary with overall and per-execution breakdown
 * Automatically polls every 5 seconds when any execution is still executing
 */
export const useBatchIterationSummary = (batchId: string) => {
  return useQuery<BatchIterationSummary, Error>({
    queryKey: ["batch-iteration-summary", batchId],
    queryFn: async () => {
      console.log("🔄 Fetching batch iteration summary for:", batchId);
      try {
        const summary = await batchApi.getIterationSummary(batchId);
        console.log("✅ Batch iteration summary received:", summary);
        return summary;
      } catch (error) {
        console.error("❌ Error fetching batch iteration summary:", error);
        throw error;
      }
    },
    enabled: !!batchId,
    staleTime: 0,
    refetchInterval: (query) => {
      // Auto-refresh every 5 seconds if any execution is still executing
      const summary = query.state.data;
      const hasExecuting = (summary?.overall_summary?.iteration_counts?.executing ?? 0) > 0;
      return hasExecuting ? 5000 : false;
    },
    refetchOnMount: true,
    refetchOnWindowFocus: true,
  });
};

/**
 * Hook to fetch lightweight batch metadata for dropdowns/selection
 * No status calculation - optimized for Leaderboard and other selection UIs
 */
export const useBatchMetadata = (
  params?: {
    gym_id?: string;
    limit?: number;
  }
) => {
  return useQuery({
    queryKey: ["batch-metadata", params],
    queryFn: async () => {
      const batches = await batchApi.getMetadata(params);
      return batches;
    },
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
};
