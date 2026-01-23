import React, { useState } from "react";
import {
  Chip,
  Typography,
  Box,
  IconButton,
  Tooltip,
  CircularProgress,
  LinearProgress,
  Button,
} from "@mui/material";
import {
  ContentCopy as CopyIcon,
  Psychology as ModelIcon,
} from "@mui/icons-material";
import { runCardStyles, getStatusColor } from "./sharedStyles";

/**
 * Get the display label for a status, converting "passed" to "completed" for playground executions
 */
export const getStatusDisplayLabel = (
  status: string,
  executionType?: "batch" | "playground"
): string => {
  if (status === "passed" && executionType === "playground") {
    return "Completed";
  }
  // Capitalize first letter
  return status.charAt(0).toUpperCase() + status.slice(1);
};

// RunStatusChip component
interface RunStatusChipProps {
  status: string;
  showProgress?: boolean;
  size?: "small" | "medium";
}

export const RunStatusChip: React.FC<RunStatusChipProps & { executionType?: "batch" | "playground" }> = ({
  status,
  showProgress = false,
  size = "small",
  executionType,
}) => {
  const isExecuting = status?.toLowerCase() === "executing";
  // Override color to be orange (warning) for executing status
  const color = isExecuting ? "warning" : getStatusColor(status);
  const displayLabel = getStatusDisplayLabel(status, executionType);

  return (
    <Chip
      label={displayLabel}
      color={
        color as
          | "default"
          | "primary"
          | "secondary"
          | "error"
          | "info"
          | "success"
          | "warning"
      }
      size={size}
      icon={
        showProgress && isExecuting ? (
          <CircularProgress size={14} thickness={4} sx={{ color: "white" }} />
        ) : undefined
      }
      sx={{
        minWidth: 80,
        fontWeight: 500,
        textTransform: "none", // Don't capitalize since we handle it in getStatusDisplayLabel
        ...(isExecuting && {
          color: "white",
          "& .MuiChip-label": {
            color: "white",
          },
        }),
        ...(showProgress &&
          isExecuting && {
            "& .MuiChip-icon": {
              marginLeft: "4px",
              marginRight: "-2px",
            },
          }),
      }}
    />
  );
};

// UuidDisplay component
interface UuidDisplayProps {
  uuid: string;
  copyable?: boolean;
  truncate?: boolean;
}

export const UuidDisplay: React.FC<UuidDisplayProps> = ({
  uuid,
  copyable = false,
  truncate = true,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(uuid);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy UUID:", error);
    }
  };

  const displayUuid = truncate ? `${uuid.slice(0, 8)}...` : uuid;

  if (copyable) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <Typography
          variant="body2"
          sx={{
            fontFamily: "monospace",
            fontSize: "0.75rem",
          }}
          title={uuid}
        >
          {displayUuid}
        </Typography>
        <Tooltip title={copied ? "Copied!" : "Copy UUID"} arrow>
          <IconButton
            size="small"
            onClick={handleCopy}
            sx={{
              ...runCardStyles.actionButton,
              minWidth: "auto",
              width: 20,
              height: 20,
            }}
          >
            <CopyIcon sx={{ fontSize: 12 }} />
          </IconButton>
        </Tooltip>
      </Box>
    );
  }

  return (
    <Typography
      variant="body2"
      sx={{
        fontFamily: "monospace",
        fontSize: "0.75rem",
      }}
      title={uuid}
    >
      {displayUuid}
    </Typography>
  );
};

// DateDisplay component
interface DateDisplayProps {
  dateString: string;
  showTime?: boolean;
  variant?: "body2" | "caption";
}

export const DateDisplay: React.FC<DateDisplayProps> = ({
  dateString,
  showTime = true,
  variant = "body2",
}) => {
  if (!dateString) {
    return (
      <Typography variant={variant} color="text.secondary">
        —
      </Typography>
    );
  }

  try {
    const date = new Date(dateString);
    const dateStr = date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
    const timeStr = date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    });

    if (showTime) {
      return (
        <Box>
          <Typography variant={variant}>{dateStr}</Typography>
          <Typography variant="caption" color="text.secondary">
            {timeStr}
          </Typography>
        </Box>
      );
    }

    return <Typography variant={variant}>{dateStr}</Typography>;
  } catch {
    return (
      <Typography variant={variant} color="text.secondary">
        Invalid date
      </Typography>
    );
  }
};

// ModelDisplay component
interface ModelDisplayProps {
  model: string;
  size?: "small" | "medium";
}

export const ModelDisplay: React.FC<ModelDisplayProps> = ({
  model,
  size = "medium",
}) => {
  const getModelColor = (modelName: string) => {
    const name = modelName.toLowerCase();
    if (name.includes("gpt")) return "primary";
    if (name.includes("claude")) return "secondary";
    if (name.includes("gemini")) return "success";
    if (name.includes("llama")) return "warning";
    return "default";
  };

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
      <ModelIcon
        fontSize={size}
        color={
          getModelColor(model) as
            | "primary"
            | "secondary"
            | "success"
            | "warning"
            | "inherit"
        }
      />
      <Typography
        variant={size === "small" ? "body2" : "body1"}
        sx={{
          fontWeight: 500,
          color: `${getModelColor(model)}.main`,
        }}
      >
        {model}
      </Typography>
    </Box>
  );
};

// Shared action button component
interface ActionButtonProps {
  icon: React.ReactNode;
  onClick: (e: React.MouseEvent) => void;
  disabled?: boolean;
  tooltip: string;
  color?:
    | "primary"
    | "secondary"
    | "error"
    | "warning"
    | "info"
    | "success"
    | "inherit";
  variant?: "contained" | "outlined" | "text";
  size?: "small" | "medium" | "large";
  children?: React.ReactNode;
}

export const ActionButton: React.FC<ActionButtonProps> = ({
  icon,
  onClick,
  disabled = false,
  tooltip,
  color = "inherit",
  variant = "text",
  size = "small",
  children,
}) => {
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onClick(e);
  };

  if (children) {
    return (
      <Tooltip title={tooltip} arrow>
        <span>
          <Button
            size={size}
            variant={variant}
            color={color}
            startIcon={icon}
            onClick={handleClick}
            disabled={disabled}
            sx={runCardStyles.actionButton}
          >
            {children}
          </Button>
        </span>
      </Tooltip>
    );
  }

  return (
    <Tooltip title={tooltip} arrow>
      <span>
        <IconButton
          size={size}
          color={color}
          onClick={handleClick}
          disabled={disabled}
          sx={runCardStyles.actionButton}
        >
          {icon}
        </IconButton>
      </span>
    </Tooltip>
  );
};

// Progress indicator component
interface ProgressIndicatorProps {
  show: boolean;
  variant?: "circular" | "linear";
  size?: number;
}

export const ProgressIndicator: React.FC<ProgressIndicatorProps> = ({
  show,
  variant = "circular",
  size = 16,
}) => {
  if (!show) return null;

  if (variant === "linear") {
    return <LinearProgress sx={{ width: "100%" }} />;
  }

  return <CircularProgress size={size} thickness={4} />;
};
