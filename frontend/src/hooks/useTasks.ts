import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { taskApi } from "../services/api";
import type { Task, TaskCreateRequest, TaskUpdateRequest } from "../types";

/**
 * Hook to fetch all tasks
 */
export const useTasks = (params?: {
  skip?: number;
  limit?: number;
  gym_id?: string;
}) => {
  return useQuery({
    queryKey: ["tasks", params],
    queryFn: () => taskApi.getAll(params),
    select: (data) => data.tasks, // Extract tasks array from TaskListResponse
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to fetch a single task by UUID
 */
export const useTask = (uuid: string) => {
  return useQuery({
    queryKey: ["tasks", uuid],
    queryFn: () => taskApi.getById(uuid),
    enabled: !!uuid,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to create a new task
 */
export const useCreateTask = (options?: {
  onSuccess?: (task: Task) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (taskData: TaskCreateRequest) => taskApi.create(taskData),
    onSuccess: (newTask) => {
      // Invalidate and refetch tasks list
      queryClient.invalidateQueries({ queryKey: ["tasks"] });

      // Add the new task to the cache
      queryClient.setQueryData(["tasks", newTask.uuid], newTask);

      // Update the tasks list cache if it exists
      queryClient.setQueryData<Task[]>(["tasks"], (oldData) => {
        if (!oldData) return [newTask];
        return [...oldData, newTask];
      });

      // Also invalidate gym-specific queries
      queryClient.invalidateQueries({
        queryKey: ["tasks", { gym_id: newTask.gym_id }],
      });

      // Invalidate gym list with task counts to update the counts
      queryClient.invalidateQueries({
        queryKey: ["gyms", "with-task-counts"],
      });

      // Call the success callback if provided
      options?.onSuccess?.(newTask);
    },
    onError: (error) => {
      console.error("Failed to create task:", error);
      // Call the error callback if provided
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to update an existing task
 */
export const useUpdateTask = (options?: {
  onSuccess?: (task: Task) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ uuid, ...taskData }: { uuid: string } & TaskUpdateRequest) =>
      taskApi.update(uuid, taskData),
    onSuccess: (updatedTask) => {
      // Update the specific task in cache
      queryClient.setQueryData(["tasks", updatedTask.uuid], updatedTask);

      // Update the tasks list cache
      queryClient.setQueryData<Task[]>(["tasks"], (oldData) => {
        if (!oldData) return [updatedTask];
        return oldData.map((task) =>
          task.uuid === updatedTask.uuid ? updatedTask : task,
        );
      });

      // Invalidate queries to ensure consistency
      queryClient.invalidateQueries({ queryKey: ["tasks"] });

      // Call the success callback if provided
      options?.onSuccess?.(updatedTask);
    },
    onError: (error) => {
      console.error("Failed to update task:", error);
      // Call the error callback if provided
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to delete a task
 */
export const useDeleteTask = (options?: {
  onSuccess?: (deletedUuid: string) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (uuid: string) => taskApi.delete(uuid),
    onSuccess: (_, deletedUuid) => {
      // Remove the task from specific cache
      queryClient.removeQueries({ queryKey: ["tasks", deletedUuid] });

      // Update the tasks list cache
      queryClient.setQueryData<Task[]>(["tasks"], (oldData) => {
        if (!oldData) return [];
        return oldData.filter((task) => task.uuid !== deletedUuid);
      });

      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["executions"] }); // Executions might be related to this task
      
      // Invalidate gym list with task counts to update the counts
      queryClient.invalidateQueries({
        queryKey: ["gyms", "with-task-counts"],
      });

      // Call the success callback if provided
      options?.onSuccess?.(deletedUuid);
    },
    onError: (error) => {
      console.error("Failed to delete task:", error);
      // Call the error callback if provided
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to get tasks count
 */
export const useTasksCount = (gym_id?: string) => {
  return useQuery({
    queryKey: ["tasks", "count", gym_id],
    queryFn: async () => {
      const params: Record<string, string | number | boolean> = gym_id
        ? { limit: 1, gym_id }
        : { limit: 1 };
      const response = await taskApi.getAll(params);
      return response.total;
    },
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
};

/**
 * Hook to get tasks by gym
 */
export const useTasksByGym = (gym_id: string) => {
  return useQuery({
    queryKey: ["tasks", "gym", gym_id],
    queryFn: () => taskApi.getAll({ gym_id }),
    select: (data) => data.tasks,
    enabled: !!gym_id,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to search tasks by prompt or task_id
 */
export const useSearchTasks = (searchTerm: string, gym_id?: string) => {
  return useQuery({
    queryKey: ["tasks", "search", searchTerm, gym_id],
    queryFn: () => taskApi.getAll(gym_id ? { gym_id } : undefined),
    select: (data) => {
      if (!searchTerm.trim()) return data.tasks;

      const term = searchTerm.toLowerCase().trim();
      return data.tasks.filter(
        (task) =>
          task.task_id.toLowerCase().includes(term) ||
          task.prompt.toLowerCase().includes(term) ||
          task.uuid.toLowerCase().includes(term),
      );
    },
    enabled: searchTerm.length >= 2, // Only search when we have at least 2 characters
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to prefetch a task (useful for hover effects)
 */
export const usePrefetchTask = () => {
  const queryClient = useQueryClient();

  return (uuid: string) => {
    queryClient.prefetchQuery({
      queryKey: ["tasks", uuid],
      queryFn: () => taskApi.getById(uuid),
      staleTime: 1000 * 60 * 5, // 5 minutes
    });
  };
};

/**
 * Hook to get tasks with gym information
 */
export const useTasksWithGyms = () => {
  return useQuery({
    queryKey: ["tasks", "with-gyms"],
    queryFn: async () => {
      const [tasksResponse] = await Promise.all([
        taskApi.getAll(),
        // We need to import gymApi for this, but it would create a circular dependency
        // So we'll keep this simple for now
        taskApi.getAll(),
      ]);

      // For now, just return tasks - we can enhance this later
      return tasksResponse.tasks;
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};
