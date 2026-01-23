import { useState } from 'react';
import { Menu, MenuItem, IconButton, ListItemIcon, ListItemText, Tooltip } from '@mui/material';
import { Sort as SortIcon, ArrowUpward, ArrowDownward } from '@mui/icons-material';

interface SortOption {
  value: string;
  label: string;
}

interface SortMenuProps {
  options: SortOption[];
  onSortChange: (key: string) => void;
  sortConfig: { key: string; direction: 'asc' | 'desc' };
}

export default function SortMenu({ options, onSortChange, sortConfig }: SortMenuProps) {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const handleClick = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleMenuItemClick = (key: string) => {
    onSortChange(key);
    handleClose();
  };

  return (
    <div>
      <Tooltip title="Sort">
        <IconButton onClick={handleClick}>
          <SortIcon />
        </IconButton>
      </Tooltip>
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleClose}
      >
        {options.map((option) => (
          <MenuItem
            key={option.value}
            selected={sortConfig.key === option.value}
            onClick={() => handleMenuItemClick(option.value)}
          >
            <ListItemText primary={option.label} />
            {sortConfig.key === option.value ? (
              <ListItemIcon sx={{ minWidth: 0, pl: 1 }}>
                {sortConfig.direction === 'asc' ? <ArrowUpward fontSize="small" /> : <ArrowDownward fontSize="small" />}
              </ListItemIcon>
            ) : null}
          </MenuItem>
        ))}
      </Menu>
    </div>
  );
}
