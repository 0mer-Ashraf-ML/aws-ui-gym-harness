import { Box, Typography, Chip } from "@mui/material";
import { Key as KeyIcon } from "@mui/icons-material";
import DataTable, {
  type TableColumn,
  type TableAction,
  DateRenderer,
} from "./DataTable";
import { runActionConfig } from "../utils/sharedStyles";
import type { Model } from "../types";

interface ModelsTableProps {
  models: Model[];
  onEdit: (model: Model) => void;
  onView?: (model: Model) => void;
  onDelete?: (model: Model) => void;
  isLoading?: boolean;
  sortBy?: keyof Model | string;
  sortDirection?: "asc" | "desc";
  onSort?: (column: keyof Model | string) => void;
}

export default function ModelsTable({
  models,
  onEdit,
  onView,
  onDelete,
  isLoading = false,
  sortBy,
  sortDirection = "desc",
  onSort,
}: ModelsTableProps) {
  // Helper function to render model type with appropriate styling
  const renderModelType = (type: string) => {
    const getTypeColor = (type: string) => {
      switch (type?.toLowerCase()) {
        case "openai":
          return "success";
        case "anthropic":
          return "info";
        case "gemini":
          return "warning";
        default:
          return "default";
      }
    };

    return (
      <Chip
        label={type}
        color={getTypeColor(type) as "success" | "info" | "warning" | "default"}
        size="small"
        sx={{
          textTransform: "capitalize",
          fontWeight: 500,
        }}
      />
    );
  };

  // Helper function to render masked API key
  const renderApiKey = (apiKey: string | unknown) => {
    const keyStr = String(apiKey || "");
    if (!keyStr) {
      return (
        <Typography variant="body2" color="error">
          Not configured
        </Typography>
      );
    }

    const maskedKey = `${keyStr.slice(0, 8)}${"*".repeat(Math.max(0, keyStr.length - 12))}${keyStr.slice(-4)}`;

    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <KeyIcon sx={{ fontSize: 14, color: "success.main" }} />
        <Typography
          variant="body2"
          sx={{
            fontFamily: "monospace",
            fontSize: "0.75rem",
            color: "text.secondary",
          }}
        >
          {maskedKey}
        </Typography>
      </Box>
    );
  };

  // Helper function to render model ID
  const renderModelId = (id: string | unknown) => (
    <Typography
      variant="body2"
      sx={{
        fontFamily: "monospace",
        fontWeight: 500,
        color: "primary.main",
      }}
    >
      {String(id || "")}
    </Typography>
  );

  // Define table columns
  const columns: TableColumn<Model>[] = [
    {
      id: "id",
      label: "Model ID",
      minWidth: 120,
      sortable: true,
      render: (value) => renderModelId(value),
    },
    {
      id: "name",
      label: "Name",
      minWidth: 150,
      sortable: true,
      render: (value) => (
        <Typography
          variant="body2"
          sx={{
            fontWeight: 600,
            color: "text.primary",
          }}
        >
          {String(value || "")}
        </Typography>
      ),
    },
    {
      id: "type",
      label: "Type",
      minWidth: 120,
      align: "center",
      sortable: true,
      render: (value) => renderModelType(String(value || "")),
    },
    {
      id: "description",
      label: "Description",
      minWidth: 250,
      sortable: false,
      render: (value) => {
        const desc = String(value || "");
        return (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{
              maxWidth: 250,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={desc}
          >
            {desc || "No description"}
          </Typography>
        );
      },
    },
    {
      id: "api_key",
      label: "API Key",
      minWidth: 180,
      sortable: false,
      render: (value) => renderApiKey(value),
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

  // Define table actions using shared configuration
  const actions: TableAction<Model>[] = [
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
      data={models as unknown as Record<string, unknown>[]}
      columns={columns as unknown as TableColumn<Record<string, unknown>>[]}
      actions={actions as unknown as TableAction<Record<string, unknown>>[]}
      isLoading={isLoading}
      sortBy={sortBy}
      sortDirection={sortDirection}
      onSort={onSort}
      emptyMessage="No models found. Create your first model to get started."
      stickyHeader={true}
      maxHeight="70vh"
    />
  );
}

// Export additional types for parent components
export type ModelsTableSortBy = keyof Model;
