import type { ReactNode } from "react";
import {
  Box,
  Typography,
  TextField,
  Button,
  InputAdornment,
} from "@mui/material";
import { Search as SearchIcon } from "@mui/icons-material";
import ViewToggle from "./ViewToggle";
import type { ViewMode } from "../hooks/useViewToggle";

interface PageHeaderProps {
  icon: ReactNode;
  title: string;
  description: string | ReactNode;
  searchPlaceholder: string;
  searchValue: string;
  onSearchChange: (value: string) => void;
  primaryButton: {
    label: string;
    icon: ReactNode;
    onClick: () => void;
    disabled?: boolean;
    variant?: "contained" | "outlined";
  };
  secondaryButton?: {
    label: string;
    icon: ReactNode;
    onClick: () => void;
    disabled?: boolean;
    variant?: "contained" | "outlined";
  };
  viewToggle?: {
    view: ViewMode;
    onChange: (view: ViewMode) => void;
    disabled?: boolean;
  };
  sortMenu?: ReactNode;
  filterMenu?: ReactNode;
  customLeftControls?: ReactNode; // replaces search when provided
}

export default function PageHeader({
  icon,
  title,
  description,
  searchPlaceholder,
  searchValue,
  onSearchChange,
  primaryButton,
  secondaryButton,
  viewToggle,
  sortMenu,
  filterMenu,
  customLeftControls,
}: PageHeaderProps) {
  return (
    <Box sx={{ mb: 4 }}>
      {/* Title Section */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 6 }}>
        {icon}
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            {title}
          </Typography>
          {typeof description === "string" ? (
            <Typography variant="body1" color="text.secondary">
              {description}
            </Typography>
          ) : (
            description
          )}
        </Box>
      </Box>

      {/* Controls Section */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 2,
        }}
      >
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          {/* Search or custom controls */}
          {customLeftControls ? (
            <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              {customLeftControls}
            </Box>
          ) : (
            <TextField
              placeholder={searchPlaceholder}
              value={searchValue}
              onChange={(e) => onSearchChange(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                ),
              }}
              sx={{ minWidth: { xs: "100%", md: 400 }, maxWidth: 500 }}
              size="small"
            />
          )}
          {filterMenu}
        </Box>

        {/* Action Buttons */}
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          {sortMenu}
          {viewToggle && (
            <ViewToggle
              view={viewToggle.view}
              onChange={viewToggle.onChange}
              disabled={viewToggle.disabled}
              size="small"
            />
          )}
          {secondaryButton && (
            <Button
              variant={secondaryButton.variant || "outlined"}
              startIcon={secondaryButton.icon}
              onClick={secondaryButton.onClick}
              disabled={secondaryButton.disabled}
            >
              {secondaryButton.label}
            </Button>
          )}
          <Button
            variant={primaryButton.variant || "contained"}
            startIcon={primaryButton.icon}
            onClick={primaryButton.onClick}
            disabled={primaryButton.disabled}
          >
            {primaryButton.label}
          </Button>
        </Box>
      </Box>
    </Box>
  );
}
