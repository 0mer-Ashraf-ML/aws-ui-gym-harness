import { useQuery } from "@tanstack/react-query";
import { batchApi } from "../services/api";

/**
 * Hook to fetch batch information by ID
 */
export function useBatch(batchId: string | null | undefined) {
  return useQuery({
    queryKey: ["batch", batchId],
    queryFn: () => batchApi.getById(batchId!),
    enabled: !!batchId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
