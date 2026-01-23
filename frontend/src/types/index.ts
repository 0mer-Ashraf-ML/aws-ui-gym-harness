// Backend-aligned types for RL Gym Harness

export type ModelType = "openai" | "anthropic" | "gemini" | "unified";
export type VerificationStrategy =
  | "verification_endpoint"
  | "local_storage_assertions"
  | "run_id_assertions"
  | "grader_config"
  | "verifier_api_script";

export interface Gym {
  uuid: string;
  name: string;
  description: string;
  base_url: string;
  verification_strategy: VerificationStrategy;
  created_at: string;
  updated_at: string;
}

export interface GymCreateRequest {
  name: string;
  description: string;
  base_url: string;
  verification_strategy?: VerificationStrategy;
}

export interface GymUpdateRequest {
  name?: string;
  description?: string;
  base_url?: string;
  verification_strategy?: VerificationStrategy;
}

export interface GymWithTaskCount extends Gym {
  task_count: number;
}

export interface GymListResponse {
  gyms: Gym[];
  total: number;
  skip: number;
  limit: number;
}

export interface GymListWithTaskCountResponse {
  gyms: GymWithTaskCount[];
  total: number;
  skip: number;
  limit: number;
}

export interface Task {
  uuid: string;
  task_id: string;
  gym_id: string;
  prompt: string;
  grader_config?: Record<string, unknown> | null;
  simulator_config?: Record<string, unknown> | null;
  verifier_path?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskCreateRequest {
  task_id?: string;
  gym_id: string;
  prompt: string;
  grader_config?: Record<string, unknown> | null;
  simulator_config?: Record<string, unknown> | null;
  verifier_path?: string | null;
}

export interface TaskUpdateRequest {
  task_id?: string;
  gym_id?: string;
  prompt?: string;
  grader_config?: Record<string, unknown> | null;
  simulator_config?: Record<string, unknown> | null;
  verifier_path?: string | null;
}

export interface TaskListResponse {
  tasks: Task[];
  total: number;
  skip: number;
  limit: number;
}

export interface TaskExport {
  task_id: string;
  prompt: string;
  verification_script_md: string;
}

export interface GymTasksExport {
  gym_id: string;
  tasks: TaskExport[];
}

export interface Batch {
  uuid: string;
  name: string;
  gym_id: string;
  number_of_iterations: number;
  status: "pending" | "executing" | "completed" | "failed" | "crashed";
  eval_insights?: { [key: string]: string } | null;
  created_at: string;
  updated_at: string;
  rerun_enabled: boolean; // Whether manual rerun is enabled for this batch
  created_by?: string; // UUID of user who created this batch
  username?: string | null; // Username/email of the user who created this batch
}

export interface BatchMetadata {
  uuid: string;
  name: string;
  created_at: string;
  gym_id: string;
}

export interface BatchCreateRequest {
  name: string;
  gym_id: string;
  number_of_iterations: number;
  selected_models: ModelType[];
  selected_task_ids?: string[]; // Optional list of task UUIDs. If not provided or empty, all tasks will be used.
}

export interface BatchUpdateRequest {
  name?: string;
  gym_id?: string;
  number_of_iterations?: number;
}

export interface BatchListResponse {
  batches: Batch[];
  total: number;
  skip: number;
  limit: number;
}

export interface Execution {
  uuid: string;
  execution_folder_name: string | null;
  task_identifier: string | null;  // Snapshot field from task.task_id
  prompt: string | null;  // Snapshot field from task.prompt
  task_id?: string | null;  // Backwards compatibility alias for task_identifier
  gym_id: string | null;  // Nullable for playground executions
  batch_id: string | null;
  number_of_iterations: number;
  model: ModelType;
  execution_type?: "batch" | "playground";  // Execution type
  playground_url?: string | null;  // URL for playground executions
  status: "pending" | "executing" | "passed" | "failed" | "crashed" | "timeout";
  eval_insights?: string | null;
  created_at: string;
  updated_at: string;
  execution_duration_seconds?: number | null;  // Total execution duration in seconds
}

export interface ExecutionStatusSummary {
  total_iterations: number;
  passed_count: number;
  failed_count: number;
  crashed_count: number;
  timeout_count: number;
  pending_count: number;
  executing_count: number;
}

export interface TaskStatusSummary {
  task_id: string;
  task_uuid: string;
  prompt: string;
  status: "pending" | "executing" | "passed" | "failed" | "crashed" | "timeout";
  total_iterations: number;
  passed_count: number;
  failed_count: number;
  crashed_count: number;
  timeout_count: number;
  pending_count: number;
  executing_count: number;
}

export interface ExecutionWithStatus extends Execution {
  status_summary: ExecutionStatusSummary;
  tasks: TaskStatusSummary[];
}

export interface ExecutionCreateRequest {
  task_identifier?: string;  // Snapshot field
  prompt?: string;  // Snapshot field
  task_id?: string;  // Backwards compatibility alias for task_identifier
  gym_id?: string | null;  // Nullable for playground executions
  batch_id?: string;
  number_of_iterations: number;
  model: ModelType;
  execution_type?: "batch" | "playground";  // Execution type
  playground_url?: string;  // URL for playground executions
  status?:
    | "pending"
    | "executing"
    | "passed"
    | "failed"
    | "crashed"
    | "timeout";
}

export interface ExecutionUpdateRequest {
  task_identifier?: string | null;  // Snapshot field
  prompt?: string | null;  // Snapshot field
  gym_id?: string;
  batch_id?: string | null;
  number_of_iterations?: number;
  model?: ModelType;
  status?:
    | "pending"
    | "executing"
    | "passed"
    | "failed"
    | "crashed"
    | "timeout";
}

export interface ExecutionListResponse {
  executions: Execution[];
  total: number;
  skip: number;
  limit: number;
}

// Legacy types for backward compatibility during migration

export interface Model {
  id: string;
  name: string;
  type: ModelType;
  description: string;
  api_key: string;
  created_at?: string;
  updated_at?: string;
}

// File-related types for execution monitoring
export interface ExecutionFile {
  path: string;
  name: string;
  type: "log" | "screenshot" | "json" | "csv" | "unknown";
  size: number;
  created_at: string;
  modified_at: string;
  extension: string;
  thumbnail?: string;
  relative_created_at?: string;
  seconds_into_execution?: number;
}

export interface DriveFolder {
  name: string;
  path: string;
  fileCount: number;
  subfolders: DriveFolder[];
  files: ExecutionFile[];
}

export interface ExecutionFileStructure {
  [key: string]: {
    screenshots?: ExecutionFile[];
    logs?: ExecutionFile[];
    [category: string]: ExecutionFile[] | undefined;
  };
}

export interface ExecutionFilesResponse {
  execution_id: string;
  execution_folder: string;
  total_files: number;
  structure?: ExecutionFileStructure;
  files?: ExecutionFile[];
}

export interface ExecutionSummary {
  execution_id: string;
  execution_folder: string;
  summary: {
    detailed_results?: Record<string, unknown>;
    execution_summary?: Record<string, unknown>;
    task_summary?: {
      file_path: string;
      size: number;
      modified_at: string;
    };
  };
}

// Execution progress types (per-iteration status)
export interface IterationProgressItem {
  uuid: string;
  iteration_number: number;
  status: "pending" | "executing" | "passed" | "failed" | "crashed" | "timeout";
  started_at?: string | null;
  completed_at?: string | null;
  execution_time_seconds?: number | null;
  verification_details?: string | null;
  verification_comments?: string | null;
  eval_insights?: string | null;
}

export interface ExecutionProgressSummaryCounts {
  total_iterations: number;
  pending_count: number;
  executing_count: number;
  passed_count: number;
  failed_count: number;
  crashed_count: number;
  timeout_count: number;
}

export interface TaskProgressItem {
  task_id: string;
  task_uuid: string;
  prompt: string;
  iterations: IterationProgressItem[];
}

export interface ExecutionProgress {
  execution_id: string;
  execution_status:
    | "pending"
    | "executing"
    | "passed"
    | "failed"
    | "crashed"
    | "timeout";
  total_iterations: number;
  completed_iterations: number;
  progress_percentage: number;
  summary: ExecutionProgressSummaryCounts;
  tasks: TaskProgressItem[];
  iterations: IterationProgressItem[]; // Keep for backward compatibility
}

export interface DriveViewState {
  currentPath: string[];
  searchTerm: string;
  viewMode: "grid" | "list";
  sortBy: "name" | "date" | "size" | "type";
  sortOrder: "asc" | "desc";
}

// API Error types
export interface APIError {
  detail: string;
  status_code?: number;
}

// Common API response patterns
export interface APIResponse<T> {
  data?: T;
  error?: APIError;
  message?: string;
}

// Authentication types
export interface User {
  uuid: string;
  email: string;
  name: string;
  picture?: string;
  is_admin: boolean;
  is_whitelisted: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login?: string;
  role?: "admin" | "user";
}

export interface AuthToken {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

// Reports: All Tasks Summary
export interface AllTasksSummaryResponse {
  summary: SummaryEntry[];
  tasks: Record<string, TaskDetailPayload>;
  total_tasks: number;
  total_iterations: number;
  filters: {
    gym_id: string | null;
    gym_name: string | null;
    start_date: string | null;
    end_date: string | null;
    default_start_date?: string | null;
    default_end_date?: string | null;
  };
}

export interface SummaryEntry {
  prompt: string;
  task: string;
  prompt_id?: string | null;
  claude_sonnet_4_breaking: string | null;
  openai_computer_use_preview_breaking: string | null;
  difficulty: string | null;
  task_start_time: string | null;
  task_end_time: string | null;
  source_total_time_seconds: number | null;
  source_total_time_formatted: string | null;
  wall_clock_seconds: number | null;
  wall_clock_formatted: string | null;
  average_iteration_minutes: number | null;
}

export interface ModelIterationEntry {
  iteration: number;
  model_response: string;
  tools_executed: string;
  status: string;
  comments: string;
  prompt_id?: string | null;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number | null;
  duration_formatted: string | null;
  run_id?: string | null;
  execution_uuid?: string | null;
  iteration_uuid?: string | null;
}

export interface ModelRunEntry {
  run_id: string;
  execution_id?: string | null;
  execution_model?: string | null;
  iterations: ModelIterationEntry[];
  iterations_count?: number | null;
  iterations_observed?: number | null;
  passes?: number | null;
  fails?: number | null;
  status_counts?: Record<string, number>;
  time_start?: string | null;
  time_end?: string | null;
  duration_seconds_avg?: number | null;
  duration_formatted_avg?: string | null;
  execution_iterations_planned?: number | null;
}

export interface TaskDetailPayload {
  prompt: string;
  totals: TaskTotals;
  per_model_iterations: Record<string, ModelIterationEntry[]>;
  per_model_runs?: Record<string, ModelRunEntry[]>;
}

export interface TaskTotals {
  iterations: number;
  passes: number;
  fails: number;
  wall_clock_seconds?: number;
  wall_clock_formatted?: string;
  source_total_time_seconds?: number;
  source_total_time_formatted?: string;
  average_iteration_minutes?: number;
}

export interface GoogleAuthRequest {
  code: string;
}

export interface WhitelistRequest {
  email: string;
  is_admin: boolean;
}

// Domain whitelist types
export interface Domain {
  uuid: string;
  domain: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DomainCreateRequest {
  domain: string;
  is_active?: boolean;
}

export interface DomainUpdateRequest {
  is_active: boolean;
}

export interface DomainListResponse {
  domains: Domain[];
  total: number;
}

export interface WhitelistDomainRequest {
  domain: string;
}

// Batch Iteration Summary types
export interface IterationCounts {
  pending: number;
  executing: number;
  passed: number;
  failed: number;
  crashed: number;
}

export interface ExecutionIterationBreakdown {
  execution_id: string;
  task_id: string | null;
  task_name: string;
  model: string;
  total_iterations: number;
  iteration_counts: IterationCounts;
}

export interface OverallIterationSummary {
  total_executions: number;
  total_iterations: number;
  iteration_counts: IterationCounts;
}

export interface BatchIterationSummary {
  batch_id: string;
  batch_name: string;
  overall_summary: OverallIterationSummary;
  execution_breakdowns: ExecutionIterationBreakdown[];
  generated_at: string;
}

// Leaderboard types
export interface LeaderboardGymStats {
  gym_id: string;
  gym_name: string;
  passed_count: number;
  failed_count: number;
  total_count: number;
  fail_percentage: number;
}

export interface LeaderboardModelGymStats {
  model: string;
  gym_id: string;
  gym_name: string;
  passed_count: number;
  failed_count: number;
  total_count: number;
  fail_percentage: number;
}

export interface LeaderboardModelStats {
  model: string;
  passed_count: number;
  failed_count: number;
  total_count: number;
  fail_percentage: number;
}

export interface LeaderboardResponse {
  overall_passed_count: number;
  overall_failed_count: number;
  overall_total_count: number;
  overall_fail_percentage: number;
  gym_stats: LeaderboardGymStats[];
  model_gym_stats: LeaderboardModelGymStats[];
  model_stats: LeaderboardModelStats[];
}

// =============================================================================
// Action Timeline Types (for iteration monitoring)
// =============================================================================

export type TimelineEntryType = "model_thinking" | "model_response" | "action";

export type ActionType =
  | "computer_action"
  | "bash_command"
  | "editor_action"
  | "navigate"
  | "screenshot"
  | "click"
  | "type"
  | "scroll"
  | "key_press"
  | "other";

export type ActionStatus = "success" | "failed" | "pending";

export interface TimelineEntry {
  id: string;
  timestamp: string;
  entry_type: TimelineEntryType;
  sequence_index: number;
}

export interface ModelThinkingEntry extends TimelineEntry {
  entry_type: "model_thinking";
  content: string;
}

export interface ModelResponseEntry extends TimelineEntry {
  entry_type: "model_response";
  content: string;
}

export interface ActionEntry extends TimelineEntry {
  entry_type: "action";
  action_type: ActionType;
  action_name: string;
  description: string;
  screenshot_path?: string; // Legacy field
  screenshot_before?: string; // Screenshot BEFORE action (showing what will be done)
  screenshot_after?: string; // Screenshot AFTER action (showing result)
  current_url?: string;
  status: ActionStatus;
  metadata: Record<string, unknown>;
}

export type TimelineEntryUnion =
  | ModelThinkingEntry
  | ModelResponseEntry
  | ActionEntry;

export interface TimelineResponse {
  entries: TimelineEntryUnion[];
  total_entries: number;
  total_actions: number;
  execution_id: string;
  iteration_id: string;
}

export interface PlaybackState {
  currentIndex: number;
  isPlaying: boolean;
  speed: number; // 0.5, 1, 2, 4
}

export interface PlaybackControls {
  play: () => void;
  pause: () => void;
  next: () => void;
  previous: () => void;
  setSpeed: (speed: number) => void;
  jumpTo: (index: number) => void;
}

export interface ConnectionState {
  status: "disconnected" | "connecting" | "connected" | "error";
  reconnectAttempts?: number;
  lastUpdate?: Date;
  error?: string;
}
