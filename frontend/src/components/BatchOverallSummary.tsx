import { useState } from "react";
import {
  Box,
  Typography,
  LinearProgress,
  Chip,
  Skeleton,
  Alert,
  Tooltip,
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
import type { BatchIterationSummary, OverallIterationSummary } from "../types";
import FailureDiagnosticsPanel from "./FailureDiagnosticsPanel";

interface BatchOverallSummaryProps {
  summary: OverallIterationSummary | undefined;
  isLoading: boolean;
  error: Error | null;
  generatedAt?: BatchIterationSummary["generated_at"];
  batchName?: string;
  batchId?: string;
}

function getRelativeTimeString(dateIso?: string) {
  if (!dateIso) return null;
  const now = Date.now();
  const updated = new Date(dateIso).getTime();
  if (Number.isNaN(updated)) return null;
  const diffMs = now - updated;
  const diffSeconds = Math.round(diffMs / 1000);
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays}d ago`;
}

export default function BatchOverallSummary({
  summary,
  isLoading,
  error,
  generatedAt,
  batchName,
  batchId,
}: BatchOverallSummaryProps) {
  const theme = useTheme();
  const [showFailureDiagnostics, setShowFailureDiagnostics] = useState(false);

  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 3 }}>
        Failed to load iteration analytics: {error.message}
      </Alert>
    );
  }

  if (isLoading || !summary) {
    return (
      <Box sx={{ mb: 3, display: "flex", flexDirection: "column", gap: 2 }}>
        <Skeleton variant="text" width="40%" height={32} />
        <Skeleton variant="rectangular" height={10} sx={{ borderRadius: 2 }} />
        <Box display="grid" gridTemplateColumns={{ xs: "1fr", sm: "repeat(2, 1fr)" }} gap={1.5}>
          <Skeleton variant="rectangular" height={64} sx={{ borderRadius: 2 }} />
          <Skeleton variant="rectangular" height={64} sx={{ borderRadius: 2 }} />
          <Skeleton variant="rectangular" height={64} sx={{ borderRadius: 2 }} />
          <Skeleton variant="rectangular" height={64} sx={{ borderRadius: 2 }} />
        </Box>
      </Box>
    );
  }

  const { total_executions, total_iterations, iteration_counts } = summary;
  const { passed, failed, executing, crashed, pending } = iteration_counts;

  const completedIterations = passed + failed + crashed;
  const progressPercentage = total_iterations
    ? Math.round((completedIterations / total_iterations) * 100)
    : 0;
  const successRate = total_iterations ? Math.round((passed / total_iterations) * 100) : 0;
  const inProgressCount = executing + pending;
  const lastUpdated = getRelativeTimeString(generatedAt);

  const palette = {
    passed: theme.palette.success.main,
    failed: theme.palette.error.main,
    crashed: theme.palette.error.dark,
    executing: theme.palette.warning.main,
  } as const;

  const metrics = [
    {
      key: "passed",
      icon: <PassedIcon sx={{ color: alpha(palette.passed, 0.7) }} />,
      title: "Success rate",
      value: `${successRate}%`,
      helper: `${passed}/${total_iterations} iterations passed`,
      tone: palette.passed,
    },
    {
      key: "failed",
      icon: <FailedIcon sx={{ color: alpha(palette.failed, 0.7) }} />,
      title: "Failed",
      value: failed,
      helper: `${failed} iteration${failed !== 1 ? "s" : ""} failed`,
      tone: failed ? palette.failed : alpha(palette.failed, 0.45),
      clickable: failed > 0 && batchId,
      onClick: failed > 0 && batchId ? () => setShowFailureDiagnostics(!showFailureDiagnostics) : undefined,
    },
    {
      key: "crashed",
      icon: <CrashedIcon sx={{ color: alpha(palette.crashed, 0.7) }} />,
      title: "Crashed",
      value: crashed,
      helper: `${crashed} iteration${crashed !== 1 ? "s" : ""} crashed`,
      tone: crashed ? palette.crashed : alpha(palette.crashed, 0.45),
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
            {batchName ? `${batchName} • ` : ""}
            {total_iterations} iteration{total_iterations !== 1 ? "s" : ""} • {total_executions} run
            {total_executions !== 1 ? "s" : ""}
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
          {lastUpdated && (
            <Tooltip title={new Date(generatedAt as string).toLocaleString()}>
              <Chip
                label={`Updated ${lastUpdated}`}
                size="small"
                variant="outlined"
                sx={{ borderColor: theme.palette.divider, color: "text.secondary" }}
              />
            </Tooltip>
          )}
        </Box>
      </Box>

      <Box>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.75}>
          <Typography variant="body2" color="text.secondary">
            Completion
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {progressPercentage}% ({completedIterations}/{total_iterations})
          </Typography>
        </Box>
        <LinearProgress
          variant="determinate"
          value={progressPercentage}
          sx={{
            height: 10,
            borderRadius: 2,
            bgcolor: theme.palette.grey[900] ? `${theme.palette.grey[900]}33` : "rgba(255,255,255,0.06)",
            "& .MuiLinearProgress-bar": {
              borderRadius: 2,
              backgroundColor: palette.passed,
              boxShadow: `0 0 8px ${alpha(palette.passed, 0.35)}`,
            },
          }}
        />
      </Box>

      <Box
        display="grid"
        gridTemplateColumns={{ xs: "repeat(auto-fit, minmax(180px, 1fr))" }}
        gap={1.5}
      >
        {metrics.map((metric) => (
          <Paper
            key={metric.title}
            onClick={metric.onClick}
            sx={{
              p: 1.5,
              borderRadius: 2,
              display: "flex",
              gap: 1.25,
              alignItems: "center",
              backgroundColor: theme.palette.background.paper,
              border: `1px solid ${alpha(metric.tone, 0.25)}`,
              boxShadow: `0 6px 18px ${alpha(metric.tone, 0.08)}`,
              cursor: metric.clickable ? "pointer" : "default",
              transition: "all 0.2s ease-in-out",
              "&:hover": metric.clickable
                ? {
                    transform: "scale(1.02)",
                    boxShadow: `0 8px 24px ${alpha(metric.tone, 0.15)}`,
                    borderColor: alpha(metric.tone, 0.4),
                  }
                : {},
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

      {/* Failure Diagnostics Panel */}
      {showFailureDiagnostics && failed > 0 && batchId && (
        <Box sx={{ mt: 2 }}>
          <FailureDiagnosticsPanel batchId={batchId} failedCount={failed} />
        </Box>
      )}

    </Box>
  );
}
