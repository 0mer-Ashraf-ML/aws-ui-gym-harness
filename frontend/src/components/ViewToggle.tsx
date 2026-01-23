import React from "react";
import { ToggleButton, ToggleButtonGroup, Tooltip, Box } from "@mui/material";
import {
  ViewModule as CardViewIcon,
  TableView as TableViewIcon,
} from "@mui/icons-material";
import type { ViewMode } from "../hooks/useViewToggle";

interface ViewToggleProps {
  view: ViewMode;
  onChange: (view: ViewMode) => void;
  disabled?: boolean;
  size?: "small" | "medium" | "large";
  orientation?: "horizontal" | "vertical";
  showLabels?: boolean;
}

export default function ViewToggle({
  view,
  onChange,
  disabled = false,
  size = "small",
  orientation = "horizontal",
  showLabels = false,
}: ViewToggleProps) {
  const handleChange = (
    _event: React.MouseEvent<HTMLElement>,
    newView: ViewMode | null,
  ) => {
    if (newView !== null) {
      onChange(newView);
    }
  };

  const cardButton = (
    <ToggleButton
      value="card"
      aria-label="card view"
      sx={{
        "&.Mui-selected": {
          backgroundColor: "background.paper",
          color: "text.primary",
          "&:hover": {
            backgroundColor: "action.hover",
          },
        },
        minWidth: showLabels ? 80 : 40,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <CardViewIcon fontSize={size === "large" ? "medium" : "small"} />
        {showLabels && "Cards"}
      </Box>
    </ToggleButton>
  );

  const tableButton = (
    <ToggleButton
      value="table"
      aria-label="table view"
      sx={{
        "&.Mui-selected": {
          backgroundColor: "background.paper",
          color: "text.primary",
          "&:hover": {
            backgroundColor: "action.hover",
          },
        },
        minWidth: showLabels ? 80 : 40,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <TableViewIcon fontSize={size === "large" ? "medium" : "small"} />
        {showLabels && "Table"}
      </Box>
    </ToggleButton>
  );

  const toggleGroup = (
    <ToggleButtonGroup
      value={view}
      exclusive
      onChange={handleChange}
      size={size}
      orientation={orientation}
      disabled={disabled}
      sx={{
        "& .MuiToggleButton-root": {
          border: "none",
          "&:hover": {
            backgroundColor: "action.hover",
          },
        },
      }}
    >
      {cardButton}
      {tableButton}
    </ToggleButtonGroup>
  );

  if (showLabels) {
    return toggleGroup;
  }

  return (
    <Box sx={{ display: "flex", alignItems: "center" }}>
      <Tooltip title="Switch view mode" arrow>
        {toggleGroup}
      </Tooltip>
    </Box>
  );
}
