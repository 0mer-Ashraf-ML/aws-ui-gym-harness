import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { Model, ModelType } from "../types";

// TODO: Replace with real API when backend endpoints are available
// For now, this is a placeholder implementation

// Mock data for development
const mockModels: Model[] = [
  {
    id: "1",
    name: "Computer Use Preview",
    type: "openai",
    description: "OpenAI's Computer Use Preview for advanced computer interaction tasks",
    api_key: "sk-proj-***...***",
    created_at: "2024-01-10T08:00:00Z",
    updated_at: "2024-01-10T08:00:00Z",
  },
  {
    id: "2",
    name: "Claude Sonnet 4",
    type: "anthropic",
    description: "Anthropic's Claude Sonnet 4 for reasoning and analysis",
    api_key: "sk-ant-***...***",
    created_at: "2024-01-11T09:30:00Z",
    updated_at: "2024-01-11T09:30:00Z",
  },
  {
    id: "3",
    name: "Gemini Computer Use",
    type: "gemini",
    description: "Google's Gemini 2.5 with Computer Use for browser automation",
    api_key: "AIza***...***",
    created_at: "2024-01-12T10:15:00Z",
    updated_at: "2024-01-12T10:15:00Z",
  },
];

// Placeholder API functions
const modelApi = {
  getAll: async (): Promise<Model[]> => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    return [...mockModels];
  },

  getById: async (id: string): Promise<Model> => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    const model = mockModels.find((m) => m.id === id);
    if (!model) throw new Error("Model not found");
    return model;
  },

  create: async (
    modelData: Omit<Model, "id" | "created_at" | "updated_at">,
  ): Promise<Model> => {
    await new Promise((resolve) => setTimeout(resolve, 800));
    const newModel: Model = {
      ...modelData,
      id: String(mockModels.length + 1),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    mockModels.push(newModel);
    return newModel;
  },

  update: async (
    id: string,
    modelData: Partial<Omit<Model, "id" | "created_at" | "updated_at">>,
  ): Promise<Model> => {
    await new Promise((resolve) => setTimeout(resolve, 600));
    const index = mockModels.findIndex((m) => m.id === id);
    if (index === -1) throw new Error("Model not found");
    mockModels[index] = {
      ...mockModels[index],
      ...modelData,
      updated_at: new Date().toISOString(),
    };
    return mockModels[index];
  },

  delete: async (id: string): Promise<void> => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    const index = mockModels.findIndex((m) => m.id === id);
    if (index === -1) throw new Error("Model not found");
    mockModels.splice(index, 1);
  },
};

/**
 * Hook to fetch all models
 */
export const useModels = () => {
  return useQuery({
    queryKey: ["models"],
    queryFn: modelApi.getAll,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to fetch a single model by ID
 */
export const useModel = (id: string) => {
  return useQuery({
    queryKey: ["models", id],
    queryFn: () => modelApi.getById(id),
    enabled: !!id,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to create a new model
 */
export const useCreateModel = (options?: {
  onSuccess?: (model: Model) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (modelData: Omit<Model, "id" | "created_at" | "updated_at">) =>
      modelApi.create(modelData),
    onSuccess: (newModel) => {
      // Invalidate and refetch models list
      queryClient.invalidateQueries({ queryKey: ["models"] });

      // Add the new model to the cache
      queryClient.setQueryData(["models", newModel.id], newModel);

      // Update the models list cache if it exists
      queryClient.setQueryData<Model[]>(["models"], (oldData) => {
        if (!oldData) return [newModel];
        return [...oldData, newModel];
      });

      // Call the success callback if provided
      options?.onSuccess?.(newModel);
    },
    onError: (error) => {
      console.error("Failed to create model:", error);
      // Call the error callback if provided
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to update an existing model
 */
export const useUpdateModel = (options?: {
  onSuccess?: (model: Model) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      ...modelData
    }: { id: string } & Partial<
      Omit<Model, "id" | "created_at" | "updated_at">
    >) => modelApi.update(id, modelData),
    onSuccess: (updatedModel) => {
      // Update the specific model in cache
      queryClient.setQueryData(["models", updatedModel.id], updatedModel);

      // Update the models list cache
      queryClient.setQueryData<Model[]>(["models"], (oldData) => {
        if (!oldData) return [updatedModel];
        return oldData.map((model) =>
          model.id === updatedModel.id ? updatedModel : model,
        );
      });

      // Invalidate queries to ensure consistency
      queryClient.invalidateQueries({ queryKey: ["models"] });

      // Call the success callback if provided
      options?.onSuccess?.(updatedModel);
    },
    onError: (error) => {
      console.error("Failed to update model:", error);
      // Call the error callback if provided
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to delete a model
 */
export const useDeleteModel = (options?: {
  onSuccess?: (deletedId: string) => void;
  onError?: (error: Error) => void;
}) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => modelApi.delete(id),
    onSuccess: (_, deletedId) => {
      // Remove the model from specific cache
      queryClient.removeQueries({ queryKey: ["models", deletedId] });

      // Update the models list cache
      queryClient.setQueryData<Model[]>(["models"], (oldData) => {
        if (!oldData) return [];
        return oldData.filter((model) => model.id !== deletedId);
      });

      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: ["models"] });

      // Call the success callback if provided
      options?.onSuccess?.(deletedId);
    },
    onError: (error) => {
      console.error("Failed to delete model:", error);
      // Call the error callback if provided
      options?.onError?.(error as Error);
    },
  });
};

/**
 * Hook to get models by type
 */
export const useModelsByType = (type: ModelType) => {
  return useQuery({
    queryKey: ["models", "type", type],
    queryFn: () => modelApi.getAll(),
    select: (data) => data.filter((model) => model.type === type),
    enabled: !!type,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to get model statistics
 */
export const useModelStatistics = () => {
  return useQuery({
    queryKey: ["models", "statistics"],
    queryFn: async () => {
      const models = await modelApi.getAll();

      return {
        total: models.length,
        byType: {
          openai: models.filter((m) => m.type === "openai").length,
          anthropic: models.filter((m) => m.type === "anthropic").length,
        },
      };
    },
    staleTime: 1000 * 60 * 2, // 2 minutes
  });
};

/**
 * Hook to search models
 */
export const useSearchModels = (searchTerm: string) => {
  return useQuery({
    queryKey: ["models", "search", searchTerm],
    queryFn: () => modelApi.getAll(),
    select: (data) => {
      if (!searchTerm.trim()) return data;

      const term = searchTerm.toLowerCase().trim();
      return data.filter(
        (model) =>
          model.name.toLowerCase().includes(term) ||
          model.description.toLowerCase().includes(term) ||
          model.type.toLowerCase().includes(term),
      );
    },
    enabled: searchTerm.length >= 2, // Only search when we have at least 2 characters
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};

/**
 * Hook to prefetch a model (useful for hover effects)
 */
export const usePrefetchModel = () => {
  const queryClient = useQueryClient();

  return (id: string) => {
    queryClient.prefetchQuery({
      queryKey: ["models", id],
      queryFn: () => modelApi.getById(id),
      staleTime: 1000 * 60 * 5, // 5 minutes
    });
  };
};
