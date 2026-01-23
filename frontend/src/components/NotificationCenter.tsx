/**
 * NotificationCenter - Shows batches with ready reports
 */

import {
  Drawer,
  Box,
  Typography,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Divider,
  Badge,
  CircularProgress,
  Alert,
  Chip,
} from "@mui/material";
import {
  Close as CloseIcon,
  CheckCircle as CheckCircleIcon,
  InsertDriveFile as ReportIcon,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useReadyReports } from "../hooks/useReadyReports";
import { formatDistanceToNow } from "date-fns";
import { batchApi } from "../services/api";
import { useQueryClient } from "@tanstack/react-query";

interface NotificationCenterProps {
  open: boolean;
  onClose: () => void;
}

export default function NotificationCenter({
  open,
  onClose,
}: NotificationCenterProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useReadyReports(
    { enabled: open }, // Only fetch when drawer is open
    open ? 10000 : 0 // Poll every 10s when open, don't poll when closed
  );

  const handleBatchClick = async (batchId: string) => {
    try {
      // Mark notification as read
      await batchApi.markNotificationRead(batchId);
      // Refetch ready reports to update count
      queryClient.invalidateQueries({ queryKey: ["ready-reports"] });
    } catch (error) {
      console.error("Failed to mark notification as read:", error);
    }
    
    navigate(`/batches/${batchId}/runs`);
    onClose();
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      sx={{
        "& .MuiDrawer-paper": {
          width: { xs: "100%", sm: 400 },
          maxWidth: "100%",
        },
      }}
    >
      <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
        {/* Header */}
        <Box
          sx={{
            p: 2,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: 1,
            borderColor: "divider",
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <ReportIcon color="primary" />
            <Typography variant="h6">Reports Ready</Typography>
            {data && data.unread_count > 0 && (
              <Badge badgeContent={data.unread_count} color="success">
                <Box sx={{ width: 20 }} />
              </Badge>
            )}
          </Box>
          <IconButton onClick={onClose} size="small">
            <CloseIcon />
          </IconButton>
        </Box>

        {/* Content */}
        <Box sx={{ flex: 1, overflow: "auto" }}>
          {isLoading && (
            <Box
              sx={{
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                py: 4,
              }}
            >
              <CircularProgress size={40} />
            </Box>
          )}

          {error && (
            <Box sx={{ p: 2 }}>
              <Alert severity="error">
                Failed to load ready reports. Please try again.
              </Alert>
            </Box>
          )}

          {!isLoading && !error && data && data.count === 0 && (
            <Box
              sx={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                py: 8,
                px: 2,
                textAlign: "center",
              }}
            >
              <ReportIcon
                sx={{ fontSize: 80, color: "text.disabled", mb: 2 }}
              />
              <Typography variant="h6" color="text.secondary" gutterBottom>
                No Reports Ready
              </Typography>
              <Typography variant="body2" color="text.secondary">
                When your batch runs complete successfully, they'll appear here
                for download.
              </Typography>
            </Box>
          )}

          {!isLoading && !error && data && data.count > 0 && (
            <List sx={{ p: 0 }}>
              {data.ready_batches.map((batch, index) => (
                <Box key={batch.batch_id}>
                  {index > 0 && <Divider />}
                  <ListItem disablePadding>
                    <ListItemButton
                      onClick={() => handleBatchClick(batch.batch_id)}
                      sx={{
                        py: 2,
                        px: 2,
                        // Different background for unread notifications
                        backgroundColor: batch.is_read ? "transparent" : "action.selected",
                        "&:hover": {
                          backgroundColor: batch.is_read ? "action.hover" : "action.focus",
                        },
                        // Add a subtle border for unread items
                        borderLeft: batch.is_read ? "none" : "4px solid",
                        borderLeftColor: batch.is_read ? "transparent" : "primary.main",
                      }}
                    >
                      <Box
                        sx={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: 2,
                          width: "100%",
                        }}
                      >
                        <CheckCircleIcon
                          color="success"
                          sx={{ mt: 0.5, flexShrink: 0 }}
                        />
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <ListItemText
                            primary={
                              <Typography
                                variant="subtitle1"
                                sx={{
                                  fontWeight: 600,
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                {batch.batch_name}
                              </Typography>
                            }
                            secondary={
                              <Box
                                sx={{ display: "flex", flexDirection: "column", gap: 0.5, mt: 0.5 }}
                              >
                                <Typography variant="caption" color="text.secondary">
                                  {batch.number_of_iterations} iteration
                                  {batch.number_of_iterations !== 1 ? "s" : ""}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  Updated{" "}
                                  {formatDistanceToNow(new Date(batch.updated_at), {
                                    addSuffix: true,
                                  })}
                                </Typography>
                              </Box>
                            }
                          />
                          <Chip
                            label="Report Ready"
                            color="success"
                            size="small"
                            sx={{ mt: 1 }}
                          />
                        </Box>
                      </Box>
                    </ListItemButton>
                  </ListItem>
                </Box>
              ))}
            </List>
          )}
        </Box>

        {/* Footer */}
        {data && data.count > 0 && (
          <Box
            sx={{
              p: 2,
              borderTop: 1,
              borderColor: "divider",
              backgroundColor: "background.default",
            }}
          >
            <Typography variant="caption" color="text.secondary" align="center" display="block">
              Click on any batch to view details and download the report
            </Typography>
          </Box>
        )}
      </Box>
    </Drawer>
  );
}

