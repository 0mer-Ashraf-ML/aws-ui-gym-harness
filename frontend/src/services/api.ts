/**
 * RL Gym Harness - Functional Compositional API Service
 *
 * This module provides a functional composition approach to API interactions
 * with the FastAPI backend. It replaces the mock data system with real API calls.
 */

import type {
  Gym,
  GymCreateRequest,
  GymUpdateRequest,
  GymListResponse,
  GymListWithTaskCountResponse,
  Task,
  TaskCreateRequest,
  TaskUpdateRequest,
  TaskListResponse,
  TaskExport,
  GymTasksExport,
  Batch,
  BatchCreateRequest,
  BatchUpdateRequest,
  BatchListResponse,
  BatchMetadata,
  Execution,
  ModelType,
  ExecutionWithStatus,
  ExecutionCreateRequest,
  ExecutionUpdateRequest,
  ExecutionListResponse,
  ExecutionFilesResponse,
  ExecutionSummary,
  ExecutionProgress,
  APIError,
  AllTasksSummaryResponse,
  BatchIterationSummary,
  LeaderboardResponse,
} from "../types";
type ExecutionExportResponse = {
  message: string;
  download_url: string;
  filename: string;
  total_executions: number;
  total_tasks: number;
};
// =============================================================================
// Configuration
// =============================================================================

const API_CONFIG = {
  baseUrl: import.meta.env.VITE_API_URL || "http://localhost:8000",
  timeout: 30000,
  retries: 3,
  disableAuth: import.meta.env.VITE_DISABLE_AUTH === "true",
} as const;

// Extended timeout for report generation operations
const REPORT_TIMEOUT = 300000; // 5 minutes for reports

// =============================================================================
// Core HTTP Client Functions
// =============================================================================

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  headers?: Record<string, string>;
  body?: unknown;
  timeout?: number;
  params?: Record<string, string | number | boolean>;
}

/**
 * Get authentication token from cookies
 */
export const getAuthToken = (): string | null => {
  // This will be handled by the auth context, but we need a fallback
  const token = document.cookie
    .split("; ")
    .find((row) => row.startsWith("auth_token="))
    ?.split("=")[1];
  return token || null;
};

/**
 * Get refresh token from cookies
 */
const getRefreshToken = (): string | null => {
  const token = document.cookie
    .split("; ")
    .find((row) => row.startsWith("refresh_token="))
    ?.split("=")[1];
  return token || null;
};

/**
 * Refresh access token using refresh token
 */
const refreshAccessToken = async (): Promise<string | null> => {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    console.warn("No refresh token available for token refresh");
    return null;
  }

  try {
    const response = await fetch(`${API_CONFIG.baseUrl}/api/v1/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      console.error(
        "Token refresh failed:",
        response.status,
        response.statusText
      );
      return null;
    }

    const authData = await response.json();

    // Update cookies with new tokens
    document.cookie = `auth_token=${authData.access_token}; path=/; max-age=${
      7 * 24 * 60 * 60
    }`;
    document.cookie = `refresh_token=${
      authData.refresh_token
    }; path=/; max-age=${7 * 24 * 60 * 60}`;
    document.cookie = `user_data=${JSON.stringify(
      authData.user
    )}; path=/; max-age=${7 * 24 * 60 * 60}`;

    console.log("Token refreshed successfully");
    return authData.access_token;
  } catch (error) {
    console.error("Error refreshing token:", error);
    return null;
  }
};

/**
 * Clear all authentication data and trigger redirect
 */
const clearAuthAndRedirect = (): void => {
  console.log("Clearing authentication data and triggering redirect to login");
  // Clear all auth cookies
  document.cookie =
    "auth_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  document.cookie =
    "refresh_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  document.cookie = "user_data=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  // Trigger a custom event that the AuthRedirectHandler can listen to
  window.dispatchEvent(new CustomEvent("auth-logout-required"));
};

/**
 * Core HTTP request function with error handling and timeout
 */
const request = async <T>(
  endpoint: string,
  options: RequestOptions = {},
  retryCount: number = 0
): Promise<T> => {
  const {
    method = "GET",
    headers = {},
    body,
    timeout = API_CONFIG.timeout,
  } = options;

  const url = `${API_CONFIG.baseUrl}${endpoint}`;

  // Add authentication token if available and auth is not disabled
  const token = getAuthToken();
  const authHeaders: Record<string, string> = 
    API_CONFIG.disableAuth || !token
      ? {}
      : { Authorization: `Bearer ${token}` };

  // Debug logging for execution API calls
  if (endpoint.includes("/executions")) {
    console.log(`🚀 API Request [${method}] ${url}`);
    console.log("🚀 Request headers:", { ...headers, ...authHeaders });
    if (body) {
      console.log("🚀 Request body:", body);
    }
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders,
        ...headers,
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      // Handle 401 Unauthorized - try to refresh token (only if auth is not disabled)
      if (response.status === 401 && retryCount === 0 && !API_CONFIG.disableAuth) {
        console.log("Access token expired, attempting to refresh...");
        const newToken = await refreshAccessToken();

        if (newToken) {
          console.log("Token refreshed, retrying request...");
          // Retry the request with the new token
          return request<T>(endpoint, options, retryCount + 1);
        } else {
          console.error("Token refresh failed, redirecting to login");
          clearAuthAndRedirect();
          throw new Error("Authentication failed - please login again");
        }
      }

      const errorData: APIError = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
        status_code: response.status,
      }));

      // Format error message - handle both string and array (validation errors) formats
      let errorMessage: string;
      if (Array.isArray(errorData.detail)) {
        // FastAPI validation errors are arrays of error objects
        errorMessage = errorData.detail
          .map((err: any) => {
            const field = err.loc?.join(".") || "field";
            return `${field}: ${err.msg || err.message || "Validation error"}`;
          })
          .join("; ");
      } else if (typeof errorData.detail === "object" && errorData.detail !== null) {
        // If detail is an object, try to extract a message
        errorMessage = JSON.stringify(errorData.detail);
      } else {
        // detail is a string
        errorMessage = errorData.detail || `Request failed with status ${response.status}`;
      }

      // Create an error object that preserves the status code
      const error = new Error(errorMessage) as Error & { status: number; statusCode: number };
      error.status = response.status;
      error.statusCode = response.status;

      throw error;
    }

    // Handle empty responses (like DELETE operations)
    if (response.status === 204) {
      if (endpoint.includes("/executions")) {
        console.log("✅ API Response [204]: Empty response (successful)");
      }
      return {} as T;
    }

    const data = await response.json();

    // Debug logging for execution API responses
    if (endpoint.includes("/executions")) {
      console.log(`✅ API Response [${response.status}]:`, data);
    }

    return data as T;
  } catch (error) {
    clearTimeout(timeoutId);

    // Debug logging for execution API errors
    if (endpoint.includes("/executions")) {
      console.error(`❌ API Request Failed [${method}] ${url}:`, error);
    }

    if (error instanceof Error) {
      if (error.name === "AbortError") {
        throw new Error(`Request timeout after ${timeout}ms`);
      }
      throw error;
    }

    throw new Error("Unknown error occurred");
  }
};

// =============================================================================
// Functional Composition Helpers
// =============================================================================

/**
 * Creates a GET request function for a specific endpoint
 */
const createGetter =
  <T>(endpoint: string) =>
  (params?: Record<string, string | number | boolean>) => {
    const searchParams = params
      ? new URLSearchParams(
          Object.entries(params).map(([key, value]) => [key, String(value)])
        ).toString()
      : "";

    const url = searchParams ? `${endpoint}?${searchParams}` : endpoint;
    return request<T>(url);
  };

/**
 * Creates a POST request function for a specific endpoint
 */
const createPoster =
  <TRequest, TResponse>(endpoint: string) =>
  (data: TRequest) =>
    request<TResponse>(endpoint, { method: "POST", body: data });

/**
 * Creates a PUT request function for a specific endpoint
 */
const createPutter =
  <TRequest, TResponse>(endpoint: string) =>
  (id: string, data: TRequest) =>
    request<TResponse>(`${endpoint}/${id}`, { method: "PUT", body: data });

/**
 * Creates a DELETE request function for a specific endpoint
 */
const createDeleter = (endpoint: string) => (id: string) =>
  request<void>(`${endpoint}/${id}`, { method: "DELETE" });

/**
 * Creates a GET-by-ID request function for a specific endpoint
 */
const createGetById =
  <T>(endpoint: string) =>
  (id: string) =>
    request<T>(`${endpoint}/${id}`);

// =============================================================================
// Gym API Functions
// =============================================================================

export const gymApi = {
  /**
   * Get all gyms with optional pagination and filtering
   */
  getAll: createGetter<GymListResponse>("/api/v1/gyms"),

  /**
   * Get all gyms with task counts
   */
  getAllWithTaskCounts: createGetter<GymListWithTaskCountResponse>("/api/v1/gyms/with-task-counts"),

  /**
   * Get a single gym by UUID
   */
  getById: createGetById<Gym>("/api/v1/gyms"),

  /**
   * Create a new gym
   */
  create: createPoster<GymCreateRequest, Gym>("/api/v1/gyms"),

  /**
   * Update an existing gym
   */
  update: createPutter<GymUpdateRequest, Gym>("/api/v1/gyms"),

  /**
   * Delete a gym
   */
  delete: createDeleter("/api/v1/gyms"),

  /**
   * Generate Excel report for a gym with optional date filters
   */
  generateReport: async (
    gymId: string,
    startDate?: string,
    endDate?: string
  ): Promise<{
    message: string;
    gym_name: string;
    gym_uuid: string;
    executions_count: number;
    execution_dirs_count: number;
    start_date: string | null;
    end_date: string | null;
    download_url: string;
    filename: string;
    json_snapshot: string;
  }> => {
    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);

    const url = `/api/v1/gyms/${gymId}/report${
      params.toString() ? `?${params}` : ""
    }`;
    return await request<{
      message: string;
      gym_name: string;
      gym_uuid: string;
      executions_count: number;
      execution_dirs_count: number;
      start_date: string | null;
      end_date: string | null;
      download_url: string;
      filename: string;
      json_snapshot: string;
    }>(url, { timeout: REPORT_TIMEOUT });
  },

  /**
   * Get execution data for a gym in JSON format
   */
  getExecutionsData: async (
    gymId: string,
    startDate?: string,
    endDate?: string
  ) => {
    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);

    const url = `/api/v1/gyms/${gymId}/executions-data${
      params.toString() ? `?${params}` : ""
    }`;
    return await request(url);
  },

  /**
   * Export all tasks for a gym (admin-only)
   */
  exportTasks: (gymUuid: string) =>
    request<GymTasksExport>(
      `/api/v1/gyms/${gymUuid}/tasks/export`,
      { method: "GET" }
    ),
} as const;

// =============================================================================
// Task API Functions
// =============================================================================

export const taskApi = {
  /**
   * Get all tasks with optional filtering by gym
   */
  getAll: createGetter<TaskListResponse>("/api/v1/tasks"),

  /**
   * Get a single task by UUID
   */
  getById: createGetById<Task>("/api/v1/tasks"),

  /**
   * Create a new task
   */
  create: createPoster<TaskCreateRequest, Task>("/api/v1/tasks"),

  /**
   * Update an existing task
   */
  update: createPutter<TaskUpdateRequest, Task>("/api/v1/tasks"),

  /**
   * Delete a task
   */
  delete: createDeleter("/api/v1/tasks"),

  /**
   * Sync tasks from a gym's API endpoint
   */
  syncFromGym: (gymId: string) =>
    request<{ message: string; new_tasks_count: number; total_tasks_count: number }>(
      `/api/v1/tasks/sync/${gymId}`,
      { method: "POST" }
    ),

  /**
   * Export a task as JSON with task_id, prompt, and verification_script_md
   */
  export: (taskUuid: string) =>
    request<TaskExport>(
      `/api/v1/tasks/${taskUuid}/export`,
      { method: "GET" }
    ),
} as const;

// =============================================================================
// Batch API Functions
// =============================================================================

export const batchApi = {
  /**
   * Get all batches with optional filtering by gym
   */
  getAll: createGetter<BatchListResponse>("/api/v1/batches"),

  /**
   * Get a single batch by UUID
   */
  getById: createGetById<Batch>("/api/v1/batches"),

  /**
   * Create a new batch
   */
  create: createPoster<BatchCreateRequest, Batch>("/api/v1/batches"),

  /**
   * Update an existing batch
   */
  update: createPutter<BatchUpdateRequest, Batch>("/api/v1/batches"),

  /**
   * Delete a batch
   */
  delete: createDeleter("/api/v1/batches"),

  /**
   * Delete all batches (admin only)
   */
  deleteAll: () =>
    request<{
      message: string;
      deleted_count: number;
      failed_count: number;
      failed_batches?: string[];
    }>("/api/v1/batches", {
      method: "DELETE",
    }),

  /**
   * Get lightweight batch metadata for dropdowns/selection (no status calculation)
   */
  getMetadata: (
    params?: { gym_id?: string; limit?: number }
  ) => {
    const queryParts: string[] = [];
    if (params?.gym_id) {
      queryParts.push(`gym_id=${encodeURIComponent(params.gym_id)}`);
    }
    if (params?.limit) {
      queryParts.push(`limit=${encodeURIComponent(params.limit)}`);
    }
    const queryString = queryParts.length > 0 ? `?${queryParts.join("&")}` : "";
    return request<BatchMetadata[]>(`/api/v1/batches/metadata${queryString}`, {
      method: "GET",
    });
  },

  /**
   * Get executions for a specific batch
   */
  getExecutions: (
    batchId: string,
    params?: Record<string, string | number | boolean>
  ) =>
    request<Execution[]>(`/api/v1/batches/${batchId}/executions`, {
      method: "GET",
      params,
    }),

  /**
   * Execute a batch
   */
  execute: (batchId: string) =>
    request<{ message: string; batch_id: string; executions_count: number }>(
      `/api/v1/batches/${batchId}/execute`,
      {
        method: "POST",
      }
    ),

  /**
   * Check if batch report is ready
   */
  checkReportReadiness: (batchId: string) =>
    request<{
      ready: boolean;
      reason: string;
      blocking_items: Array<{
        type: string;
        execution_id: string;
        iteration_number: number;
        status: string;
        task_identifier: string;
        model: string;
        error_message?: string;
        missing_directory?: string;
      }>;
      counts?: {
        pending: number;
        executing: number;
        crashed: number;
        failed_without_directory: number;
        total_blocking: number;
      };
    }>(`/api/v1/batches/${batchId}/report-readiness`),

  /**
   * Get all batches with ready reports
   */
  getReadyReports: () =>
    request<{
      ready_batches: Array<{
        batch_id: string;
        batch_name: string;
        gym_id: string;
        number_of_iterations: number;
        is_read: boolean;
        created_at: string;
        updated_at: string;
      }>;
      count: number;
      unread_count: number;
    }>(`/api/v1/batches/ready-reports`),

  /**
   * Mark a batch notification as read for current user
   */
  markNotificationRead: (batchId: string) =>
    request<{
      message: string;
      batch_id: string;
    }>(`/api/v1/batches/${batchId}/mark-notification-read`, {
      method: "POST",
    }),

  /**
   * Download batch archive as ZIP
   * Returns the download URL for use with download service
   */
  downloadBatch: (batchId: string) => {
    const token = getAuthToken();
    const url = `${API_CONFIG.baseUrl}/api/v1/batches/${batchId}/download`;
    return token ? `${url}?token=${encodeURIComponent(token)}` : url;
  },

  /**
   * Generate batch report
   */
  generateReport: (batchId: string) =>
    request<{
      message: string;
      batch_name: string;
      batch_uuid: string;
      executions_count: number;
      execution_dirs_count: number;
      download_url: string;
      filename: string;
      json_snapshot: string;
    }>(`/api/v1/batches/${batchId}/report`, { timeout: REPORT_TIMEOUT }),

  /**
   * Terminate a running/pending batch and cleanup
   */
  terminate: (batchId: string) =>
    request<{
      message: string;
      terminated: number;
      inspected: number;
      errors?: string[];
    }>(`/api/v1/batches/${batchId}/terminate`, { method: "POST" }),

  /**
   * Rerun failed iterations in a batch
   */
  rerunFailedIterations: (batchId: string) =>
    request<{
      message: string;
      batch_id: string;
      total_failed_iterations: number;
      rerun_iterations: number;
      skipped_iterations: number;
      failed_cleanups: number;
      failed_resets: number;
      failed_queues: number;
    }>(`/api/v1/batches/${batchId}/rerun-failed-iterations`, {
      method: "POST",
    }),

  /**
   * Get batch iteration summary with overall and per-execution breakdown
   */
  getIterationSummary: (batchId: string) =>
    request<BatchIterationSummary>(
      `/api/v1/batches/${batchId}/iteration-summary`
    ),

  getFailureDiagnostics: (batchId: string) =>
    request<any>(`/api/v1/batches/${batchId}/failure-diagnostics`),

  /**
   * Get batch report data for preview (no file generation)
   */
  getReportData: (batchId: string) =>
    request<{
      batch_name: string;
      batch_uuid: string;
      executions_count: number;
      batch_insights: { [key: string]: string };
      summary_rows: any[];
      task_rows: any;
      iteration_records: any[];
      total_iterations: number;
    }>(`/api/v1/batches/${batchId}/report-data`, { timeout: REPORT_TIMEOUT }),
} as const;

// =============================================================================
// Execution API Functions
// =============================================================================

export const executionApi = {
  /**
   * Get all executions with optional filtering, sorting, and search
   */
  getAll: (params?: Record<string, string | number | boolean | string[]>) => {
    // Handle array parameters (like status) for FastAPI list query params
    const searchParams = params
      ? new URLSearchParams(
          Object.entries(params).flatMap(([key, value]) => {
            if (Array.isArray(value)) {
              // For arrays, add multiple query params with the same name
              return value.map((v) => [key, String(v)]);
            } else if (value !== undefined && value !== null) {
              return [[key, String(value)]];
            }
            return [];
          })
        ).toString()
      : "";

    const url = searchParams ? `/api/v1/executions?${searchParams}` : "/api/v1/executions";
    return request<ExecutionListResponse>(url);
  },

  /**
   * Get a single execution by UUID with enhanced status information
   */
  getById: createGetById<ExecutionWithStatus>("/api/v1/executions"),

  /**
   * Create a new execution
   */
  create: createPoster<ExecutionCreateRequest, Execution>("/api/v1/executions"),

  /**
   * Update an existing execution
   */
  update: createPutter<ExecutionUpdateRequest, Execution>("/api/v1/executions"),

  /**
   * Delete an execution
   */
  delete: createDeleter("/api/v1/executions"),

  /**
   * Execute/start a run
   */
  execute: (uuid: string) =>
    request<Execution>(`/api/v1/executions/${uuid}/execute`, {
      method: "POST",
    }),

  /**
   * Get execution progress including per-iteration statuses
   */
  getProgress: (uuid: string) =>
    request<ExecutionProgress>(`/api/v1/executions/${uuid}/progress`),

  /**
   * Get progress for all playground executions in a single request
   */
  getPlaygroundProgress: (
    params?: {
      skip?: number;
      limit?: number;
      search?: string;
      status?: Execution["status"][];
      model?: ModelType[];
      sort_by?: string;
      sort_order?: "asc" | "desc";
    }
  ) =>
    request<{
      execution_progress: Record<string, {
        execution_id: string;
        total_iterations: number;
        completed_iterations: number;
        progress_percentage: number;
        summary: {
          total_iterations: number;
          pending_count: number;
          executing_count: number;
          passed_count: number;
          failed_count: number;
          crashed_count: number;
          timeout_count: number;
        };
      }>;
      total_executions: number;
      returned_executions: number;
      generated_at: string;
    }>(
      `/api/v1/executions/playground-progress${(() => {
        if (!params) {
          return "";
        }
        const sp = new URLSearchParams(
          Object.entries(params).flatMap(([key, value]) => {
            if (value === undefined || value === null) {
              return [];
            }
            if (Array.isArray(value)) {
              return value.map((v) => [key, String(v)]);
            }
            return [[key, String(value)]];
          })
        );
        const q = sp.toString();
        return q ? `?${q}` : "";
      })()}`
    ),

  /**
   * Aggregate reports: all tasks summary with filters
   */
  getAllTasksSummary: (
    params: {
      gym_id?: string;
      start_date?: string;
      end_date?: string;
      max_executions?: number;
      include_task_details?: boolean;
    } = {}
  ) =>
    request<AllTasksSummaryResponse>(
      `/api/v1/executions/all-tasks-summary${(() => {
        const sp = new URLSearchParams();
        if (params.gym_id) sp.append("gym_id", params.gym_id);
        if (params.start_date) sp.append("start_date", params.start_date);
        if (params.end_date) sp.append("end_date", params.end_date);
        if (typeof params.max_executions === "number")
          sp.append("max_executions", String(params.max_executions));
        if (typeof params.include_task_details === "boolean")
          sp.append(
            "include_task_details",
            String(params.include_task_details)
          );
        const q = sp.toString();
        return q ? `?${q}` : "";
      })()}`
    ),

  /**
   * Generate and download the aggregate summary report (Excel)
   */
  downloadAllTasksSummaryReport: async (
    params: {
      gym_id?: string;
      start_date?: string;
      end_date?: string;
      max_executions?: number;
      include_snapshot?: boolean;
    } = {}
  ): Promise<void> => {
    const sp = new URLSearchParams();
    if (params.gym_id) sp.append("gym_id", params.gym_id);
    if (params.start_date) sp.append("start_date", params.start_date);
    if (params.end_date) sp.append("end_date", params.end_date);
    if (typeof params.max_executions === "number")
      sp.append("max_executions", String(params.max_executions));
    if (typeof params.include_snapshot === "boolean")
      sp.append("include_snapshot", String(params.include_snapshot));

    const url = `/api/v1/executions/all-tasks-summary/report${
      sp.toString() ? `?${sp}` : ""
    }`;
    const { download_url } = await request<{ download_url: string }>(url, {
      timeout: REPORT_TIMEOUT,
    });
    await executionApi.downloadExport(download_url);
  },
  /**
   * Trigger server-side export of ALL executions.
   * Returns { message, download_url, filename, total_executions, total_tasks }
   */
  exportAll: async (): Promise<ExecutionExportResponse> => {
    const url = `${API_CONFIG.baseUrl}/api/v1/executions/export`;

    const token = getAuthToken();

    // Use longer timeout for large exports (2 minutes)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120000);

    try {
      const res = await fetch(url, {
        method: "GET",
        credentials: "include",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          "Cache-Control": "no-store",
          Pragma: "no-cache",
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        const errorMessage =
          errorData.detail || `Export failed: ${res.status} ${res.statusText}`;
        throw new Error(errorMessage);
      }

      return res.json();
    } catch (error) {
      clearTimeout(timeoutId);
      if (error instanceof Error && error.name === "AbortError") {
        throw new Error(
          "Export timeout - the export is taking too long. Please try exporting fewer executions."
        );
      }
      throw error;
    }
  },

  /**
   * Download the exported Excel file (forces fresh fetch to avoid 304)
   */
  downloadExport: async (downloadUrl: string): Promise<void> => {
    const absoluteUrl = downloadUrl.startsWith("http")
      ? downloadUrl
      : `${API_CONFIG.baseUrl}${downloadUrl}`;

    // Add cache-buster so browser/CDN won't do conditional GET -> 304
    const url =
      absoluteUrl + (absoluteUrl.includes("?") ? "&" : "?") + `v=${Date.now()}`;

    const token = getAuthToken();
    const res = await fetch(url, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        "Cache-Control": "no-store",
        Pragma: "no-cache",
      },
    });

    if (!res.ok) {
      throw new Error(`Download failed: ${res.status} ${res.statusText}`);
    }

    const blob = await res.blob();

    // Try to extract filename from Content-Disposition; fallback to URL
    const filename = (() => {
      const cd = res.headers.get("Content-Disposition") || "";
      const match = cd.match(/filename="?([^"]+)"?/i);
      if (match?.[1]) return match[1];
      const pathPart = new URL(absoluteUrl).pathname.split("/").pop() || "";
      return pathPart || "executions_all_results.xlsx";
    })();

    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 10_000);
  },
} as const;

// =============================================================================
// File API Functions
// =============================================================================

export const fileApi = {
  /**
   * Get all files for an execution with polling capability
   */
  getExecutionFiles: (
    executionId: string,
    format: "hierarchical" | "flat" = "hierarchical"
  ) =>
    request<ExecutionFilesResponse>(
      `/api/v1/executions/${executionId}/files?format=${format}&_=${Date.now()}`
    ),

  /**
   * Get files for a specific iteration within an execution
   */
  getIterationFiles: (
    executionId: string,
    iterationId: string,
    format: "hierarchical" | "flat" = "hierarchical"
  ) =>
    request<ExecutionFilesResponse>(
      `/api/v1/executions/${executionId}/iterations/${iterationId}/files?format=${format}&_=${Date.now()}`
    ),

  /**
   * Get file URL for download/preview with authentication
   */
  getFileUrl: (executionId: string, filePath: string) => {
    const token = getAuthToken();
    const baseUrl = `${
      API_CONFIG.baseUrl
    }/api/v1/executions/${executionId}/files/${encodeURIComponent(filePath)}`;
    return token ? `${baseUrl}?token=${encodeURIComponent(token)}` : baseUrl;
  },

  /**
   * Get file thumbnail URL for images with authentication
   */
  getThumbnailUrl: (executionId: string, filePath: string) => {
    const token = getAuthToken();
    const baseUrl = `${
      API_CONFIG.baseUrl
    }/api/v1/executions/${executionId}/files/${encodeURIComponent(filePath)}`;
    return token ? `${baseUrl}?token=${encodeURIComponent(token)}` : baseUrl;
  },

  /**
   * Download file with progress tracking
   */
  downloadFile: async (
    executionId: string,
    filePath: string,
    onProgress?: (progress: number) => void
  ) => {
    const url = fileApi.getFileUrl(executionId, filePath);
    const response = await fetch(url);
    if (!response.ok)
      throw new Error(`Failed to download: ${response.statusText}`);

    const contentLength = response.headers.get("content-length");
    if (!contentLength || !onProgress) {
      return response.blob();
    }

    const total = parseInt(contentLength, 10);
    let loaded = 0;
    const reader = response.body!.getReader();
    const chunks = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      chunks.push(value);
      loaded += value.length;
      onProgress(Math.round((loaded / total) * 100));
    }

    return new Blob(chunks);
  },

  /**
   * Get execution summary with parsed JSON data
   */
  getExecutionSummary: (executionId: string) =>
    request<ExecutionSummary>(`/api/v1/executions/${executionId}/summary`),

  /**
   * Download iteration archive as ZIP
   * Returns the download URL for use with download service
   */
  downloadIteration: (executionId: string, iterationId: string) => {
    const token = getAuthToken();
    const url = `${API_CONFIG.baseUrl}/api/v1/executions/${executionId}/iterations/${iterationId}/download`;
    return token ? `${url}?token=${encodeURIComponent(token)}` : url;
  },

  /**
   * Download execution archive as ZIP
   * Returns the download URL for use with download service
   */
  downloadExecution: (executionId: string) => {
    const token = getAuthToken();
    const url = `${API_CONFIG.baseUrl}/api/v1/executions/${executionId}/download`;
    return token ? `${url}?token=${encodeURIComponent(token)}` : url;
  },
} as const;

// =============================================================================
// Health Check API
// =============================================================================

interface HealthResponse {
  status: string;
  timestamp: string;
  services: Record<string, string>;
}

// =============================================================================
// Leaderboard API Functions
// =============================================================================

export const leaderboardApi = {
  /**
   * Get leaderboard statistics with optional filters
   */
  get: (params?: {
    batch_ids?: string[];
    start_date?: string;
    end_date?: string;
    gym_ids?: string[];
  }) => {
    const queryParts: string[] = [];
    
    if (params?.batch_ids && params.batch_ids.length > 0) {
      params.batch_ids.forEach((id) => {
        queryParts.push(`batch_ids=${encodeURIComponent(id)}`);
      });
    }
    
    if (params?.start_date) {
      queryParts.push(`start_date=${encodeURIComponent(params.start_date)}`);
    }
    
    if (params?.end_date) {
      queryParts.push(`end_date=${encodeURIComponent(params.end_date)}`);
    }
    
    if (params?.gym_ids && params.gym_ids.length > 0) {
      params.gym_ids.forEach((id) => {
        queryParts.push(`gym_ids=${encodeURIComponent(id)}`);
      });
    }
    
    const queryString = queryParts.length > 0 ? `?${queryParts.join("&")}` : "";
    
    return request<LeaderboardResponse>(`/api/v1/leaderboard${queryString}`, {
      method: "GET",
    });
  },
} as const;

// =============================================================================
// Health API Functions
// =============================================================================

export const healthApi = {
  /**
   * Check API health status
   */
  check: () => request<HealthResponse>("/health"),
} as const;

// =============================================================================
// Composed API Functions (Higher-level operations)
// =============================================================================

/**
 * Get gyms with their associated tasks
 */
export const getGymsWithTasks = async (): Promise<
  (Gym & { tasks: Task[] })[]
> => {
  const [gymResponse, taskResponse] = await Promise.all([
    gymApi.getAll(),
    taskApi.getAll(),
  ]);

  return gymResponse.gyms.map((gym) => ({
    ...gym,
    tasks: taskResponse.tasks.filter((task) => task.gym_id === gym.uuid),
  }));
};

/**
 * Get executions with their associated gym and task information
 */
export const getExecutionsWithDetails = async (): Promise<
  (Execution & { gym?: Gym; task?: Task })[]
> => {
  const [executionResponse, gymResponse, taskResponse] = await Promise.all([
    executionApi.getAll(),
    gymApi.getAll(),
    taskApi.getAll(),
  ]);

  return executionResponse.executions.map((execution) => {
    const gym = gymResponse.gyms.find((g) => g.uuid === execution.gym_id);
    // Match task_identifier (string) with task.task_id (string), not with task.uuid
    const task = execution.task_identifier
      ? taskResponse.tasks.find((t) => t.task_id === execution.task_identifier)
      : undefined;

    return {
      ...execution,
      task_id: execution.task_identifier,  // Backwards compatibility: populate task_id from task_identifier
      gym,
      task,
    };
  });
};

/**
 * Create a gym and initial tasks in one operation
 */
export const createGymWithTasks = async (
  gymData: GymCreateRequest,
  tasks: Omit<TaskCreateRequest, "gym_id">[]
): Promise<{ gym: Gym; tasks: Task[] }> => {
  const gym = await gymApi.create(gymData);

  const createdTasks = await Promise.all(
    tasks.map((task) =>
      taskApi.create({
        ...task,
        gym_id: gym.uuid,
      })
    )
  );

  return {
    gym,
    tasks: createdTasks,
  };
};

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Test API connectivity
 */
export const testConnection = async (): Promise<boolean> => {
  try {
    await healthApi.check();
    return true;
  } catch {
    return false;
  }
};

/**
 * Retry a function with exponential backoff
 */
export const withRetry = async <T>(
  fn: () => Promise<T>,
  maxRetries: number = API_CONFIG.retries
): Promise<T> => {
  let lastError: Error;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));

      if (attempt === maxRetries) {
        break;
      }

      // Exponential backoff: 1s, 2s, 4s, 8s...
      const delay = Math.pow(2, attempt) * 1000;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError!;
};

// =============================================================================
// Configuration Functions
// =============================================================================

/**
 * Update API configuration
 */
export const updateApiConfig = (config: Partial<typeof API_CONFIG>) => {
  Object.assign(API_CONFIG, config);
};

/**
 * Get current API configuration
 */
export const getApiConfig = () => ({ ...API_CONFIG });

export const exportAndDownloadAllExecutions = async () => {
  const { download_url } = await executionApi.exportAll();
  await executionApi.downloadExport(download_url);
};

// =============================================================================
// Action Timeline API (for iteration monitoring)
// =============================================================================

import type { TimelineResponse } from "../types";

type ScreenshotVariant = "before" | "after";

export const timelineApi = {
  /**
   * Get action timeline for an iteration
   */
  getTimeline: (executionId: string, iterationId: string, live: boolean = false) =>
    request<TimelineResponse>(
      `/api/v1/executions/${executionId}/iterations/${iterationId}/timeline${live ? '?live=true' : ''}`
    ),

  /**
   * Get screenshot URL for a specific action
   */
  getScreenshotUrl: (
    executionId: string,
    iterationId: string,
    actionId: string,
    variant: ScreenshotVariant = "after"
  ) => {
    const token = getAuthToken();
    const baseUrl = `${API_CONFIG.baseUrl}/api/v1/executions/${executionId}/iterations/${iterationId}/actions/${actionId}/screenshot`;
    const params = new URLSearchParams();
    if (variant && variant !== "after") {
      params.set("variant", variant);
    }
    if (token) {
      params.set("token", token);
    }
    const query = params.toString();
    return query ? `${baseUrl}?${query}` : baseUrl;
  },

};

// =============================================================================
// Export everything as default for backward compatibility
// =============================================================================

export default {
  gymApi,
  taskApi,
  batchApi,
  executionApi,
  fileApi,
  healthApi,
  timelineApi,
  getGymsWithTasks,
  getExecutionsWithDetails,
  createGymWithTasks,
  testConnection,
  withRetry,
  updateApiConfig,
  getApiConfig,
};
