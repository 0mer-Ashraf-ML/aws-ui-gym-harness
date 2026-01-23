import { useNavigate } from "react-router-dom";
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  Skeleton,
} from "@mui/material";
import {
  Schedule as ClockIcon,
  CheckCircle as CompletedIcon,
} from "@mui/icons-material";
import type { IterationProgressItem } from "../types";
import { getStatusColor } from "../utils/sharedStyles";
import { getStatusDisplayLabel } from "../utils/runUtils";

interface IterationCardProps {
  iteration: IterationProgressItem;
  executionId: string;
  taskId?: string;
  executionType?: "batch" | "playground";
  batchId?: string;
}

export default function IterationCard({
  iteration,
  executionId,
  taskId,
  executionType,
  batchId,
}: IterationCardProps) {
  const navigate = useNavigate();

  const statusColor = getStatusColor(iteration.status) as
    | "default"
    | "primary"
    | "secondary"
    | "error"
    | "info"
    | "success"
    | "warning";

  const handleCardClick = () => {
    // Use batch-aware URL if batch context is available
    if (batchId) {
      navigate(`/batches/${batchId}/executions/${executionId}/iterations/${iteration.uuid}`);
    } else {
      navigate(`/executions/${executionId}/iterations/${iteration.uuid}`);
    }
  };

  // Determine what to show based on status
  const status = iteration.status.toLowerCase();
  const isPending = status === "pending";
  const isExecuting = status === "executing";

  return (
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
      onClick={handleCardClick}
    >
      <CardContent sx={{ flexGrow: 1, pb: 0 }}>
        {/* Header with Iteration Number and Status */}
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            mb: 2,
          }}
        >
          <Typography variant="h6" component="h2" sx={{ fontWeight: 600 }}>
            Iteration {iteration.iteration_number}
          </Typography>
          <Chip
            label={getStatusDisplayLabel(iteration.status, executionType)}
            color={statusColor}
            size="small"
            sx={{ textTransform: "none" }}
          />
        </Box>

        {/* Content */}
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, mb: 2 }}>
          {/* Task Info - Hide for playground executions */}
          {taskId && executionType !== "playground" && (
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
                title={taskId}
              >
                {taskId}
              </Typography>
            </Box>
          )}

          {/* Timing Grid */}
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 1.5,
              mt: 0.5,
            }}
          >
            {/* Started */}
            <Box>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.5 }}>
                <ClockIcon sx={{ fontSize: 14, color: "text.secondary" }} />
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Started
                </Typography>
              </Box>
              {isPending ? (
                <Box>
                  <Skeleton variant="text" width="60%" height={20} />
                  <Skeleton variant="text" width="40%" height={16} />
                </Box>
              ) : iteration.started_at ? (
                <Box>
                  <Typography variant="body2" fontWeight={500}>
                    {new Date(iteration.started_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {new Date(iteration.started_at).toLocaleDateString([], {
                      month: "short",
                      day: "numeric",
                    })}
                  </Typography>
                </Box>
              ) : (
                <Typography variant="caption" color="text.secondary">
                  Pending
                </Typography>
              )}
            </Box>

            {/* Completed */}
            <Box>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.5 }}>
                <CompletedIcon sx={{ fontSize: 14, color: "text.secondary" }} />
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Completed
                </Typography>
              </Box>
              {isPending || isExecuting ? (
                <Box>
                  <Skeleton variant="text" width="60%" height={20} />
                  <Skeleton variant="text" width="40%" height={16} />
                </Box>
              ) : iteration.completed_at ? (
                <Box>
                  <Typography variant="body2" fontWeight={500}>
                    {new Date(iteration.completed_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {new Date(iteration.completed_at).toLocaleDateString([], {
                      month: "short",
                      day: "numeric",
                    })}
                  </Typography>
                </Box>
              ) : null}
            </Box>
          </Box>
        </Box>
      </CardContent>

      {/* Execution Time - Full Width Footer */}
      {(isPending || isExecuting || (iteration.execution_time_seconds !== undefined && iteration.execution_time_seconds !== null)) && (
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            px: 2,
            py: 1.5,
            bgcolor: "rgba(255,255,255,0.05)",
            borderTop: "1px solid",
            borderTopColor: "divider",
          }}
        >
          <Typography variant="caption" color="text.secondary" fontWeight={600}>
            Execution Time
          </Typography>
          {isPending || isExecuting ? (
            <Skeleton variant="rectangular" width={60} height={22} sx={{ borderRadius: 1 }} />
          ) : (
            <Chip
              label={`${iteration.execution_time_seconds}s`}
              size="small"
              variant="outlined"
              sx={{ fontSize: "0.7rem", height: 22, fontWeight: 600 }}
            />
          )}
        </Box>
      )}
    </Card>
  );
}
