import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Breadcrumbs,
  Chip,
  Collapse,
  IconButton,
  LinearProgress,
  Link as MLink,
  Paper,
  Slide,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  Download as DownloadIcon,
  Assessment as AssessmentIcon,
  KeyboardArrowDown as KeyboardArrowDownIcon,
  KeyboardArrowUp as KeyboardArrowUpIcon,
} from "@mui/icons-material";
import { Link as RouterLink, useParams, useLocation } from "react-router-dom";

import PageHeader from "../components/PageHeader";
import { useGyms } from "../hooks/useGyms";
import { executionApi } from "../services/api";
import type { TaskDetailPayload, TaskTotals, ModelIterationEntry } from "../types";
import { getStatusColor } from "../utils/sharedStyles";

type RunSummaryRow = {
  id: string;
  model_key: string;
  model_label: string;
  run_id: string;
  execution_id?: string | null;
  time_start: string | null;
  time_end: string | null;
  avg_duration_seconds: number | null;
  avg_duration_formatted: string | null;
  iterations_count: number | null;
  iterations: ModelIterationEntry[];
  status_counts?: Record<string, number> | undefined;
};

type ModelSummaryBlock = {
  model_key: string;
  model_label: string;
  runs_count: number;
  time_start: string | null;
  time_end: string | null;
  avg_duration_formatted: string | null;
  runs: RunSummaryRow[];
};

const formatDuration = (seconds: number | null | undefined): string | null => {
  if (seconds == null || Number.isNaN(seconds)) return null;
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600)
    .toString()
    .padStart(2, "0");
  const minutes = Math.floor((total % 3600) / 60)
    .toString()
    .padStart(2, "0");
  const secs = Math.floor(total % 60)
    .toString()
    .padStart(2, "0");
  return `${hours}:${minutes}:${secs}`;
};

const formatModelLabel = (key: string): string =>
  key
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ") || key;

const formatDateTime = (value: string | null): string => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
};

const formatDisplayDate = (value?: string | null): string => {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
};

const summariseModelBlock = (
  modelKey: string,
  modelLabel: string,
  runs: RunSummaryRow[],
): ModelSummaryBlock => {
  const timeStart = runs
    .map((run) => run.time_start)
    .filter((value): value is string => Boolean(value))
    .reduce<string | null>((min, current) => {
      if (!min || current < min) return current;
      return min;
    }, null);

  const timeEnd = runs
    .map((run) => run.time_end)
    .filter((value): value is string => Boolean(value))
    .reduce<string | null>((max, current) => {
      if (!max || current > max) return current;
      return max;
    }, null);

  const durations = runs
    .map((run) => run.avg_duration_seconds)
    .filter((value): value is number => Number.isFinite(value));

  const averageDurationFormatted = durations.length
    ? formatDuration(durations.reduce((total, current) => total + current, 0) / durations.length)
    : null;

  return {
    model_key: modelKey,
    model_label: modelLabel,
    runs_count: runs.length,
    time_start: timeStart,
    time_end: timeEnd,
    avg_duration_formatted: averageDurationFormatted,
    runs,
  };
};

const STATUS_PRIORITY: Array<keyof Record<string, number>> = [
  "CRASHED",
  "FAILED",
  "TIMEOUT",
  "EXECUTING",
  "PASSED",
  "PENDING",
];

const normalizeStatusKey = (status: string | undefined | null): string =>
  (status ?? "").trim().toUpperCase();

const deriveRunStatus = (
  statusCounts: Record<string, number> | undefined,
  iterations: ModelIterationEntry[],
): string => {
  const counts: Record<string, number> = statusCounts ? { ...statusCounts } : {};

  if (Object.keys(counts).length === 0) {
    // Fallback to iteration data if no counts provided
    iterations.forEach((iteration) => {
      const key = normalizeStatusKey(iteration.status);
      if (!key) return;
      counts[key] = (counts[key] || 0) + 1;
    });
  }

  const normalizedCounts: Record<string, number> = {};
  Object.entries(counts).forEach(([key, value]) => {
    if (value == null) return;
    const normalizedKey = normalizeStatusKey(key);
    if (!normalizedKey) return;
    normalizedCounts[normalizedKey] = (normalizedCounts[normalizedKey] || 0) + Number(value);
  });

  for (const priority of STATUS_PRIORITY) {
    if ((normalizedCounts[priority] || 0) > 0) {
      return priority.toLowerCase();
    }
  }

  return "pending";
};

const formatStatusLabel = (status: string): string => {
  if (!status) return "Unknown";
  const lower = status.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
};

interface ModelRunsTableProps {
  runs: RunSummaryRow[];
  isLoading: boolean;
}

const ModelRunsTable = ({ runs, isLoading }: ModelRunsTableProps) => {
  const [expandedRuns, setExpandedRuns] = useState<Set<string>>(new Set());

  if (!runs.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No executions recorded for this model yet.
      </Typography>
    );
  }

  const toggleRun = (runId: string) => {
    setExpandedRuns((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) {
        next.delete(runId);
      } else {
        next.add(runId);
      }
      return next;
    });
  };

  return (
    <TableContainer component={Paper} variant="outlined">
      {isLoading && <LinearProgress />}
      <Table size="small" aria-label="model executions table">
        <TableHead>
          <TableRow>
            <TableCell width={48} />
            <TableCell sx={{ fontWeight: 600 }}>Execution</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
            <TableCell align="center" sx={{ fontWeight: 600 }}>
              Iterations
            </TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Time start</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Time end</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Duration (avg)</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {runs.map((run) => {
            const isExpanded = expandedRuns.has(run.id);
            const statusKey = deriveRunStatus(run.status_counts, run.iterations);
            const statusLabel = formatStatusLabel(statusKey);
            const statusCountsEntries = run.status_counts
              ? Object.entries(run.status_counts)
                  .map(([key, value]) => [formatStatusLabel(key), value] as const)
                  .filter(([, value]) => (value ?? 0) > 0)
              : [];

            const iterationsObserved = run.iterations.length;
            const plannedIterations = run.iterations_count;
            const iterationsLabel = plannedIterations
              ? `${iterationsObserved}/${plannedIterations}`
              : iterationsObserved || "—";

            const statusChipColor = getStatusColor(statusKey) as
              | "default"
              | "primary"
              | "secondary"
              | "error"
              | "info"
              | "success"
              | "warning";

            const countsTooltip = statusCountsEntries
              .map(([label, value]) => `${label}: ${value}`)
              .join("\n");

            return (
              <Fragment key={run.id}>
                <TableRow
                  hover
                  sx={{ cursor: "pointer" }}
                  onClick={() => toggleRun(run.id)}
                >
                  <TableCell>
                    <IconButton
                      size="small"
                      onClick={(event) => {
                        event.stopPropagation();
                        toggleRun(run.id);
                      }}
                      aria-label={
                        isExpanded
                          ? "Collapse iteration details"
                          : "Expand iteration details"
                      }
                    >
                      {isExpanded ? (
                        <KeyboardArrowUpIcon fontSize="small" />
                      ) : (
                        <KeyboardArrowDownIcon fontSize="small" />
                      )}
                    </IconButton>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {run.run_id || "—"}
                    </Typography>
                    {run.execution_id && (
                      <Typography variant="caption" color="text.secondary">
                        Execution ID: {run.execution_id}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={statusLabel}
                      color={statusChipColor}
                      sx={{ textTransform: "capitalize", mb: statusCountsEntries.length ? 0.5 : 0 }}
                    />
                    {statusCountsEntries.length > 0 && (
                      <Tooltip title={countsTooltip} placement="top" arrow>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                          {statusCountsEntries
                            .map(([label, value]) => `${label} ${value}`)
                            .join(" · ")}
                        </Typography>
                      </Tooltip>
                    )}
                  </TableCell>
                  <TableCell align="center">
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      {iterationsLabel}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    {formatDateTime(run.time_start)}
                  </TableCell>
                  <TableCell>
                    {formatDateTime(run.time_end)}
                  </TableCell>
                  <TableCell>
                    {run.avg_duration_formatted || (run.avg_duration_seconds != null ? formatDuration(run.avg_duration_seconds) : "—")}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={7}>
                    <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                      <Box sx={{ backgroundColor: "action.hover", p: 2, borderRadius: 1 }}>
                        {run.iterations.length === 0 ? (
                          <Typography variant="body2" color="text.secondary">
                            No iterations recorded for this execution.
                          </Typography>
                        ) : (
                          <Table size="small" aria-label="iteration details">
                            <TableHead>
                              <TableRow>
                                <TableCell sx={{ fontWeight: 600 }}>Iteration</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>Prompt ID</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>Model Response</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>Comments</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>Tools Executed</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>Start</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>End</TableCell>
                                <TableCell sx={{ fontWeight: 600 }}>Duration</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {run.iterations.map((iteration) => {
                                const iterationStatusKey = normalizeStatusKey(iteration.status);
                                const iterationStatusColor = getStatusColor(iterationStatusKey.toLowerCase()) as
                                  | "default"
                                  | "primary"
                                  | "secondary"
                                  | "error"
                                  | "info"
                                  | "success"
                                  | "warning";

                                const modelResponse = iteration.model_response?.trim() || "";
                                const truncatedResponse = modelResponse.length > 160
                                  ? `${modelResponse.slice(0, 160)}…`
                                  : modelResponse || "—";

                                const comments = iteration.comments?.trim() || "";
                                const truncatedComments = comments.length > 160
                                  ? `${comments.slice(0, 160)}…`
                                  : comments || "—";

                                const durationLabel =
                                  iteration.duration_formatted ||
                                  (typeof iteration.duration_seconds === "number"
                                    ? formatDuration(iteration.duration_seconds)
                                    : "—");

                                return (
                                  <TableRow key={`${run.id}-${iteration.iteration}-${iteration.run_id ?? ""}`} hover>
                                    <TableCell>
                                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                        {iteration.iteration ?? "—"}
                                      </Typography>
                                    </TableCell>
                                    <TableCell>
                                      {iteration.prompt_id || "—"}
                                    </TableCell>
                                    <TableCell>
                                      <Chip
                                        size="small"
                                        label={formatStatusLabel(iterationStatusKey)}
                                        color={iterationStatusColor}
                                        sx={{ textTransform: "capitalize" }}
                                      />
                                    </TableCell>
                                    <TableCell>
                                      <Tooltip title={modelResponse || "No response"} placement="top" arrow>
                                        <Typography
                                          variant="body2"
                                          sx={{
                                            maxWidth: 240,
                                            whiteSpace: "pre-wrap",
                                            wordBreak: "break-word",
                                          }}
                                        >
                                          {truncatedResponse}
                                        </Typography>
                                      </Tooltip>
                                    </TableCell>
                                    <TableCell>
                                      <Tooltip title={comments || "No comments"} placement="top" arrow>
                                        <Typography
                                          variant="body2"
                                          sx={{
                                            maxWidth: 200,
                                            whiteSpace: "pre-wrap",
                                            wordBreak: "break-word",
                                          }}
                                        >
                                          {truncatedComments}
                                        </Typography>
                                      </Tooltip>
                                    </TableCell>
                                    <TableCell>
                                      {iteration.tools_executed || "—"}
                                    </TableCell>
                                    <TableCell>{formatDateTime(iteration.start_time)}</TableCell>
                                    <TableCell>{formatDateTime(iteration.end_time)}</TableCell>
                                    <TableCell>{durationLabel}</TableCell>
                                  </TableRow>
                                );
                              })}
                            </TableBody>
                          </Table>
                        )}
                      </Box>
                    </Collapse>
                  </TableCell>
                </TableRow>
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
};

const buildFallbackSummary = (taskId: string): ModelSummaryBlock[] => {
  const placeholderRuns: RunSummaryRow[] = [
    {
      id: `${taskId}-placeholder-openai`,
      model_key: "openai_computer_use_preview",
      model_label: "OpenAI Computer Use Preview",
      run_id: "RUN-1",
      time_start: null,
      time_end: null,
      avg_duration_seconds: null,
      avg_duration_formatted: null,
      iterations_count: 0,
      iterations: [],
      status_counts: {},
    },
  ];

  return [
    summariseModelBlock("openai_computer_use_preview", "OpenAI Computer Use Preview", placeholderRuns),
  ];
};

const buildModelSummaries = (
  taskId: string,
  payload: TaskDetailPayload,
): ModelSummaryBlock[] => {
  const summaries: ModelSummaryBlock[] = [];

  const perModelRuns = payload.per_model_runs ?? {};
  const runKeys = Object.keys(perModelRuns);

  if (runKeys.length > 0) {
    runKeys.sort();
    runKeys.forEach((modelKey) => {
      const runEntries = perModelRuns[modelKey] ?? [];
      if (!runEntries.length) return;

      const rows: RunSummaryRow[] = runEntries.map((run, index) => {
        const averageSeconds =
          typeof run.duration_seconds_avg === "number" && Number.isFinite(run.duration_seconds_avg)
            ? run.duration_seconds_avg
            : null;
        const formattedAverage =
          averageSeconds != null
            ? formatDuration(averageSeconds)
            : run.duration_formatted_avg ?? null;

        const iterationsCount =
          typeof run.iterations_count === "number" && Number.isFinite(run.iterations_count)
            ? run.iterations_count
            : run.iterations?.length ?? null;

        const iterationEntries: ModelIterationEntry[] = Array.isArray(run.iterations)
          ? run.iterations.map((iteration) => ({
              iteration: typeof iteration.iteration === "number" ? iteration.iteration : Number(iteration.iteration) || 0,
              model_response: iteration.model_response ?? "",
              tools_executed: iteration.tools_executed ?? "No data",
              status: iteration.status ?? "UNKNOWN",
              comments: iteration.comments ?? "",
              prompt_id: iteration.prompt_id ?? null,
              start_time: iteration.start_time ?? null,
              end_time: iteration.end_time ?? null,
              duration_seconds:
                typeof iteration.duration_seconds === "number"
                  ? iteration.duration_seconds
                  : Number(iteration.duration_seconds) || null,
              duration_formatted: iteration.duration_formatted ?? null,
              run_id: iteration.run_id ?? run.run_id,
              execution_uuid: iteration.execution_uuid ?? run.execution_id ?? null,
              iteration_uuid: iteration.iteration_uuid ?? null,
            }))
          : [];

        iterationEntries.sort((a, b) => {
          const iterationDiff = (a.iteration ?? 0) - (b.iteration ?? 0);
          if (iterationDiff !== 0) return iterationDiff;
          const startA = a.start_time ?? "";
          const startB = b.start_time ?? "";
          if (startA !== startB) return startA.localeCompare(startB);
          return (a.run_id ?? "").localeCompare(b.run_id ?? "");
        });

        return {
          id: `${taskId}-${modelKey}-${run.run_id}-${index}`,
          model_key: modelKey,
          model_label: formatModelLabel(modelKey),
          run_id: run.run_id,
          execution_id: run.execution_id ?? null,
          time_start: run.time_start ?? null,
          time_end: run.time_end ?? null,
          avg_duration_seconds: averageSeconds,
          avg_duration_formatted: formattedAverage,
          iterations_count: iterationsCount ?? (iterationEntries.length || null),
          iterations: iterationEntries,
          status_counts: run.status_counts ?? undefined,
        };
      });

      rows.sort((a, b) => {
        const startA = a.time_start ?? "";
        const startB = b.time_start ?? "";
        if (startA !== startB) return startA.localeCompare(startB);
        return a.run_id.localeCompare(b.run_id);
      });

      summaries.push(
        summariseModelBlock(modelKey, formatModelLabel(modelKey), rows),
      );
    });

    return summaries.sort((a, b) => a.model_label.localeCompare(b.model_label));
  }

  const perModelIterations = payload.per_model_iterations || {};

  Object.entries(perModelIterations).forEach(([modelKey, iterations]) => {
    if (!iterations || iterations.length === 0) return;

    const runsMap = new Map<string, ModelIterationEntry[]>();

    iterations.forEach((iteration, index) => {
      const runId = iteration.run_id?.trim() || `iteration_${iteration.iteration || index + 1}`;
      const existing = runsMap.get(runId);
      if (existing) {
        existing.push(iteration);
      } else {
        runsMap.set(runId, [iteration]);
      }
    });

    const rows: RunSummaryRow[] = Array.from(runsMap.entries()).map(([runId, runIterations], index) => {
      runIterations.sort((a, b) => {
        const iterationDiff = (a.iteration ?? 0) - (b.iteration ?? 0);
        if (iterationDiff !== 0) return iterationDiff;
        const startA = a.start_time ?? "";
        const startB = b.start_time ?? "";
        if (startA !== startB) return startA.localeCompare(startB);
        return (a.run_id ?? "").localeCompare(b.run_id ?? "");
      });

      const startTimes = runIterations
        .map((iteration) => iteration.start_time)
        .filter((value): value is string => Boolean(value));
      const endTimes = runIterations
        .map((iteration) => iteration.end_time)
        .filter((value): value is string => Boolean(value));

      const earliestStart = startTimes.length
        ? startTimes.reduce((min, current) => (current < min ? current : min))
        : null;
      const latestEnd = endTimes.length
        ? endTimes.reduce((max, current) => (current > max ? current : max))
        : null;

      const durations = runIterations
        .map((iteration) => iteration.duration_seconds)
        .filter((value): value is number => Number.isFinite(value));

      const averageDurationSeconds = durations.length
        ? durations.reduce((total, current) => total + current, 0) / durations.length
        : null;

      const iterationsCount = runIterations.length;

      return {
        id: `${taskId}-${modelKey}-${runId}-${index}`,
        model_key: modelKey,
        model_label: formatModelLabel(modelKey),
        run_id: runId,
        execution_id: null,
        time_start: earliestStart,
        time_end: latestEnd,
        avg_duration_seconds: averageDurationSeconds,
        avg_duration_formatted:
          averageDurationSeconds != null ? formatDuration(averageDurationSeconds) : null,
        iterations_count: iterationsCount,
        iterations: runIterations,
        status_counts: undefined,
      };
    });

    rows.sort((a, b) => {
      const startA = a.time_start ?? "";
      const startB = b.time_start ?? "";
      if (startA !== startB) return startA.localeCompare(startB);
      return a.run_id.localeCompare(b.run_id);
    });

    summaries.push(
      summariseModelBlock(modelKey, formatModelLabel(modelKey), rows),
    );
  });

  return summaries.sort((a, b) => a.model_label.localeCompare(b.model_label));
};

const buildTotalsEntries = (totals: TaskTotals | null | undefined) => {
  if (!totals) return [] as Array<{ label: string; value: string | number | null }>;

  const entries: Array<{ label: string; value: string | number | null }> = [
    { label: "Iterations", value: totals.iterations },
    { label: "Passes", value: totals.passes },
    { label: "Fails", value: totals.fails },
  ];

  if (totals.wall_clock_formatted || totals.wall_clock_seconds !== undefined) {
    entries.push({
      label: "Wall clock",
      value: totals.wall_clock_formatted ?? formatDuration(totals.wall_clock_seconds),
    });
  }

  if (totals.source_total_time_formatted || totals.source_total_time_seconds !== undefined) {
    entries.push({
      label: "Source total",
      value:
        totals.source_total_time_formatted ?? formatDuration(totals.source_total_time_seconds),
    });
  }

  if (totals.average_iteration_minutes !== undefined) {
    entries.push({
      label: "Avg iteration (mins)",
      value:
        totals.average_iteration_minutes != null
          ? Math.round(totals.average_iteration_minutes * 100) / 100
          : null,
    });
  }

  return entries.filter((entry) => entry.value !== undefined && entry.value !== null && entry.value !== "");
};

export default function ReportTaskDetail() {
  const { taskId = "TASK-1" } = useParams<{ taskId: string }>();
  const location = useLocation();
  const { data: gyms } = useGyms();

  const queryFilters = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return {
      gymId: params.get("gymId") ?? undefined,
      start: params.get("start") ?? undefined,
      end: params.get("end") ?? undefined,
    };
  }, [location.search]);

  const requestFilters = useMemo(
    () => ({
      gym_id: queryFilters.gymId || undefined,
      start_date: queryFilters.start || undefined,
      end_date: queryFilters.end || undefined,
    }),
    [queryFilters],
  );

  const selectedGymName = useMemo(() => {
    if (!requestFilters.gym_id) return null;
    const match = gyms?.find((gym) => gym.uuid === requestFilters.gym_id);
    return match?.name || requestFilters.gym_id;
  }, [gyms, requestFilters.gym_id]);

  const [taskPayload, setTaskPayload] = useState<TaskDetailPayload | null>(null);
  const [modelSummaries, setModelSummaries] = useState<ModelSummaryBlock[]>(buildFallbackSummary(taskId));
  const [totals, setTotals] = useState<TaskTotals | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  useEffect(() => {
    setModelSummaries(buildFallbackSummary(taskId));
    setTaskPayload(null);
    setTotals(null);
    setError(null);
  }, [taskId, requestFilters.gym_id, requestFilters.start_date, requestFilters.end_date]);

  const fetchTaskDetails = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const response = await executionApi.getAllTasksSummary({
        include_task_details: true,
        gym_id: requestFilters.gym_id,
        start_date: requestFilters.start_date,
        end_date: requestFilters.end_date,
      });

      const payload: TaskDetailPayload | undefined = response.tasks?.[taskId];
      if (!payload) {
        setTaskPayload(null);
        setTotals(null);
        setError(`No data available for task ${taskId}.`);
        return;
      }

      const summaries = buildModelSummaries(taskId, payload);
      setModelSummaries(summaries);
      setTaskPayload(payload);
      setTotals(payload.totals ?? null);
    } catch (e: any) {
      setTaskPayload(null);
      setTotals(null);
      setError(e?.message || "Failed to load task details");
    } finally {
      setIsLoading(false);
    }
  }, [taskId, requestFilters]);

  useEffect(() => {
    void fetchTaskDetails();
  }, [fetchTaskDetails]);

  const totalsEntries = useMemo(() => buildTotalsEntries(totals), [totals]);

  return (
    <Slide direction="up" in mountOnEnter unmountOnExit>
      <Box>
        <Box sx={{ mb: 2 }}>
          <Breadcrumbs aria-label="breadcrumb">
            <MLink component={RouterLink} color="inherit" to="/reports" underline="hover">
              Reports
            </MLink>
            <MLink color="text.primary" underline="none">
              {taskId}
            </MLink>
          </Breadcrumbs>
        </Box>

        <PageHeader
          icon={<AssessmentIcon sx={{ fontSize: 48 }} />}
          title={`Task Reports: ${taskId}`}
          description="Detailed results for this task across all models"
          searchPlaceholder=""
          searchValue=""
          onSearchChange={() => {}}
          customLeftControls={
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="body2" color="text.secondary">
                Filters
              </Typography>
              <Chip label={`Gym: ${selectedGymName ?? "All"}`} size="small" color="default" />
              <Chip
                label={`Start: ${formatDisplayDate(requestFilters.start_date)}`}
                size="small"
                color="default"
              />
              <Chip
                label={`End: ${formatDisplayDate(requestFilters.end_date)}`}
                size="small"
                color="default"
              />
            </Stack>
          }
          primaryButton={{
            label: "Refresh",
            icon: <AssessmentIcon />,
            onClick: () => {
              void fetchTaskDetails();
            },
          }}
          secondaryButton={{
            label: isDownloading ? "Preparing report..." : "Download Report",
            icon: <DownloadIcon />,
            onClick: async () => {
              try {
                setIsDownloading(true);
                setDownloadError(null);
                await executionApi.downloadAllTasksSummaryReport({
                  gym_id: requestFilters.gym_id,
                  start_date: requestFilters.start_date,
                  end_date: requestFilters.end_date,
                  include_snapshot: false,
                });
              } catch (downloadErr) {
                const message = downloadErr instanceof Error ? downloadErr.message : "Failed to download report";
                setDownloadError(message);
              } finally {
                setIsDownloading(false);
              }
            },
            disabled: isDownloading,
          }}
        />

        {downloadError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {downloadError}
          </Alert>
        )}

        {error ? (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        ) : (
          <>
            <Stack spacing={3} sx={{ mb: 4 }}>
              <Paper sx={{ p: 3, borderRadius: 2, border: "1px solid", borderColor: "divider" }} elevation={0}>
                <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                  Prompt
                </Typography>
                <Typography variant="body1" sx={{ whiteSpace: "pre-wrap" }}>
                  {taskPayload?.prompt || "No prompt available."}
                </Typography>
              </Paper>

              {totalsEntries.length > 0 && (
                <Box>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                    Totals
                  </Typography>
                  <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
                    {totalsEntries.map(({ label, value }) => (
                      <Box
                        key={label}
                        sx={{
                          minWidth: 180,
                          border: "1px solid",
                          borderColor: "divider",
                          borderRadius: 2,
                          p: 2,
                          backgroundColor: "background.paper",
                        }}
                      >
                        <Typography variant="caption" color="text.secondary">
                          {label}
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {value ?? "—"}
                        </Typography>
                      </Box>
                    ))}
                  </Stack>
                </Box>
              )}
            </Stack>

            {modelSummaries.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No execution data available for this task.
              </Typography>
            ) : (
              modelSummaries.map((summary) => (
                <Box key={summary.model_key} sx={{ mb: 4 }}>
                  <Stack
                    direction="row"
                    spacing={2}
                    alignItems="center"
                    sx={{ mb: 1 }}
                    flexWrap="wrap"
                    useFlexGap
                  >
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {summary.model_label}
                    </Typography>
                    <Chip label={`${summary.runs_count} execution${summary.runs_count === 1 ? "" : "s"}`} size="small" />
                    {summary.avg_duration_formatted && (
                      <Chip label={`Avg duration: ${summary.avg_duration_formatted}`} size="small" />
                    )}
                    {summary.time_start && summary.time_end && (
                      <Typography variant="caption" color="text.secondary">
                        {formatDateTime(summary.time_start)} → {formatDateTime(summary.time_end)}
                      </Typography>
                    )}
                  </Stack>

                  <ModelRunsTable runs={summary.runs} isLoading={isLoading} />
                </Box>
              ))
            )}
          </>
        )}
      </Box>
    </Slide>
  );
}
