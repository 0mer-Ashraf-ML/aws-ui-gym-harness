import { Box, Chip, Tooltip, Typography } from "@mui/material";
import {
  Wifi as WifiIcon,
  WifiOff as WifiOffIcon,
  Sync as SyncIcon,
  ErrorOutline as ErrorIcon,
} from "@mui/icons-material";
import type {
  useRealTimeStatus,
  useStatusIndicator,
} from "../hooks/realtime/useRealTimeStatus";
import { getStatusDisplayLabel } from "../utils/runUtils";

interface RealTimeStatusIndicatorProps {
  realTimeStatus: ReturnType<typeof useRealTimeStatus>;
  statusIndicator: ReturnType<typeof useStatusIndicator>;
  variant?: "icon" | "chip" | "detailed";
  showLastUpdate?: boolean;
  showLabel?: boolean;
  size?: "small" | "medium" | "large";
}

export default function RealTimeStatusIndicator({
  realTimeStatus,
  statusIndicator,
  variant = "icon",
  showLastUpdate = false,
  showLabel = false,
  size = "small",
}: RealTimeStatusIndicatorProps) {
  const getIconSize = () => {
    switch (size) {
      case "small":
        return 14;
      case "medium":
        return 18;
      case "large":
        return 22;
      default:
        return 14;
    }
  };

  const getStatusIcon = () => {
    const iconSize = getIconSize();

    switch (realTimeStatus.connectionState.status) {
      case "connected":
        return (
          <WifiIcon sx={{ fontSize: iconSize, color: "text.secondary" }} />
        );
      case "connecting":
      case "reconnecting":
        return (
          <SyncIcon
            sx={{
              fontSize: iconSize,
              color: "warning.main",
              animation: "spin 2s linear infinite",
            }}
          />
        );
      case "error":
        return <ErrorIcon sx={{ fontSize: iconSize, color: "error.main" }} />;
      default:
        return <WifiOffIcon sx={{ fontSize: iconSize, color: "error.main" }} />;
    }
  };

  const getTooltipContent = () => {
    let content = `Real-time: ${statusIndicator.label}`;

    if (statusIndicator.lastUpdate) {
      content += ` • Last update: ${statusIndicator.lastUpdate.toLocaleTimeString()}`;
    }

    if (statusIndicator.error) {
      content += ` • Error: ${statusIndicator.error}`;
    }

    return content;
  };

  if (variant === "icon") {
    return (
      <Tooltip title={getTooltipContent()}>
        <Box sx={{ display: "flex", alignItems: "center" }}>
          {getStatusIcon()}
        </Box>
      </Tooltip>
    );
  }

  if (variant === "chip") {
    return (
      <Tooltip title={getTooltipContent()}>
        <Chip
          icon={getStatusIcon()}
          label={showLabel ? statusIndicator.label : undefined}
          size={size === "large" ? "medium" : "small"}
          color={
            statusIndicator.color as
              | "default"
              | "primary"
              | "secondary"
              | "success"
              | "error"
              | "info"
              | "warning"
          }
          variant="outlined"
          sx={{
            fontSize: size === "small" ? "0.75rem" : "0.875rem",
            ...(showLabel ? {} : { "& .MuiChip-label": { display: "none" } }),
          }}
        />
      </Tooltip>
    );
  }

  if (variant === "detailed") {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {getStatusIcon()}
          <Typography
            variant={size === "small" ? "caption" : "body2"}
            color="text.secondary"
          >
            {statusIndicator.label}
          </Typography>
        </Box>

        {showLastUpdate && statusIndicator.lastUpdate && (
          <Typography variant="caption" color="text.secondary" sx={{ ml: 2.5 }}>
            Last update: {statusIndicator.lastUpdate.toLocaleTimeString()}
          </Typography>
        )}

        {statusIndicator.error && (
          <Typography variant="caption" color="error" sx={{ ml: 2.5 }}>
            Error: {statusIndicator.error}
          </Typography>
        )}
      </Box>
    );
  }

  return null;
}

// Helper component for execution status with real-time indicator
export function ExecutionStatusWithRealTime({
  status,
  realTimeStatus,
  statusIndicator,
  showAnimation = true,
  executionType,
}: {
  status: "pending" | "executing" | "passed" | "failed" | "crashed" | "timeout";
  realTimeStatus: ReturnType<typeof useRealTimeStatus>;
  statusIndicator: ReturnType<typeof useStatusIndicator>;
  showAnimation?: boolean;
  executionType?: "batch" | "playground";
}) {
  const getStatusColor = (status: string) => {
    switch (status) {
      case "passed":
        return "success";
      case "executing":
        return "warning";
      case "failed":
      case "crashed":
        return "error";
      case "timeout":
        return "secondary";
      default:
        return "default";
    }
  };

  const getStatusLabel = (status: string) => {
    // Use the shared utility function
    return getStatusDisplayLabel(status, executionType);
  };

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      <Chip
        label={getStatusLabel(status)}
        color={
          getStatusColor(status) as
            | "default"
            | "primary"
            | "secondary"
            | "success"
            | "error"
            | "info"
            | "warning"
        }
        size="small"
      />

      {status === "executing" && showAnimation && (
        <RealTimeStatusIndicator
          realTimeStatus={realTimeStatus}
          statusIndicator={statusIndicator}
          variant="icon"
          size="small"
        />
      )}

      {status !== "executing" && (
        <RealTimeStatusIndicator
          realTimeStatus={realTimeStatus}
          statusIndicator={statusIndicator}
          variant="icon"
          size="small"
        />
      )}
    </Box>
  );
}
