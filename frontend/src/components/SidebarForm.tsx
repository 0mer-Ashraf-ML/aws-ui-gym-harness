import {
  Drawer,
  Box,
  Typography,
  IconButton,
  Divider,
  useTheme,
  useMediaQuery,
} from "@mui/material";
import { Close as CloseIcon } from "@mui/icons-material";
import { type ReactNode } from "react";

interface SidebarFormProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  actions?: ReactNode;
  width?: number | string;
  disableBackdropClick?: boolean;
}

export default function SidebarForm({
  open,
  onClose,
  title,
  children,
  actions,
  width = 480,
  disableBackdropClick = false,
}: SidebarFormProps) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  // On mobile, use full width, otherwise use specified width
  const drawerWidth = isMobile ? "100%" : width;

  const handleBackdropClick = () => {
    if (!disableBackdropClick) {
      onClose();
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={handleBackdropClick}
      sx={{
        zIndex: 1300, // Above app bar
        "& .MuiDrawer-paper": {
          width: drawerWidth,
          maxWidth: "100vw",
          display: "flex",
          flexDirection: "column",
          background: theme.palette.background.default,
          zIndex: 1300, // Above app bar
        },
        "& .MuiBackdrop-root": {
          backgroundColor: "rgba(0, 0, 0, 0.6)",
          zIndex: 1299, // Just below drawer
        },
      }}
      ModalProps={{
        keepMounted: false, // Better performance on mobile
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          p: 3,
          pb: 2,
          borderBottom: `1px solid ${theme.palette.divider}`,
          backgroundColor: theme.palette.background.default,
          position: "sticky",
          top: 0,
          zIndex: 1,
        }}
      >
        <Typography
          variant="h6"
          component="h2"
          sx={{
            fontWeight: 600,
            color: theme.palette.text.primary,
          }}
        >
          {title}
        </Typography>
        <IconButton
          onClick={onClose}
          sx={{
            ml: 2,
            color: theme.palette.text.secondary,
            "&:hover": {
              backgroundColor: theme.palette.action.hover,
            },
          }}
        >
          <CloseIcon />
        </IconButton>
      </Box>

      {/* Content */}
      <Box
        sx={{
          flex: 1,
          overflow: "auto",
          p: 3,
          pt: 2,
        }}
      >
        {children}
      </Box>

      {/* Actions */}
      {actions && (
        <>
          <Divider />
          <Box
            sx={{
              p: 3,
              pt: 2,
              backgroundColor:
                theme.palette.mode === "light" ? "#f5f5f5" : "#202020",
              borderTop: `1px solid ${theme.palette.divider}`,
              position: "sticky",
              bottom: 0,
              zIndex: 1,
            }}
          >
            {actions}
          </Box>
        </>
      )}
    </Drawer>
  );
}
