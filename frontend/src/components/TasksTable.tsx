import { useState } from "react";
import { Box, Typography, Chip } from "@mui/material";
import { Assignment as TaskIcon, Download as DownloadIcon } from "@mui/icons-material";
import DataTable, {
  type TableColumn,
  type TableAction,
  UuidRenderer,
  DateRenderer,
} from "./DataTable";
import { runActionConfig, sharedTheme } from "../utils/sharedStyles";
import {
  analyzePrompt,
  getCharacterCountTextShort,
  truncatePrompt,
} from "../utils/promptUtils";
import { downloadJSON } from "../utils/downloadUtils";
import { taskApi } from "../services/api";
import type { Task } from "../types";

interface TasksTableProps {
  tasks: Task[];
  gyms?: Array<{ uuid: string; name: string }>;
  onEdit: (task: Task) => void;
  onView?: (task: Task) => void;
  onDelete?: (task: Task) => void;
  isLoading?: boolean;
  sortBy?: keyof Task | string;
  sortDirection?: "asc" | "desc";
  onSort?: (column: keyof Task | string) => void;
}

export default function TasksTable({
  tasks,
  gyms = [],
  onEdit,
  onView,
  onDelete,
  isLoading = false,
  sortBy,
  sortDirection = "desc",
  onSort,
}: TasksTableProps) {
  const [isDownloading, setIsDownloading] = useState(false);

  // Helper function to get gym name by ID
  const getGymName = (gymId: string) => {
    const gym = gyms.find((g) => g.uuid === gymId);
    return gym?.name || "Unknown Gym";
  };

  // Handle download action
  const handleDownload = async (task: Task) => {
    setIsDownloading(true);
    try {
      const exportData = await taskApi.export(task.uuid);
      downloadJSON(exportData, `${task.task_id}.json`);
    } catch (error) {
      console.error("Error downloading task:", error);
      alert("Failed to download task. Please try again.");
    } finally {
      setIsDownloading(false);
    }
  };

  // Helper function to render task ID with icon
  const renderTaskId = (taskId: string) => {
    if (!taskId) return "Auto-generated";

    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <TaskIcon sx={{ fontSize: 16, color: "text.secondary" }} />
        <Typography
          variant="body2"
          sx={{
            fontFamily: "monospace",
            fontWeight: 500,
          }}
        >
          {taskId}
        </Typography>
      </Box>
    );
  };

  // Helper function to render truncated prompt with full text in tooltip
  // Helper function to render truncated prompt text
  const renderPrompt = (prompt: string) => {
    const displayText = truncatePrompt(prompt, 100);
    const isLong = prompt.length > 100;

    return (
      <Typography
        variant="body2"
        sx={{
          maxWidth: 300,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          cursor: isLong ? "help" : "default",
        }}
        title={prompt}
      >
        {displayText}
      </Typography>
    );
  };

  // Define table columns
  const columns: TableColumn<Task>[] = [
    {
      id: "uuid",
      label: "Task UUID",
      minWidth: 120,
      sortable: true,
      render: (value) => UuidRenderer(String(value || "")),
    },
    {
      id: "task_id",
      label: "Task ID",
      minWidth: 150,
      sortable: true,
      render: (value) => renderTaskId(String(value || "")),
    },
    {
      id: "gym_id",
      label: "Gym",
      minWidth: 150,
      sortable: false,
      render: (value) => (
        <Chip
          label={getGymName(String(value || ""))}
          size="small"
          variant="outlined"
          sx={{
            ...sharedTheme.actionButton,
            maxWidth: 140,
            fontSize: "0.75rem",
            fontWeight: 500,
          }}
        />
      ),
    },
    {
      id: "prompt",
      label: "Prompt",
      minWidth: 300,
      sortable: false,
      render: (value) => {
        const promptStr = String(value || "");
        const analysis = analyzePrompt(promptStr);
        return (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
            {renderPrompt(promptStr)}
            <Box sx={{ display: "flex", gap: 0.5, alignItems: "center" }}>
              <Chip
                label={getCharacterCountTextShort(analysis.characterCount)}
                size="small"
                variant="outlined"
                sx={{
                  ...sharedTheme.actionButton,
                  fontSize: "0.65rem",
                  height: 20,
                  minHeight: 20,
                }}
              />
              <Chip
                label={analysis.label}
                size="small"
                color={analysis.color}
                sx={{
                  ...sharedTheme.actionButton,
                  fontSize: "0.65rem",
                  height: 20,
                  minHeight: 20,
                }}
              />
            </Box>
          </Box>
        );
      },
    },
    {
      id: "created_at",
      label: "Created",
      minWidth: 140,
      sortable: true,
      render: (value) => DateRenderer(String(value || "")),
    },
    {
      id: "updated_at",
      label: "Updated",
      minWidth: 140,
      sortable: true,
      render: (value) => DateRenderer(String(value || "")),
    },
  ];

  // Define table actions using shared configuration.
  // Delete action will be conditionally rendered by parent based on admin role.
  const actions: TableAction<Task>[] = [
    ...(onView
      ? [
          {
            ...runActionConfig.view,
            onClick: onView,
            show: () => true,
          },
        ]
      : []),
    {
      ...runActionConfig.edit,
      onClick: onEdit,
      show: () => true,
    },
    {
      icon: <DownloadIcon fontSize="small" />,
      label: "Download JSON",
      color: "inherit" as const,
      onClick: handleDownload,
      show: () => true,
      disabled: () => isDownloading,
    },
    ...(onDelete
      ? [
          {
            ...runActionConfig.delete,
            onClick: onDelete,
            show: () => true,
          },
        ]
      : []),
  ];

  return (
    <DataTable
      data={tasks as unknown as Record<string, unknown>[]}
      columns={columns as unknown as TableColumn<Record<string, unknown>>[]}
      actions={actions as unknown as TableAction<Record<string, unknown>>[]}
      isLoading={isLoading}
      sortBy={sortBy}
      sortDirection={sortDirection}
      onSort={onSort}
      emptyMessage="No tasks found. Create your first task to get started."
      stickyHeader={true}
      maxHeight="70vh"
    />
  );
}

// Export additional types for parent components
export type TasksTableSortBy = keyof Task;
