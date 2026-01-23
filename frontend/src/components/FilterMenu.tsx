import { useState, type MouseEvent } from "react";
import {
  Menu,
  MenuItem,
  IconButton,
  Badge,
  Box,
  Typography,
  Checkbox,
  ListItemText,
  Divider,
  Button,
} from "@mui/material";
import {
  FilterList as FilterListIcon,
  Clear as ClearIcon,
} from "@mui/icons-material";
import type { ActiveFilters } from "../hooks/useFiltering";

export interface FilterCategory {
  key: string;
  label: string;
  options: readonly (string | number)[];
}

interface FilterMenuProps {
  options: FilterCategory[];
  activeFilters: ActiveFilters;
  onFilterToggle: (filterKey: string, value: string | number) => void;
  onClearFilters: () => void;
}

export default function FilterMenu({
  options,
  activeFilters,
  onFilterToggle,
  onClearFilters,
}: FilterMenuProps) {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [subMenuAnchorEl, setSubMenuAnchorEl] = useState<null | HTMLElement>(
    null,
  );
  const [selectedCategory, setSelectedCategory] =
    useState<null | FilterCategory>(null);

  const activeFilterCount = Array.from(activeFilters.values()).reduce(
    (acc, set) => acc + set.size,
    0,
  );

  const handleMainMenuClick = (event: MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMainMenuClose = () => {
    setAnchorEl(null);
    handleSubMenuClose();
  };

  const handleSubMenuClick = (
    event: MouseEvent<HTMLElement>,
    category: FilterCategory,
  ) => {
    setSubMenuAnchorEl(event.currentTarget);
    setSelectedCategory(category);
  };

  const handleSubMenuClose = () => {
    setSubMenuAnchorEl(null);
    setSelectedCategory(null);
  };

  const handleClear = () => {
    onClearFilters();
    handleMainMenuClose();
  };

  const hasOptions = options.length > 0;
  const canOpenMenu = hasOptions || activeFilterCount > 0;

  return (
    <div>
      <IconButton onClick={handleMainMenuClick} disabled={!canOpenMenu}>
        <Badge badgeContent={activeFilterCount} color="primary">
          <FilterListIcon />
        </Badge>
      </IconButton>

      {/* Main Menu */}
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl) && canOpenMenu}
        onClose={handleMainMenuClose}
        PaperProps={{
          sx: {
            minWidth: 220,
          },
        }}
      >
        <Box
          sx={{
            px: 2,
            py: 1,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 2,
          }}
        >
          <Typography variant="subtitle1">Filter By</Typography>
          <Button
            size="small"
            onClick={handleClear}
            disabled={activeFilterCount === 0}
            startIcon={<ClearIcon />}
            sx={{
              color: "white",
              minWidth: "auto",
              padding: "1px 4px",
              fontSize: "0.65rem",
              lineHeight: 1.2,
              "& .MuiButton-startIcon": {
                marginRight: "2px",
                "& > svg": {
                  fontSize: "0.75rem",
                },
              },
            }}
          >
            Clear
          </Button>
        </Box>
        <Divider sx={{ my: 0.5 }} />
        {hasOptions ? (
          options.map((category) => (
            <MenuItem
              key={category.key}
              onClick={(e) => handleSubMenuClick(e, category)}
            >
              <ListItemText primary={category.label} />
              <Typography variant="body2" color="text.secondary">
                {activeFilters.get(category.key)?.size || 0} selected
              </Typography>
            </MenuItem>
          ))
        ) : (
          <Box sx={{ px: 2, py: 1.5 }}>
            <Typography variant="body2" color="text.secondary">
              No filters available for the current results.
            </Typography>
            {activeFilterCount > 0 && (
              <Typography variant="caption" color="text.secondary">
                Clear filters to see all runs.
              </Typography>
            )}
          </Box>
        )}
      </Menu>

      {/* Sub Menu */}
      <Menu
        anchorEl={subMenuAnchorEl}
        open={Boolean(subMenuAnchorEl) && Boolean(selectedCategory)}
        onClose={handleSubMenuClose}
        anchorOrigin={{ vertical: "top", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
      >
        {selectedCategory?.options.map((option) => {
          const isChecked =
            activeFilters.get(selectedCategory.key)?.has(option) || false;
          return (
            <MenuItem
              key={option}
              onClick={() => onFilterToggle(selectedCategory.key, option)}
            >
              <Checkbox checked={isChecked} />
              <ListItemText primary={String(option)} />
            </MenuItem>
          );
        })}
      </Menu>
    </div>
  );
}
