import {
  PlayArrow as ExecuteIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Visibility as ViewIcon,
} from "@mui/icons-material";

// Shared color theme
export const sharedTheme = {
  actionButton: {
    color: "#898989",
    borderColor: "#898989",
    backgroundColor: "transparent",
    "&:hover": {
      color: "white",
      borderColor: "white",
      backgroundColor: "transparent",
    },
    "&.Mui-disabled": {
      opacity: 0.5,
    },
  },
};

// Shared styles for components
export const runCardStyles = {
  actionButton: {
    ...sharedTheme.actionButton,
    transition: "all 0.2s ease-in-out",
    "&:hover": {
      ...sharedTheme.actionButton["&:hover"],
      backgroundColor: "rgba(255, 255, 255, 0.1)",
    },
  },
};

// Action configurations
export const runActionConfig = {
  execute: {
    icon: <ExecuteIcon fontSize="small" />,
    label: "Execute",
    color: "primary" as const,
    isDisabled: (status: string) => status === "executing",
    getTooltip: (status: string) => {
      switch (status) {
        case "executing":
          return "Cannot execute while running";
        case "failed":
        case "crashed":
        case "timeout":
          return "Retry execution";
        case "passed":
          return "Re-run execution";
        default:
          return "Execute run";
      }
    },
  },
  edit: {
    icon: <EditIcon fontSize="small" />,
    label: "Edit",
    color: "secondary" as const,
  },
  delete: {
    icon: <DeleteIcon fontSize="small" />,
    label: "Delete",
    color: "error" as const,
  },
  view: {
    icon: <ViewIcon fontSize="small" />,
    label: "View",
    color: "info" as const,
  },
};

// Status color mapping - using gray theme colors
export const getStatusColor = (status: string) => {
  switch (status?.toLowerCase()) {
    case "passed":
    case "completed":
      return "default"; // Gray color instead of green
    case "executing":
    case "running":
      return "warning"; // Orange color for executing status
    case "failed":
    case "crashed":
    case "error":
      return "error";
    case "timeout":
      return "secondary"; // Purple color for timeout status
    case "pending":
      return "info";
    default:
      return "default";
  }
};

// Utility functions
export const formatIterations = (iterations: number): string => {
  if (iterations >= 1000000) {
    return `${(iterations / 1000000).toFixed(1)}M`;
  }
  if (iterations >= 1000) {
    return `${(iterations / 1000).toFixed(1)}K`;
  }
  return iterations.toString();
};

export const getGymDisplayName = (
  gymId: string,
  gyms: Array<{ uuid: string; name: string }> = [],
): string => {
  if (!gymId) return "No gym assigned";

  const gym = gyms.find((g) => g.uuid === gymId);
  if (gym) {
    return gym.name;
  }

  return `ID: ${gymId.slice(0, 8)}...`;
};

export const getTaskDisplayText = (
  taskUuid: string | null,
  tasks: Array<{ uuid: string; task_id?: string; prompt?: string }> = [],
  maxLength: number = 50,
): string => {
  if (!taskUuid) return "No task assigned";

  const task = tasks.find((t) => t.uuid === taskUuid);
  if (task) {
    if (task.task_id) {
      return task.task_id;
    }

    const prompt = task.prompt || "";
    if (prompt && maxLength > 0 && prompt.length > maxLength) {
      return `${prompt.slice(0, maxLength)}...`;
    }
    return prompt || "Unknown task";
  }

  return "Unknown task";
};
