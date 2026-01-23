import React from "react";
import { Box, Chip, Typography } from "@mui/material";
import { getStatusColor } from "../utils/sharedStyles";
import { getStatusDisplayLabel } from "../utils/runUtils";
import type { ExecutionStatusSummary, TaskStatusSummary } from "../types";

interface StatusCountsProps {
  statusSummary: ExecutionStatusSummary | TaskStatusSummary;
  size?: "small" | "medium";
  showLabel?: boolean;
  variant?: "outlined" | "filled";
  executionType?: "batch" | "playground";
}

export const StatusCounts: React.FC<StatusCountsProps> = ({
  statusSummary,
  size = "small",
  showLabel = false,
  variant = "outlined",
  executionType,
}) => {

  // Only show non-zero counts
  const statusCounts = [
    { status: "passed", count: statusSummary.passed_count, label: getStatusDisplayLabel("passed", executionType) },
    { status: "failed", count: statusSummary.failed_count, label: "Failed" },
    { status: "crashed", count: statusSummary.crashed_count, label: "Crashed" },
    { status: "timeout", count: statusSummary.timeout_count || 0, label: "Timeout" },
    { status: "executing", count: statusSummary.executing_count, label: "Running" },
    { status: "pending", count: statusSummary.pending_count, label: "Pending" },
  ].filter(({ count }) => count > 0);

  if (statusCounts.length === 0) {
    return null;
  }

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexWrap: "wrap" }}>
      {showLabel && (
        <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
          Status:
        </Typography>
      )}
      {statusCounts.map(({ status, count, label }) => (
        <Chip
          key={status}
          label={`${label}: ${count}`}
          size={size}
          variant={variant}
          color={getStatusColor(status as any) as any}
          sx={{
            fontWeight: 500,
            "& .MuiChip-label": {
              fontSize: size === "small" ? "0.75rem" : "0.875rem",
            },
          }}
        />
      ))}
    </Box>
  );
};

export default StatusCounts;
