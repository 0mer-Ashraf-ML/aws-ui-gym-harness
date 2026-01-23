import { Typography } from "@mui/material";
import DataTable, { type TableColumn, type TableAction } from "./DataTable";
import type { Execution } from "../types";
import {
  RunStatusChip,
  UuidDisplay,
  DateDisplay,
  ModelDisplay,
} from "../utils/runUtils";
import {
  runActionConfig,
  getGymDisplayName,
  getTaskDisplayText,
  formatIterations,
} from "../utils/sharedStyles";

interface RunsTableProps {
  runs: Execution[];
  gyms?: Array<{ uuid: string; name: string }>;
  tasks?: Array<{ uuid: string; task_id: string; prompt: string }>;
  onEdit?: (run: Execution) => void;
  onView?: (run: Execution) => void;
  onDelete?: (run: Execution) => void;
  onRowClick?: (run: Execution) => void;
  isLoading?: boolean;
  sortBy?: keyof Execution | string;
  sortDirection?: "asc" | "desc";
  onSort?: (column: keyof Execution | string) => void;
}

export default function RunsTable({
  runs,
  gyms = [],
  tasks = [],
  onEdit,
  onView,
  onDelete,
  onRowClick,
  isLoading = false,
  sortBy,
  sortDirection = "desc",
  onSort,
}: RunsTableProps) {
  // Define table columns
  const columns: TableColumn<Execution>[] = [
    {
      id: "uuid",
      label: "Run ID",
      minWidth: 120,
      sortable: true,
      render: (value) => (
        <UuidDisplay uuid={String(value || "")} copyable={true} />
      ),
    },
    {
      id: "status",
      label: "Status",
      minWidth: 100,
      sortable: true,
      render: (value) => (
        <RunStatusChip
          status={String(value || "") as Execution["status"]}
          showProgress={true}
          size="small"
        />
      ),
    },
    {
      id: "model",
      label: "Model",
      minWidth: 100,
      sortable: true,
      render: (value) => (
        <ModelDisplay model={String(value || "")} size="small" />
      ),
    },
    {
      id: "gym_id",
      label: "Gym / URL",
      minWidth: 150,
      sortable: false,
      render: (value, row) => {
        // For playground executions, show URL instead of gym
        if ((row as any).execution_type === "playground") {
          const url = (row as any).playground_url || "";
          return (
            <Typography
              variant="body2"
              noWrap
              sx={{ fontWeight: 500 }}
              title={url}
            >
              {url || "No URL"}
            </Typography>
          );
        }
        return (
          <Typography
            variant="body2"
            noWrap
            sx={{ fontWeight: 500 }}
            title={getGymDisplayName(String(value || ""), gyms)}
          >
            {getGymDisplayName(String(value || ""), gyms)}
          </Typography>
        );
      },
    },
    {
      id: "task_id",
      label: "Task / Prompt",
      minWidth: 200,
      sortable: false,
      render: (value, row) => {
        // For playground executions, show prompt instead of task
        if ((row as any).execution_type === "playground") {
          const prompt = row.prompt || "";
          return (
            <Typography
              variant="body2"
              noWrap
              sx={{
                maxWidth: 200,
                overflow: "hidden",
                textOverflow: "ellipsis",
                fontWeight: 500,
              }}
              title={prompt}
            >
              {prompt || "No prompt"}
            </Typography>
          );
        }
        const displayText = getTaskDisplayText(
          String(value || "") || null,
          tasks,
          40,
        );
        return (
          <Typography
            variant="body2"
            noWrap
            sx={{
              maxWidth: 200,
              overflow: "hidden",
              textOverflow: "ellipsis",
              fontWeight: 500,
            }}
            title={displayText}
          >
            {displayText}
          </Typography>
        );
      },
    },
    {
      id: "number_of_iterations",
      label: "Iterations",
      minWidth: 80,
      align: "center",
      sortable: true,
      render: (value) => (
        <Typography variant="body2" align="center" sx={{ fontWeight: 500 }}>
          {formatIterations(Number(value || 0))}
        </Typography>
      ),
    },

    {
      id: "created_at",
      label: "Created",
      minWidth: 140,
      sortable: true,
      render: (value) => (
        <DateDisplay dateString={String(value || "")} showTime={true} />
      ),
    },
    {
      id: "updated_at",
      label: "Updated",
      minWidth: 140,
      sortable: true,
      render: (value) => (
        <DateDisplay dateString={String(value || "")} showTime={true} />
      ),
    },
  ];

  // Define table actions using shared configuration
  const actions: TableAction<Execution>[] = [
    {
      ...runActionConfig.execute,
      onClick: () => {},
      disabled: () => true,
      show: () => false,
    },
    ...(onView
      ? [
          {
            ...runActionConfig.view,
            onClick: onView,
            show: () => true,
          },
        ]
      : []),
    ...(onEdit
      ? [
          {
            ...runActionConfig.edit,
            onClick: onEdit,
            disabled: () => true,
            show: () => true,
          },
        ]
      : []),
    ...(onDelete
      ? [
          {
            ...runActionConfig.delete,
            onClick: onDelete,
            disabled: (row: Execution) =>
              row.status === "pending" || row.status === "executing",
            show: () => true,
          },
        ]
      : []),
  ];

  return (
    <DataTable
      data={runs as unknown as Record<string, unknown>[]}
      columns={columns as unknown as TableColumn<Record<string, unknown>>[]}
      actions={actions as unknown as TableAction<Record<string, unknown>>[]}
      isLoading={isLoading}
      sortBy={sortBy}
      sortDirection={sortDirection}
      onSort={onSort}
      onRowClick={onRowClick as ((row: Record<string, unknown>) => void) | undefined}
      emptyMessage="No runs found. Create your first run to get started."
      stickyHeader={true}
      maxHeight="70vh"
    />
  );
}

// Export additional types for parent components
export type RunsTableSortBy = keyof Execution | "gym_name" | "task_prompt";
