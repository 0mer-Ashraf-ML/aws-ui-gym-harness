import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Card,
  CardContent,
  CardActions,
  Typography,
  Box,
  IconButton,
  Tooltip,
  Link,
  LinearProgress,
  Chip,
  Skeleton,
} from "@mui/material";
import {
  Schedule as IterationsIcon,
  Visibility as ViewDetailsIcon,
  CheckCircle as PassedIcon,
  Error as FailedIcon,
  Schedule as PendingIcon,
  Bolt as ExecutingIcon,
  BugReport as CrashedIcon,
} from "@mui/icons-material";
import type { Execution, IterationCounts } from "../types";
import { useDeleteRun } from "../hooks/useRuns";
import { useBatch } from "../hooks/useBatch";
import { useAuth } from "../contexts/AuthContext";
import {
  RunStatusChip,
  UuidDisplay,
  DateDisplay,
  ModelDisplay,
  getStatusDisplayLabel,
} from "../utils/runUtils";
import {
  runActionConfig,
  runCardStyles,
  formatIterations,
} from "../utils/sharedStyles";
import {
  DeleteConfirmationModal,
  DetailModal,
  DetailContent,
  DetailSection,
  DetailFields,
  DetailField,
} from "./shared";

interface RunCardProps {
  run: Execution;
  onEdit: (run: Execution) => void;
  gymName?: string;
  taskIdentifier?: string;
  taskPrompt?: string;
  hideEditButton?: boolean;
  iterationStats?: IterationCounts;
}

export default function RunCard({
  run,
  onEdit,
  gymName,
  taskIdentifier,
  taskPrompt,
  hideEditButton = false,
  iterationStats,
}: RunCardProps) {
  const navigate = useNavigate();
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const deleteRunMutation = useDeleteRun();
  const { data: batch } = useBatch(run.batch_id);
  const { isAdmin } = useAuth();

  const handleDelete = () => {
    deleteRunMutation.mutate(run.uuid, {
      onSuccess: () => {
        setDeleteConfirmOpen(false);
      },
      onError: (error) => {
        console.error("Failed to delete run:", error);
        const errorMessage =
          error instanceof Error ? error.message : "Unknown error occurred";
        alert(`Failed to delete run: ${errorMessage}`);
        setDeleteConfirmOpen(false);
      },
    });
  };

  const canModify = run.status !== "executing" && run.status !== "pending";
  
  // Non-admin users cannot delete batch-owned runs
  const canDelete = canModify && (!run.batch_id || isAdmin);

  const totalIterationsPlanned = run.number_of_iterations ?? 0;
  const stats = iterationStats;
  const completedIterations = stats
    ? stats.passed + stats.failed + stats.crashed
    : 0;
  const inProgressIterations = stats
    ? stats.executing + stats.pending
    : 0;
  const successRate = totalIterationsPlanned
    ? Math.round(((stats?.passed ?? 0) / totalIterationsPlanned) * 100)
    : 0;
  const completionPercent = totalIterationsPlanned
    ? Math.round((completedIterations / totalIterationsPlanned) * 100)
    : 0;
  const hasStats = Boolean(stats);

  const statusBreakdown = [
    {
      key: "passed",
      label: getStatusDisplayLabel("passed", run.execution_type),
      value: stats?.passed ?? 0,
      color: "default" as const,
      icon: <PassedIcon sx={{ fontSize: 14 }} />,
    },
    {
      key: "executing",
      label: "Executing",
      value: stats?.executing ?? 0,
      color: "warning" as const,
      icon: <ExecutingIcon sx={{ fontSize: 14 }} />,
    },
    {
      key: "pending",
      label: "Pending",
      value: stats?.pending ?? 0,
      color: "info" as const,
      icon: <PendingIcon sx={{ fontSize: 14 }} />,
    },
    {
      key: "failed",
      label: "Failed",
      value: stats?.failed ?? 0,
      color: "error" as const,
      icon: <FailedIcon sx={{ fontSize: 14 }} />,
    },
    {
      key: "crashed",
      label: "Crashed",
      value: stats?.crashed ?? 0,
      color: "error" as const,
      icon: <CrashedIcon sx={{ fontSize: 14 }} />,
    },
  ].filter((item) => item.value > 0);

  return (
    <>
      <Card
        sx={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
          cursor: "pointer",
          transition: "all 0.2s ease-in-out",
          "&:hover": {
            boxShadow: 6,
            transform: "translateY(-2px)",
          },
          borderRadius: 2,
        }}
        onClick={() => {
          // Use batch-aware URL if execution is part of a batch
          if (run.batch_id) {
            navigate(`/batches/${run.batch_id}/executions/${run.uuid}/monitor`);
          } else {
            navigate(`/executions/${run.uuid}/monitor`);
          }
        }}
      >
        <CardContent sx={{ flexGrow: 1, pb: 1 }}>
          {/* Header with UUID and Status */}
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              mb: 2,
            }}
          >
            <Box>
              <Typography variant="h6" component="h2" sx={{ fontWeight: 600 }}>
                Run
              </Typography>
              <UuidDisplay uuid={run.uuid} copyable={true} />
            </Box>
            <RunStatusChip
              status={run.status}
              showProgress={true}
              size="small"
              executionType={run.execution_type}
            />
          </Box>

          {/* Content */}
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
            {/* Model */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ minWidth: 50 }}
              >
                Model:
              </Typography>
              <ModelDisplay model={run.model} size="small" />
            </Box>

            {/* Gym / URL (for playground) */}
            {(run as any).execution_type === "playground" ? (
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ minWidth: 50 }}
                >
                  URL:
                </Typography>
                <Link
                  href={(run as any).playground_url || ""}
                  target="_blank"
                  rel="noopener noreferrer"
                  variant="body2"
                  sx={{ fontWeight: 500, maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis" }}
                  title={(run as any).playground_url || ""}
                >
                  {(run as any).playground_url || "No URL"}
                </Link>
              </Box>
            ) : (
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ minWidth: 50 }}
                >
                  Gym:
                </Typography>
                <Typography
                  variant="body2"
                  color="text.primary"
                  sx={{ fontWeight: 500 }}
                  title={gymName || run.gym_id || ""}
                >
                  {gymName || run.gym_id || "No gym"}
                </Typography>
              </Box>
            )}

            {/* Task Identifier / Prompt (for playground) */}
            {(run as any).execution_type === "playground" ? (
              <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ minWidth: 50 }}
                >
                  Prompt:
                </Typography>
                <Typography
                  variant="body2"
                  color="text.primary"
                  sx={{ fontWeight: 500, flex: 1 }}
                  title={run.prompt || "No prompt"}
                >
                  {run.prompt ? (run.prompt.length > 100 ? `${run.prompt.slice(0, 100)}...` : run.prompt) : "No prompt"}
                </Typography>
              </Box>
            ) : (
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ minWidth: 50 }}
                >
                  Task:
                </Typography>
                <Typography
                  variant="body2"
                  color="text.primary"
                  sx={{ fontWeight: 500 }}
                  title={taskIdentifier || "No task assigned"}
                >
                  {taskIdentifier || "No task assigned"}
                </Typography>
              </Box>
            )}

            {/* Iterations & Created */}
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                gap: 1.5,
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <IterationsIcon fontSize="small" color="action" />
                <Typography variant="body2" color="text.primary" sx={{ fontWeight: 500 }}>
                  {formatIterations(run.number_of_iterations)} iteration
                  {run.number_of_iterations !== 1 ? "s" : ""}
                </Typography>
              </Box>
              <Box sx={{ textAlign: { xs: "left", sm: "right" } }}>
                <Typography variant="caption" color="text.secondary" display="block">
                  Created
                </Typography>
                <DateDisplay
                  dateString={run.created_at}
                  showTime={false}
                  variant="caption"
                />
              </Box>
            </Box>

            {/* Iteration Stats */}
            <Box
              sx={{
                mt: 2,
                mx: -2,
                px: 2,
                py: 1.75,
                bgcolor: "rgba(255,255,255,0.035)",
              }}
            >
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                <Typography variant="subtitle2" color="text.secondary" fontWeight={700}>
                  Iteration Insights
                </Typography>
                {inProgressIterations > 0 && (
                  <Chip
                    size="small"
                    color="warning"
                    icon={<ExecutingIcon sx={{ fontSize: 14 }} />}
                    label={`${inProgressIterations} in progress`}
                    sx={{
                      height: 24,
                      fontSize: "0.68rem",
                      animation: "pulse 2.5s ease-in-out infinite",
                      "@keyframes pulse": {
                        "0%,100%": { opacity: 1 },
                        "50%": { opacity: 0.35 },
                      },
                    }}
                  />
                )}
              </Box>

              {hasStats ? (
                <>
                  <Box sx={{ mb: 1.25 }}>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.6}>
                      <Typography variant="caption" color="text.secondary">
                        {completedIterations}/{totalIterationsPlanned} complete
                      </Typography>
                      <Typography variant="caption" fontWeight={600}>
                        {completionPercent}% success {successRate ? `• ${successRate}% ${getStatusDisplayLabel("passed", run.execution_type).toLowerCase()}` : ""}
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={Math.min(Math.max(completionPercent, 0), 100)}
                      sx={{
                        height: 6,
                        borderRadius: 2,
                        bgcolor: "rgba(255,255,255,0.08)",
                        "& .MuiLinearProgress-bar": {
                          borderRadius: 2,
                          backgroundImage: "linear-gradient(90deg, #4caf50, #66bb6a)",
                          boxShadow: "0 0 10px rgba(102,187,106,0.35)",
                        },
                      }}
                    />
                  </Box>

                  <Box display="flex" flexWrap="wrap" gap={0.9}>
                    {statusBreakdown.length > 0 ? (
                      statusBreakdown.map((item) => (
                        <Chip
                          key={item.key}
                          icon={item.icon}
                          label={`${item.label}: ${item.value}`}
                          size="small"
                          color={item.color}
                          variant={item.key === "passed" ? "filled" : "outlined"}
                          sx={{
                            height: 26,
                            fontSize: "0.72rem",
                            borderColor:
                              item.key === "passed" ? undefined : "rgba(255,255,255,0.18)",
                          }}
                        />
                      ))
                    ) : (
                      <Typography variant="caption" color="text.secondary">
                        Awaiting iteration results…
                      </Typography>
                    )}
                  </Box>
                </>
              ) : (
                <Box display="flex" alignItems="center" gap={1}>
                  <LinearProgress
                    variant="indeterminate"
                    sx={{ flexGrow: 1, height: 6, borderRadius: 2, bgcolor: "rgba(255,255,255,0.08)" }}
                  />
                  <Typography variant="caption" color="text.secondary">
                    Gathering iteration metrics…
                  </Typography>
                </Box>
              )}
            </Box>
          </Box>
        </CardContent>

        <CardActions
          sx={{
            justifyContent: "space-between",
            px: 2,
            pb: 2,
            pt: 0,
            borderTop: "1px solid",
            borderTopColor: "divider",
          }}
        >
          {/* Execution Time on Left */}
          {(run.status === "pending" || run.status === "executing" || (run.execution_duration_seconds !== undefined && run.execution_duration_seconds !== null)) && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                Execution Time:
              </Typography>
              {run.status === "pending" ? (
                <Skeleton variant="rectangular" width={60} height={22} sx={{ borderRadius: 1 }} />
              ) : (
                <Typography variant="caption" color="text.primary" sx={{ fontWeight: 600 }}>
                  {(() => {
                    const totalSeconds = Math.round(run.execution_duration_seconds || 0);
                    const hours = Math.floor(totalSeconds / 3600);
                    const minutes = Math.floor((totalSeconds % 3600) / 60);
                    const seconds = totalSeconds % 60;
                    
                    if (hours > 0) {
                      return `${hours}h ${minutes}m ${seconds}s`;
                    } else if (minutes > 0) {
                      return `${minutes}m ${seconds}s`;
                    } else {
                      return `${seconds}s`;
                    }
                  })()}
                </Typography>
              )}
            </Box>
          )}

          {/* Action Buttons on Right */}
          <Box sx={{ display: "flex", gap: 0.5 }}>
            <Tooltip title="View Details" arrow>
              <span onClick={(e) => e.stopPropagation()}>
                <IconButton
                  size="small"
                  color="primary"
                  onClick={(e) => {
                    e.stopPropagation();
                    setDetailsOpen(true);
                  }}
                  sx={runCardStyles.actionButton}
                >
                  <ViewDetailsIcon />
                </IconButton>
              </span>
            </Tooltip>

            {!hideEditButton && (
              <Tooltip title="Edit disabled" arrow>
                <span onClick={(e) => e.stopPropagation()}>
                  <IconButton
                    size="small"
                    color={runActionConfig.edit.color}
                    onClick={(e) => {
                      e.stopPropagation();
                      onEdit(run);
                    }}
                    disabled={true}
                    sx={runCardStyles.actionButton}
                  >
                    {runActionConfig.edit.icon}
                  </IconButton>
                </span>
              </Tooltip>
            )}

            <Tooltip
              title={
                !canModify
                  ? "Cannot delete while pending or executing"
                  : run.batch_id && !isAdmin
                  ? "Only administrators can delete batch runs"
                  : "Delete"
              }
              arrow
            >
              <span onClick={(e) => e.stopPropagation()}>
                <IconButton
                  size="small"
                  color={runActionConfig.delete.color}
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeleteConfirmOpen(true);
                  }}
                  disabled={!canDelete}
                  sx={runCardStyles.actionButton}
                >
                  {runActionConfig.delete.icon}
                </IconButton>
              </span>
            </Tooltip>
          </Box>
        </CardActions>
      </Card>

      {/* Details Modal */}
      <DetailModal
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        onEdit={() => {
          setDetailsOpen(false);
          onEdit(run);
        }}
        title="Run Details"
        editButtonText="Edit Run"
        canEdit={false}
      >
        <DetailContent>
          {/* Status and Model */}
          <DetailSection showDivider={false}>
            <Box sx={{ display: "flex", gap: 2, alignItems: "center" }}>
              <RunStatusChip status={run.status} showProgress={true} executionType={run.execution_type} />
              <ModelDisplay model={run.model} />
            </Box>
          </DetailSection>

          {/* Basic Information */}
          <DetailSection title="Basic Information">
            <DetailFields>
              <DetailField
                label="UUID"
                value={<UuidDisplay uuid={run.uuid} truncate={false} />}
                fullWidth
              />
              <DetailField
                label="Iterations"
                value={formatIterations(run.number_of_iterations)}
              />
              <DetailField
                label="Created"
                value={<DateDisplay dateString={run.created_at} />}
              />
              <DetailField
                label="Updated"
                value={<DateDisplay dateString={run.updated_at} />}
              />
              {batch && (
                <DetailField
                  label="Batch"
                  value={
                    <Link
                      component="button"
                      variant="body1"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/batches/${run.batch_id}/runs`);
                      }}
                      sx={{
                        textDecoration: "none",
                        fontWeight: 500,
                        color: "primary.main",
                        "&:hover": {
                          textDecoration: "underline",
                        },
                      }}
                    >
                      {batch?.name || "No batch assigned"}
                    </Link>
                  }
                />
              )}
            </DetailFields>
          </DetailSection>

          {/* Configuration */}
          <DetailSection title="Configuration">
            <DetailFields>
              {(run as any).execution_type === "playground" ? (
                <DetailField 
                  label="URL" 
                  value={
                    <Link href={(run as any).playground_url || ""} target="_blank" rel="noopener noreferrer">
                      {(run as any).playground_url || "No URL"}
                    </Link>
                  } 
                />
              ) : (
                <DetailField label="Gym" value={gymName || run.gym_id || "No gym"} />
              )}
              {(run as any).execution_type === "playground" ? (
                <DetailField
                  label="Prompt"
                  value={
                    <Box>
                      <Typography
                        variant="body2"
                        sx={{ whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}
                      >
                        {run.prompt || "No prompt"}
                      </Typography>
                    </Box>
                  }
                  fullWidth
                />
              ) : (
                <DetailField
                  label="Task"
                  value={
                    <Box>
                      <Typography
                        variant="body1"
                        sx={{ fontFamily: "monospace", fontWeight: 500, mb: 1 }}
                      >
                        {taskIdentifier || run.task_identifier || run.task_id || "No task assigned"}
                      </Typography>
                      {taskPrompt && (
                        <Typography variant="body2" color="text.secondary">
                          {taskPrompt}
                        </Typography>
                      )}
                    </Box>
                  }
                  fullWidth
                />
              )}
            </DetailFields>
          </DetailSection>

          {/* Iteration Insights */}
          <DetailSection title="Iteration Insights">
            {hasStats ? (
              <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                <Box display="flex" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2" color="text.secondary">
                    {completedIterations}/{totalIterationsPlanned} complete
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {successRate}% success
                    {successRate ? ` • ${stats?.passed ?? 0} ${getStatusDisplayLabel("passed", run.execution_type).toLowerCase()}` : ""}
                  </Typography>
                </Box>

                <LinearProgress
                  variant="determinate"
                  value={Math.min(Math.max(completionPercent, 0), 100)}
                  sx={{
                    height: 8,
                    borderRadius: 2,
                    bgcolor: "rgba(255,255,255,0.1)",
                    "& .MuiLinearProgress-bar": {
                      borderRadius: 2,
                      backgroundImage: "linear-gradient(90deg, #4caf50, #66bb6a)",
                    },
                  }}
                />

                <Box display="flex" flexWrap="wrap" gap={0.75}>
                  {statusBreakdown.length > 0 ? (
                    statusBreakdown.map((item) => (
                      <Chip
                        key={`detail-${item.key}`}
                        icon={item.icon}
                        label={`${item.label}: ${item.value}`}
                        size="small"
                        color={item.color}
                        variant={item.key === "passed" ? "filled" : "outlined"}
                        sx={{
                          height: 28,
                          fontSize: "0.78rem",
                          borderColor:
                            item.key === "passed" ? undefined : "rgba(255,255,255,0.18)",
                        }}
                      />
                    ))
                  ) : (
                    <Typography variant="caption" color="text.secondary">
                      Awaiting iteration breakdown…
                    </Typography>
                  )}
                </Box>
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Iteration insights appear once the run starts reporting results.
              </Typography>
            )}
          </DetailSection>
        </DetailContent>
      </DetailModal>

      {/* Delete Confirmation Modal */}
      <DeleteConfirmationModal
        open={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        onConfirm={handleDelete}
        item={run}
        isLoading={deleteRunMutation.isPending}
      />
    </>
  );
}
