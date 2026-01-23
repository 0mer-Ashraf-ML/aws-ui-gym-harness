import {
  Box,
  Typography,
  LinearProgress,
  Chip,
  Skeleton,
  Alert,
  useTheme,
  Paper,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import {
  CheckCircle as PassedIcon,
  Error as FailedIcon,
  BugReport as CrashedIcon,
  Bolt as ExecutingIcon,
} from "@mui/icons-material";
import type { Execution, ExecutionProgress } from "../types";
import { getStatusDisplayLabel } from "../utils/runUtils";

interface ExecutionOverallSummaryProps {
  execution: Execution | undefined;
  isLoading: boolean;
  error: Error | null;
  progressData?: ExecutionProgress;
}

export default function ExecutionOverallSummary({
  execution,
  isLoading,
  error,
  progressData,
}: ExecutionOverallSummaryProps) {
  const theme = useTheme();

  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 3 }}>
        Failed to load execution summary: {error.message}
      </Alert>
    );
  }

  if (isLoading || !execution) {
    return (
      <Box sx={{ mb: 3, display: "flex", flexDirection: "column", gap: 2 }}>
        <Skeleton variant="text" width="40%" height={32} />
        <Skeleton variant="rectangular" height={10} sx={{ borderRadius: 2 }} />
        <Box display="grid" gridTemplateColumns={{ xs: "1fr", sm: "repeat(2, 1fr)", md: "repeat(4, 1fr)" }} gap={1.5}>
          <Skeleton variant="rectangular" height={64} sx={{ borderRadius: 2 }} />
          <Skeleton variant="rectangular" height={64} sx={{ borderRadius: 2 }} />
          <Skeleton variant="rectangular" height={64} sx={{ borderRadius: 2 }} />
          <Skeleton variant="rectangular" height={64} sx={{ borderRadius: 2 }} />
        </Box>
      </Box>
    );
  }

  // Calculate counts from progressData if available, otherwise use status_summary
  let passed = 0;
  let failed = 0;
  let executing = 0;
  let crashed = 0;
  let pending = 0;
  let timeout = 0;

  if (progressData && progressData.tasks) {
    // Calculate from actual iteration statuses
    progressData.tasks.forEach(task => {
      task.iterations.forEach(iteration => {
        const status = iteration.status.toLowerCase();
        if (status === "passed") passed++;
        else if (status === "failed") failed++;
        else if (status === "executing") executing++;
        else if (status === "crashed") crashed++;
        else if (status === "pending") pending++;
        else if (status === "timeout") timeout++;
      });
    });
  } else if (execution && 'status_summary' in execution && execution.status_summary) {
    // Fallback to status_summary (for ExecutionWithStatus type)
    const statusSummary = (execution as any).status_summary;
    passed = statusSummary.passed_count || 0;
    failed = statusSummary.failed_count || 0;
    executing = statusSummary.executing_count || 0;
    crashed = statusSummary.crashed_count || 0;
    pending = statusSummary.pending_count || 0;
    timeout = statusSummary.timeout_count || 0;
  }

  const totalIterations = execution.number_of_iterations || 0;

  const completedIterations = passed + failed + crashed + timeout;
  const progressPercentage = totalIterations
    ? Math.round((completedIterations / totalIterations) * 100)
    : 0;
  const successRate = totalIterations ? Math.round((passed / totalIterations) * 100) : 0;
  const inProgressCount = executing + pending;

  const palette = {
    passed: theme.palette.success.main,
    failed: theme.palette.error.main,
    crashed: theme.palette.error.dark,
    executing: theme.palette.warning.main,
    timeout: theme.palette.error.light,
  } as const;

  const passedLabel = getStatusDisplayLabel("passed", execution.execution_type);
  const metrics = [
    {
      key: "passed",
      icon: <PassedIcon sx={{ color: alpha(palette.passed, 0.7) }} />,
      title: "Success rate",
      value: `${successRate}%`,
      helper: `${passed}/${totalIterations} iterations ${passedLabel.toLowerCase()}`,
      tone: palette.passed,
    },
    {
      key: "failed",
      icon: <FailedIcon sx={{ color: alpha(palette.failed, 0.7) }} />,
      title: "Failed",
      value: failed,
      helper: `${failed} iteration${failed !== 1 ? "s" : ""} failed`,
      tone: failed ? palette.failed : alpha(palette.failed, 0.45),
    },
    {
      key: "crashed",
      icon: <CrashedIcon sx={{ color: alpha(palette.crashed, 0.7) }} />,
      title: "Crashed",
      value: crashed + timeout,
      helper: `${crashed} crashed • ${timeout} timeout`,
      tone: (crashed + timeout) ? palette.crashed : alpha(palette.crashed, 0.45),
    },
    {
      key: "executing",
      icon: <ExecutingIcon sx={{ color: alpha(palette.executing, 0.7) }} />,
      title: "In progress",
      value: inProgressCount,
      helper: `${executing} executing • ${pending} pending`,
      tone: inProgressCount ? palette.executing : alpha(palette.executing, 0.5),
    },
  ];

  return (
    <Box component="section" sx={{ display: "flex", flexDirection: "column", gap: 2.5, mb: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" rowGap={1.5}>
        <Box>
          <Typography variant="h6" component="h2" fontWeight={600}>
            Iteration Analytics
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {totalIterations} iteration{totalIterations !== 1 ? "s" : ""} • {execution.model.toUpperCase()}
          </Typography>
        </Box>
        <Box display="flex" alignItems="center" gap={1}>
          {executing > 0 && (
            <Chip
              icon={<ExecutingIcon sx={{ fontSize: 16, color: "inherit" }} />}
              label="Live refresh"
              size="small"
              sx={{
                fontWeight: 600,
                borderRadius: 1.5,
                paddingX: 1,
                color: theme.palette.common.white,
                backgroundColor: `${theme.palette.warning.main}55`,
                border: "1px solid rgba(255,255,255,0.35)",
                animation: "pulse 2.5s ease-in-out infinite",
                "@keyframes pulse": {
                  "0%,100%": { opacity: 1 },
                  "50%": { opacity: 0.45 },
                },
                "& .MuiChip-icon": {
                  color: theme.palette.common.white,
                },
              }}
            />
          )}
        </Box>
      </Box>

      {totalIterations > 1 && (
        <Box>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.75}>
            <Typography variant="body2" color="text.secondary">
              Completion
            </Typography>
            <Typography variant="body2" fontWeight={600}>
              {progressPercentage}% ({completedIterations}/{totalIterations})
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={progressPercentage}
            sx={{
              height: 6,
              borderRadius: 1,
              bgcolor: theme.palette.grey[900] ? `${theme.palette.grey[900]}33` : "rgba(255,255,255,0.06)",
              "& .MuiLinearProgress-bar": {
                borderRadius: 1,
                backgroundColor: palette.passed,
                boxShadow: `0 0 6px ${alpha(palette.passed, 0.3)}`,
              },
            }}
          />
        </Box>
      )}

      <Box
        display="grid"
        gridTemplateColumns={{ xs: "repeat(auto-fit, minmax(180px, 1fr))" }}
        gap={1.5}
      >
        {metrics.map((metric) => (
          <Paper
            key={metric.title}
            sx={{
              p: 1.5,
              borderRadius: 2,
              display: "flex",
              gap: 1.25,
              alignItems: "center",
              backgroundColor: theme.palette.background.paper,
              border: `1px solid ${alpha(metric.tone, 0.25)}`,
              boxShadow: `0 6px 18px ${alpha(metric.tone, 0.08)}`,
            }}
          >
            <Box
              sx={{
                width: 38,
                height: 38,
                borderRadius: 1.5,
                display: "grid",
                placeItems: "center",
                backgroundColor: alpha(metric.tone, 0.12),
              }}
            >
              {metric.icon}
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary" sx={{ textTransform: "uppercase", letterSpacing: 0.5 }}>
                {metric.title}
              </Typography>
              <Typography
                variant="h5"
                fontWeight={700}
                lineHeight={1.05}
                sx={{ letterSpacing: 0.2 }}
              >
                {metric.value}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {metric.helper}
              </Typography>
            </Box>
          </Paper>
        ))}
      </Box>
    </Box>
  );
}
