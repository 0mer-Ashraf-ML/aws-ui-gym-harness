import React from "react";
import { Snackbar, Alert, Slide } from "@mui/material";
import type { AlertColor, SlideProps } from "@mui/material";
import type { SnackbarState } from "../hooks/useSnackbar";

interface NotificationSnackbarProps {
  snackbar: SnackbarState;
  onClose: () => void;
  autoHideDuration?: number;
  anchorOrigin?: {
    vertical: "top" | "bottom";
    horizontal: "left" | "center" | "right";
  };
}

// Transition component for slide animation
function SlideTransition(props: SlideProps) {
  return <Slide {...props} direction="up" />;
}

/**
 * Reusable notification snackbar component for displaying CRUD operation status
 * and other system notifications with consistent styling and behavior
 */
const NotificationSnackbar: React.FC<NotificationSnackbarProps> = ({
  snackbar,
  onClose,
  autoHideDuration = 6000,
  anchorOrigin = { vertical: "bottom", horizontal: "right" },
}) => {
  const handleClose = (
    _event?: React.SyntheticEvent | Event,
    reason?: string,
  ) => {
    // Don't close on clickaway to prevent accidental dismissals
    if (reason === "clickaway") {
      return;
    }
    onClose();
  };

  return (
    <Snackbar
      open={snackbar.open}
      autoHideDuration={autoHideDuration}
      onClose={handleClose}
      anchorOrigin={anchorOrigin}
      TransitionComponent={SlideTransition}
      sx={{
        // Ensure snackbar appears above modals and other high z-index elements
        "& .MuiSnackbar-root": {
          zIndex: 9999,
        },
      }}
    >
      <Alert
        onClose={handleClose}
        severity={snackbar.severity as AlertColor}
        variant="filled"
        elevation={6}
        sx={{
          minWidth: 300,
          fontSize: "0.875rem",
          fontWeight: 500,
          boxShadow: (theme) => theme.shadows[8],
          // Custom styling for different severity levels
          "&.MuiAlert-filledSuccess": {
            backgroundColor: "#2e7d32",
            "& .MuiAlert-icon": {
              color: "#ffffff",
            },
          },
          "&.MuiAlert-filledError": {
            backgroundColor: "#d32f2f",
            "& .MuiAlert-icon": {
              color: "#ffffff",
            },
          },
          "&.MuiAlert-filledWarning": {
            backgroundColor: "#ed6c02",
            "& .MuiAlert-icon": {
              color: "#ffffff",
            },
          },
          "&.MuiAlert-filledInfo": {
            backgroundColor: "#0288d1",
            "& .MuiAlert-icon": {
              color: "#ffffff",
            },
          },
          // Hover effect for close button
          "& .MuiAlert-action .MuiButtonBase-root:hover": {
            backgroundColor: "rgba(255, 255, 255, 0.1)",
          },
        }}
      >
        {snackbar.message}
      </Alert>
    </Snackbar>
  );
};

export default NotificationSnackbar;
