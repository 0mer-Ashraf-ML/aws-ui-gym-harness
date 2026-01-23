/**
 * Monitoring Service - API calls for token usage tracking
 * Follows the functional composition pattern from api.ts
 */

// Import the request function to make HTTP calls
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Simple request wrapper matching the api.ts pattern
async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = document.cookie
    .split('; ')
    .find((row) => row.startsWith('auth_token='))
    ?.split('=')[1];

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers || {}) as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

// Type definitions
export interface TokenUsageAggregation {
  model_name: string;
  model_versions: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_api_calls: number;
  total_cached_tokens: number;
  total_estimated_cost_usd: number;
  execution_count: number;
  iteration_count: number;
  average_tokens_per_iteration: number;
  average_tokens_per_api_call: number;
  average_input_tokens_per_api_call: number;
  average_output_tokens_per_api_call: number;
  first_usage: string;
  last_usage: string;
}

export interface TokenUsageSummary {
  total_tokens: number;
  total_cost_usd: number;
  total_api_calls: number;
  by_model: Record<string, TokenUsageAggregation>;
  time_range_start?: string;
  time_range_end?: string;
}

export interface DailyUsage {
  date: string;
  model_name: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  api_calls: number;
  cost_usd: number;
}

export interface TokenUsageRecord {
  uuid: string;
  iteration_id: string;
  execution_id: string;
  model_name: string;
  model_version: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  api_calls_count: number;
  cached_tokens: number;
  estimated_cost_usd: number;
  created_at: string;
  updated_at: string;
}

export interface CostBreakdown {
  total_cost_usd: number;
  models: Array<{
    model_name: string;
    total_cost_usd: number;
    total_tokens: number;
    api_calls: number;
    cost_per_call: number;
    cost_per_1k_tokens: number;
    percentage_of_total: number;
  }>;
}

export interface UsageGym {
  gym_id: string;
  gym_name: string;
}

export interface UsageBatch {
  batch_id: string;
  batch_name: string;
  batch_is_deleted: boolean;
}

// Helper to build query params
function buildQueryParams(params?: Record<string, string | number | undefined>): string {
  if (!params) return '';
  
  const filtered = Object.entries(params)
    .filter(([_, value]) => value !== undefined)
    .map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`);
  
  return filtered.length > 0 ? `?${filtered.join('&')}` : '';
}

/**
 * Get usage summary with optional filters
 */
export const getUsageSummary = async (params?: {
  model_name?: string;
  start_date?: string;
  end_date?: string;
  execution_id?: string;
  gym_id?: string;
  batch_id?: string;
}): Promise<TokenUsageSummary> => {
  const queryParams = buildQueryParams(params);
  return request<TokenUsageSummary>(`/api/v1/monitoring/usage/summary${queryParams}`);
};

/**
 * Get daily usage breakdown
 */
export const getDailyUsage = async (params?: {
  model_name?: string;
  start_date?: string;
  end_date?: string;
  gym_id?: string;
  batch_id?: string;
}): Promise<DailyUsage[]> => {
  const queryParams = buildQueryParams(params);
  return request<DailyUsage[]>(`/api/v1/monitoring/usage/daily${queryParams}`);
};

/**
 * Get cost breakdown
 */
export const getCostBreakdown = async (params?: {
  start_date?: string;
  end_date?: string;
}): Promise<CostBreakdown> => {
  const queryParams = buildQueryParams(params);
  return request<CostBreakdown>(`/api/v1/monitoring/usage/cost-breakdown${queryParams}`);
};

/**
 * Get usage for a specific execution
 */
export const getExecutionUsage = async (executionId: string): Promise<TokenUsageRecord[]> => {
  return request<TokenUsageRecord[]>(`/api/v1/monitoring/usage/execution/${executionId}`);
};

/**
 * Get usage for a specific iteration
 */
export const getIterationUsage = async (iterationId: string): Promise<TokenUsageRecord[]> => {
  return request<TokenUsageRecord[]>(`/api/v1/monitoring/usage/iteration/${iterationId}`);
};

/**
 * Get all available models
 */
export const getAvailableModels = async (): Promise<string[]> => {
  return request<string[]>('/api/v1/monitoring/usage/models');
};

/**
 * Get all usage records with pagination
 */
export const getAllUsage = async (params?: {
  skip?: number;
  limit?: number;
  model_name?: string;
  start_date?: string;
  end_date?: string;
  gym_id?: string;
  batch_id?: string;
}): Promise<TokenUsageRecord[]> => {
  const queryParams = buildQueryParams(params);
  return request<TokenUsageRecord[]>(`/api/v1/monitoring/usage/all${queryParams}`);
};

/**
 * Get distinct gyms from token usage snapshots
 */
export const getUsageGyms = async (): Promise<UsageGym[]> => {
  return request<UsageGym[]>('/api/v1/monitoring/usage/gyms');
};

/**
 * Get distinct batches from token usage snapshots (optional filter by gym_id)
 */
export const getUsageBatches = async (params?: {
  gym_id?: string;
}): Promise<UsageBatch[]> => {
  const queryParams = buildQueryParams(params);
  return request<UsageBatch[]>(`/api/v1/monitoring/usage/batches${queryParams}`);
};

/**
 * Download CSV file
 */
export const downloadUsageCSV = async (params?: {
  model_name?: string;
  start_date?: string;
  end_date?: string;
  gym_id?: string;
  batch_id?: string;
}): Promise<void> => {
  const queryParams = buildQueryParams(params);
  
  const token = document.cookie
    .split('; ')
    .find((row) => row.startsWith('auth_token='))
    ?.split('=')[1];

  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}/api/v1/monitoring/usage/export/csv${queryParams}`, {
    headers,
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `token_usage_${new Date().toISOString().split('T')[0]}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

