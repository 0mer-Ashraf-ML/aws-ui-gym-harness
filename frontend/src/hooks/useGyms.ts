import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { gymApi } from "../services/api";
import type { Gym, GymCreateRequest, GymUpdateRequest } from "../types";

/**
 * Hook to fetch all gyms
 */
export const useGyms = (params?: {
  skip?: number;
  limit?: number;
  include_tasks?: boolean;
}) => {
  return useQuery({
    queryKey: ["gyms", params],
    queryFn: () => gymApi.getAll(params),
    select: (data) => data.gyms, // Extract gyms array from GymListResponse
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to fetch all gyms with task counts
 */
export const useGymsWithTaskCounts = (params?: {
  skip?: number;
  limit?: number;
}) => {
  return useQuery({
    queryKey: ["gyms", "with-task-counts", params],
    queryFn: () => gymApi.getAllWithTaskCounts(params),
    select: (data) => data.gyms, // Extract gyms array from GymListWithTaskCountResponse
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to fetch a single gym by UUID
 */
export const useGym = (uuid: string) => {
  return useQuery({
    queryKey: ["gyms", uuid],
    queryFn: () => gymApi.getById(uuid),
    enabled: !!uuid,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to create a new gym
 */
export const useCreateGym = (options?: {
  onSuccess?: (gym: Gym) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (gymData: GymCreateRequest) => gymApi.create(gymData),
    onSuccess: (newGym) => {
      // Invalidate and refetch gyms list
      queryClient.invalidateQueries({ queryKey: ["gyms"] });

      // Add the new gym to the cache
      queryClient.setQueryData(["gyms", newGym.uuid], newGym);

      // Update the gyms list cache if it exists
      queryClient.setQueryData<Gym[]>(["gyms"], (oldData) => {
        if (!oldData) return [newGym];
        return [...oldData, newGym];
      });

      // Call the success callback if provided
      options?.onSuccess?.(newGym);
    },
    onError: (error: any) => {
      console.error("Failed to create gym:", error);
      
      // Extract user-friendly error message for duplicate URL errors
      let errorMessage = error?.message || "Failed to create gym";
      if (error?.response?.data?.detail) {
        const detail = error.response.data.detail;
        // Check if it's a duplicate URL error
        if (detail.includes("base URL") && detail.includes("already exists")) {
          errorMessage = detail;
        } else if (detail.includes("name") && detail.includes("already exists")) {
          errorMessage = detail;
        } else {
          errorMessage = detail;
        }
      }
      
      // Call the error callback with enhanced error message
      const enhancedError = new Error(errorMessage);
      options?.onError?.(enhancedError);
    },
  });
};

/**
 * Hook to update an existing gym
 */
export const useUpdateGym = (options?: {
  onSuccess?: (gym: Gym) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ uuid, ...gymData }: { uuid: string } & GymUpdateRequest) =>
      gymApi.update(uuid, gymData),
    onSuccess: (updatedGym) => {
      // Update the specific gym in cache
      queryClient.setQueryData(["gyms", updatedGym.uuid], updatedGym);

      // Update the gyms list cache
      queryClient.setQueryData<Gym[]>(["gyms"], (oldData) => {
        if (!oldData) return [updatedGym];
        return oldData.map((gym) =>
          gym.uuid === updatedGym.uuid ? updatedGym : gym,
        );
      });

      // Invalidate queries to ensure consistency
      queryClient.invalidateQueries({ queryKey: ["gyms"] });

      // Call the success callback if provided
      options?.onSuccess?.(updatedGym);
    },
    onError: (error: any) => {
      console.error("Failed to update gym:", error);
      
      // Extract user-friendly error message for duplicate URL errors
      let errorMessage = error?.message || "Failed to update gym";
      if (error?.response?.data?.detail) {
        const detail = error.response.data.detail;
        // Check if it's a duplicate URL error
        if (detail.includes("base URL") && detail.includes("already exists")) {
          errorMessage = detail;
        } else if (detail.includes("name") && detail.includes("already exists")) {
          errorMessage = detail;
        } else {
          errorMessage = detail;
        }
      }
      
      // Call the error callback with enhanced error message
      const enhancedError = new Error(errorMessage);
      options?.onError?.(enhancedError);
    },
  });
};

/**
 * Hook to delete a gym
 */
export const useDeleteGym = (options?: {
  onSuccess?: (deletedUuid: string) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (uuid: string) => gymApi.delete(uuid),
    onSuccess: (_, deletedUuid) => {
      // Remove the gym from specific cache
      queryClient.removeQueries({ queryKey: ["gyms", deletedUuid] });

      // Update the gyms list cache
      queryClient.setQueryData<Gym[]>(["gyms"], (oldData) => {
        if (!oldData) return [];
        return oldData.filter((gym) => gym.uuid !== deletedUuid);
      });

      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: ["gyms"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] }); // Tasks might be related to this gym
      queryClient.invalidateQueries({ queryKey: ["executions"] }); // Executions might be related to this gym

      // Call the success callback if provided
      options?.onSuccess?.(deletedUuid);
    },
    onError: (error) => {
      console.error("Failed to delete gym:", error);
      // Call the error callback if provided
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to get gyms count
 */
export const useGymsCount = () => {
  return useQuery({
    queryKey: ["gyms", "count"],
    queryFn: async () => {
      const response = await gymApi.getAll({ limit: 1 });
      return response.total;
    },
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
};

/**
 * Hook to search gyms by name or description
 */
export const useSearchGyms = (searchTerm: string) => {
  return useQuery({
    queryKey: ["gyms", "search", searchTerm],
    queryFn: () => gymApi.getAll(),
    select: (data) => {
      if (!searchTerm.trim()) return data.gyms;

      const term = searchTerm.toLowerCase().trim();
      return data.gyms.filter(
        (gym) =>
          gym.name.toLowerCase().includes(term) ||
          gym.description?.toLowerCase().includes(term) ||
          gym.base_url.toLowerCase().includes(term),
      );
    },
    enabled: searchTerm.length >= 2, // Only search when we have at least 2 characters
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to prefetch a gym (useful for hover effects)
 */
export const usePrefetchGym = () => {
  const queryClient = useQueryClient();

  return (uuid: string) => {
    queryClient.prefetchQuery({
      queryKey: ["gyms", uuid],
      queryFn: () => gymApi.getById(uuid),
      staleTime: 1000 * 60 * 5, // 5 minutes
    });
  };
};
