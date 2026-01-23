/**
 * ActionMonitoringModal - Modal wrapper for the monitoring view
 */

import {
  Dialog,
  DialogTitle,
  DialogContent,
  IconButton,
  Box,
  Typography,
  CircularProgress,
  Alert,
  useTheme,
} from "@mui/material";
import { Close as CloseIcon, MonitorHeart as MonitorIcon } from "@mui/icons-material";
import ActionMonitoringView from "./ActionMonitoringView";
import { useTimelineMonitoring } from "../hooks/useTimelineMonitoring";

interface ActionMonitoringModalProps {
  open: boolean;
  onClose: () => void;
  executionId: string;
  iterationId: string;
  iterationNumber: number;
  isLiveIteration?: boolean;
}

export default function ActionMonitoringModal({
  open,
  onClose,
  executionId,
  iterationId,
  iterationNumber,
  isLiveIteration = false,
}: ActionMonitoringModalProps) {
  const theme = useTheme();

  const {
    entries: timelineEntries,
    isLoading,
    error,
    isLive,
    connectionState,
  } = useTimelineMonitoring(executionId, iterationId, {
    enabled: open,
    iterationStatus: isLiveIteration ? "executing" : "passed",
  });
  
  // No cleanup needed - MUI Dialog handles everything!

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={false}
      fullWidth
      keepMounted={false}
      disablePortal={false}
      PaperProps={{
        sx: {
          width: "95vw",
          height: "90vh",
          maxWidth: "none",
          m: 2,
        },
      }}
    >
      {/* Modal Header */}
      <DialogTitle
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: `1px solid ${theme.palette.divider}`,
          py: 1.5,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <MonitorIcon sx={{ color: theme.palette.primary.main }} />
          <Box>
            <Typography variant="h6">
              Live Monitoring - Iteration {iterationNumber}
            </Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mt: 0.5 }}>
              <Typography variant="caption" color="text.secondary">
                Execution: {executionId.slice(0, 8)}...
              </Typography>
              {isLive && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                  <Box
                    sx={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      bgcolor: theme.palette.success.main,
                      animation: "pulse 2s infinite",
                      "@keyframes pulse": {
                        "0%": { opacity: 1 },
                        "50%": { opacity: 0.4 },
                        "100%": { opacity: 1 },
                      },
                    }}
                  />
                  <Typography
                    variant="caption"
                    color="success.main"
                    fontWeight="medium"
                  >
                    STREAMING LIVE
                  </Typography>
                </Box>
              )}
              {(connectionState.status === "connecting" && isLiveIteration) && (
                <Typography variant="caption" color="warning.main">
                  Connecting...
                </Typography>
              )}
            </Box>
          </Box>
        </Box>
        <IconButton onClick={onClose} size="small">
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      {/* Modal Content */}
      <DialogContent
        sx={{
          p: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {isLoading ? (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              gap: 2,
            }}
          >
            <CircularProgress size={48} />
            <Typography variant="body1" color="text.secondary">
              Loading timeline data...
            </Typography>
            {isLiveIteration && (
              <Typography variant="caption" color="text.disabled">
                Connecting to live stream...
              </Typography>
            )}
          </Box>
        ) : error ? (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              gap: 2,
              p: 4,
            }}
          >
            <Alert severity="error" sx={{ maxWidth: 600 }}>
              <Typography variant="body1" fontWeight="medium" gutterBottom>
                Failed to load timeline
              </Typography>
              <Typography variant="body2">{error?.message || "Unknown error"}</Typography>
            </Alert>
            {connectionState.status === "error" && (
              <Typography variant="caption" color="text.secondary">
                Falling back to polling for updates...
              </Typography>
            )}
          </Box>
        ) : (
          <ActionMonitoringView
            executionId={executionId}
            iterationId={iterationId}
            timelineEntries={timelineEntries}
            isLive={isLive}
            autoPlayCompleted={!isLiveIteration && timelineEntries.length > 0}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

