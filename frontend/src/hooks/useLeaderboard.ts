import { useQuery } from "@tanstack/react-query";
import { leaderboardApi } from "../services/api";
import type { LeaderboardResponse } from "../types";

export interface LeaderboardFilters {
  batch_ids?: string[];
  start_date?: string;
  end_date?: string;
  gym_ids?: string[];
}

/**
 * Hook to fetch leaderboard data with filters
 */
export const useLeaderboard = (filters?: LeaderboardFilters) => {
  return useQuery<LeaderboardResponse, Error>({
    queryKey: ["leaderboard", filters],
    queryFn: () => leaderboardApi.get(filters),
    staleTime: 1000 * 30, // 30 seconds
    refetchOnWindowFocus: true,
  });
};

