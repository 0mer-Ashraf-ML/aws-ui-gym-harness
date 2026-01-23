import React from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TableSortLabel,
  IconButton,
  Tooltip,
  Chip,
  Box,
  Typography,
  Skeleton,
  LinearProgress,
} from "@mui/material";
import {
  runCardStyles,
  sharedTheme,
  getStatusColor,
} from "../utils/sharedStyles";

export interface TableColumn<T> {
  id: keyof T | string;
  label: string;
  minWidth?: number;
  align?: "left" | "right" | "center";
  sortable?: boolean;
  render?: (value: unknown, row: T) => React.ReactNode;
}

export interface TableAction<T> {
  icon: React.ReactNode;
  label: string;
  onClick: (row: T) => void;
  disabled?: (row: T) => boolean;
  color?:
    | "primary"
    | "secondary"
    | "error"
    | "warning"
    | "info"
    | "success"
    | "inherit";
  show?: (row: T) => boolean;
}

interface DataTableProps<T extends Record<string, unknown>> {
  data: T[];
  columns: TableColumn<T>[];
  actions?: TableAction<T>[];
  isLoading?: boolean;
  sortBy?: keyof T | string;
  sortDirection?: "asc" | "desc";
  onSort?: (column: keyof T | string) => void;
  emptyMessage?: string;
  stickyHeader?: boolean;
  maxHeight?: string | number;
  onRowClick?: (row: T) => void;
}

export default function DataTable<T extends Record<string, unknown>>({
  data,
  columns,
  actions = [],
  isLoading = false,
  sortBy,
  sortDirection = "asc",
  onSort,
  emptyMessage = "No data available",
  stickyHeader = true,
  maxHeight = "70vh",
  onRowClick,
}: DataTableProps<T>) {
  const handleSort = (column: keyof T | string) => {
    if (onSort && columns.find((col) => col.id === column)?.sortable) {
      onSort(column);
    }
  };

  const renderCell = (column: TableColumn<T>, row: T): React.ReactNode => {
    const value = column.id === "actions" ? null : row[column.id as keyof T];

    if (column.render) {
      return column.render(value, row);
    }

    // Default rendering based on value type
    if (value === null || value === undefined) {
      return (
        <Typography variant="body2" color="text.secondary">
          —
        </Typography>
      );
    }

    if (typeof value === "boolean") {
      return (
        <Chip
          label={value ? "Yes" : "No"}
          color={value ? "success" : "default"}
          size="small"
          sx={{
            ...sharedTheme.actionButton,
            minWidth: 60,
            fontWeight: 500,
          }}
        />
      );
    }

    if (typeof value === "string" && value.includes("T")) {
      // Likely a date string
      try {
        const date = new Date(value);
        return (
          <Typography variant="body2">
            {date.toLocaleDateString()} {date.toLocaleTimeString()}
          </Typography>
        );
      } catch {
        return <Typography variant="body2">{String(value)}</Typography>;
      }
    }

    return <Typography variant="body2">{String(value)}</Typography>;
  };

  const renderActions = (row: T) => {
    if (!actions.length) return null;

    return (
      <Box sx={{ display: "flex", gap: 0.5, justifyContent: "center" }}>
        {actions
          .filter((action) => !action.show || action.show(row))
          .map((action, index) => (
            <Tooltip key={index} title={action.label} arrow>
              <span>
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    action.onClick(row);
                  }}
                  disabled={action.disabled ? action.disabled(row) : false}
                  color={action.color || "default"}
                  sx={{
                    ...runCardStyles.actionButton,
                    "&.Mui-disabled": {
                      opacity: 0.5,
                    },
                    "&:hover": {
                      backgroundColor: "action.hover",
                    },
                  }}
                >
                  {action.icon}
                </IconButton>
              </span>
            </Tooltip>
          ))}
      </Box>
    );
  };

  const LoadingRow = () => (
    <TableRow>
      {columns.map((_, index) => (
        <TableCell key={index}>
          <Skeleton variant="text" width="100%" />
        </TableCell>
      ))}
      {actions.length > 0 && (
        <TableCell>
          <Box sx={{ display: "flex", gap: 0.5 }}>
            {actions.map((_, index) => (
              <Skeleton key={index} variant="circular" width={32} height={32} />
            ))}
          </Box>
        </TableCell>
      )}
    </TableRow>
  );

  const EmptyRow = () => (
    <TableRow>
      <TableCell
        colSpan={columns.length + (actions.length > 0 ? 1 : 0)}
        sx={{ textAlign: "center", py: 4 }}
      >
        <Typography variant="body1" color="text.secondary">
          {emptyMessage}
        </Typography>
      </TableCell>
    </TableRow>
  );

  return (
    <Paper sx={{ width: "100%", overflow: "hidden" }}>
      {isLoading && <LinearProgress />}
      <TableContainer sx={{ maxHeight }}>
        <Table stickyHeader={stickyHeader} size="small">
          <TableHead>
            <TableRow>
              {columns.map((column) => (
                <TableCell
                  key={String(column.id)}
                  align={column.align || "left"}
                  style={{ minWidth: column.minWidth }}
                  sx={{
                    fontWeight: 600,
                    backgroundColor: (theme) =>
                      theme.palette.mode === "light" ? "#f5f5f5" : "#161616",
                    color: (theme) =>
                      theme.palette.mode === "light"
                        ? "text.primary"
                        : "common.white",
                    border: "1px solid",
                    borderColor: "divider",
                    "&:not(:first-child)": {
                      borderLeft: "none",
                    },
                  }}
                >
                  {column.sortable && onSort ? (
                    <TableSortLabel
                      active={sortBy === column.id}
                      direction={sortBy === column.id ? sortDirection : "asc"}
                      onClick={() => handleSort(column.id)}
                      sx={{
                        "&.MuiTableSortLabel-root": {
                          color: "common.white",
                        },
                        "&.MuiTableSortLabel-root:hover": {
                          color: "primary.main",
                        },
                        "&.Mui-active": {
                          color: "primary.main",
                        },
                      }}
                    >
                      {column.label}
                    </TableSortLabel>
                  ) : (
                    column.label
                  )}
                </TableCell>
              ))}
              {actions.length > 0 && (
                <TableCell
                  align="center"
                  sx={{
                    fontWeight: 600,
                    backgroundColor: (theme) =>
                      theme.palette.mode === "light" ? "#f5f5f5" : "#161616",
                    color: (theme) =>
                      theme.palette.mode === "light"
                        ? "text.primary"
                        : "common.white",
                    border: "1px solid",
                    borderColor: "divider",
                    borderLeft: "none",
                    minWidth: Math.max(actions.length * 40, 120),
                  }}
                >
                  Actions
                </TableCell>
              )}
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, index) => (
                <LoadingRow key={index} />
              ))
            ) : data.length === 0 ? (
              <EmptyRow />
            ) : (
              data.map((row, index) => (
                <TableRow
                  hover
                  key={String(
                    (row as Record<string, unknown>).uuid ||
                      (row as Record<string, unknown>).id ||
                      index
                  )}
                  sx={{
                    "&:last-child td, &:last-child th": { border: 0 },
                    cursor: "pointer",
                    "&:hover": {
                      backgroundColor: "action.hover",
                    },
                  }}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {columns.map((column) => (
                    <TableCell
                      key={String(column.id)}
                      align={column.align || "left"}
                    >
                      {renderCell(column, row)}
                    </TableCell>
                  ))}
                  {actions.length > 0 && (
                    <TableCell align="center">{renderActions(row)}</TableCell>
                  )}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}

// Pre-built status chip renderer for common use cases
export const StatusChipRenderer = (status: string) => {
  return (
    <Chip
      label={status}
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
      sx={{
        ...sharedTheme.actionButton,
        minWidth: 80,
        fontWeight: 500,
        textTransform: "capitalize",
      }}
    />
  );
};

// Pre-built UUID renderer for truncated display
export const UuidRenderer = (uuid: string) => (
  <Tooltip title={uuid} arrow>
    <Typography
      variant="body2"
      sx={{
        fontFamily: "monospace",
        cursor: "help",
        fontSize: "0.75rem",
        color: "text.secondary",
      }}
    >
      {uuid?.slice(0, 8)}...
    </Typography>
  </Tooltip>
);

// Pre-built date renderer
export const DateRenderer = (dateString: string) => {
  if (!dateString) return "—";

  try {
    const date = new Date(dateString);
    return (
      <Box>
        <Typography variant="body2">{date.toLocaleDateString()}</Typography>
        <Typography variant="caption" color="text.secondary">
          {date.toLocaleTimeString()}
        </Typography>
      </Box>
    );
  } catch {
    return dateString;
  }
};
