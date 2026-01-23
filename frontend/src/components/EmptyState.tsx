import type { ReactNode } from "react";
import { Paper, Typography, Button, Stack, Box, useTheme } from "@mui/material";
import { Clear as ClearIcon } from "@mui/icons-material";

interface EmptyStateAction {
  label: string;
  icon?: ReactNode;
  onClick: () => void;
  variant?: "contained" | "outlined" | "text";
}

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description: string;
  isSearchState?: boolean;
  searchTerm?: string;
  onClearSearch?: () => void;
  primaryAction?: EmptyStateAction;
  secondaryAction?: EmptyStateAction;
}

export default function EmptyState({
  icon,
  title,
  description,
  isSearchState = false,
  searchTerm,
  onClearSearch,
  primaryAction,
  secondaryAction,
}: EmptyStateProps) {
  const theme = useTheme();

  return (
    <Paper
      elevation={1}
      sx={{
        textAlign: "center",
        py: 8,
        px: 4,
        borderRadius: 3,
        backgroundColor: theme.palette.mode === "light" ? "#f5f5f5" : "#202020",
        border: `1px solid ${theme.palette.mode === "light" ? theme.palette.divider : "#2E2E2E"}`,
      }}
    >
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
        }}
      >
        {/* Icon */}
        <Box
          sx={{
            mb: 2,
            "& > svg": {
              fontSize: 80,
              color: "text.secondary",
              opacity: 0.5,
            },
          }}
        >
          {icon}
        </Box>

        {/* Title */}
        <Typography variant="h5" gutterBottom color="text.secondary">
          {title}
        </Typography>

        {/* Description */}
        <Typography
          variant="body1"
          color="text.secondary"
          sx={{
            mb: 4,
            maxWidth: 400,
            mx: "auto",
          }}
        >
          {isSearchState && searchTerm
            ? `${description} "${searchTerm}"`
            : description}
        </Typography>

        {/* Actions */}
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          justifyContent="center"
        >
          {/* Clear Search Button (for search states) */}
          {isSearchState && onClearSearch && (
            <Button
              variant="outlined"
              startIcon={<ClearIcon />}
              onClick={onClearSearch}
            >
              Clear Search
            </Button>
          )}

          {/* Secondary Action */}
          {secondaryAction && (
            <Button
              variant={secondaryAction.variant || "outlined"}
              startIcon={secondaryAction.icon}
              onClick={secondaryAction.onClick}
            >
              {secondaryAction.label}
            </Button>
          )}

          {/* Primary Action */}
          {primaryAction && (
            <Button
              variant={primaryAction.variant || "contained"}
              size={isSearchState ? "medium" : "large"}
              startIcon={primaryAction.icon}
              onClick={primaryAction.onClick}
              sx={
                !isSearchState
                  ? {
                      px: 4,
                      py: 1.5,
                      borderRadius: 2,
                      textTransform: "none",
                      fontSize: "1.1rem",
                    }
                  : undefined
              }
            >
              {primaryAction.label}
            </Button>
          )}
        </Stack>
      </Box>
    </Paper>
  );
}
