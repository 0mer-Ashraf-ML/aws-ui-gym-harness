import { Box, Typography, Link, Chip } from "@mui/material";
import {
  Launch as LaunchIcon,
  Verified as VerifiedIcon,
} from "@mui/icons-material";
import DataTable, {
  type TableColumn,
  type TableAction,
  UuidRenderer,
  DateRenderer,
} from "./DataTable";
import { runActionConfig } from "../utils/sharedStyles";
import type { Gym } from "../types";

interface GymsTableProps {
  gyms: Gym[];
  onEdit: (gym: Gym) => void;
  onView?: (gym: Gym) => void;
  onDelete?: (gym: Gym) => void;
  isLoading?: boolean;
  sortBy?: keyof Gym | string;
  sortDirection?: "asc" | "desc";
  onSort?: (column: keyof Gym | string) => void;
}

export default function GymsTable({
  gyms,
  onEdit,
  onView,
  onDelete,
  isLoading = false,
  sortBy,
  sortDirection = "desc",
  onSort,
}: GymsTableProps) {
  // Helper function to render URLs with external link
  const renderUrl = (url: string | unknown, label?: string) => {
    const urlStr = String(url || "");
    if (!urlStr) return "—";

    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <Link
          href={urlStr}
          target="_blank"
          rel="noopener noreferrer"
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 0.5,
            textDecoration: "none",
            color: "text.primary",
            "&:hover": {
              textDecoration: "underline",
              color: "text.secondary",
            },
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <Typography
            variant="body2"
            sx={{
              maxWidth: 200,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={urlStr}
          >
            {label || urlStr}
          </Typography>
          <LaunchIcon sx={{ fontSize: 12, opacity: 0.7 }} />
        </Link>
      </Box>
    );
  };

  // Helper function to render verification status
  const renderVerificationStatus = (verificationStrategy: string) => {
    const strategyLabel = verificationStrategy.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

    return (
      <Chip
        icon={<VerifiedIcon sx={{ fontSize: 14 }} />}
        label={strategyLabel}
        size="small"
        sx={{
          backgroundColor: "#016239",
          color: "white",
          fontWeight: 500,
          fontSize: "0.75rem",
          border: "none",
          "& .MuiChip-icon": {
            color: "inherit",
          },
        }}
      />
    );
  };

  // Define table columns
  const columns: TableColumn<Gym>[] = [
    {
      id: "uuid",
      label: "Gym ID",
      minWidth: 120,
      sortable: true,
      render: (value) => UuidRenderer(String(value || "")),
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
      id: "description",
      label: "Description",
      minWidth: 250,
      sortable: false,
      render: (value) => (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{
            maxWidth: 200,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={String(value || "")}
        >
          {String(value || "") || "No description"}
        </Typography>
      ),
    },
    {
      id: "base_url",
      label: "Base URL",
      minWidth: 200,
      sortable: false,
      render: (value) => renderUrl(String(value || ""), "Visit"),
    },
    {
      id: "verification_strategy",
      label: "Verification",
      minWidth: 120,
      align: "center",
      sortable: false,
      render: (value) => (
        <Box
          sx={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
          }}
        >
          {renderVerificationStatus(String(value || ""))}
        </Box>
      ),
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
  const actions: TableAction<Gym>[] = [
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
      data={gyms as unknown as Record<string, unknown>[]}
      columns={columns as unknown as TableColumn<Record<string, unknown>>[]}
      actions={actions as unknown as TableAction<Record<string, unknown>>[]}
      isLoading={isLoading}
      sortBy={sortBy}
      sortDirection={sortDirection}
      onSort={onSort}
      emptyMessage="No gyms found. Create your first gym to get started."
      stickyHeader={true}
      maxHeight="70vh"
    />
  );
}

// Export additional types for parent components
export type GymsTableSortBy = keyof Gym;
