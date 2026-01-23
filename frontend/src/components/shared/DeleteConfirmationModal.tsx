import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  Box,
  Button,
  IconButton,
  useTheme,
} from "@mui/material";
import { Delete as DeleteIcon, Close as CloseIcon } from "@mui/icons-material";
import { RunStatusChip } from "../../utils/runUtils";
import { modalConfig } from "../../utils/modalConfig";
import type { Execution } from "../../types";

interface DeleteConfirmationModalProps<T = Execution> {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  item: T | null;
  isLoading?: boolean;
  title?: string;
  message?: string;
}

export default function DeleteConfirmationModal<
  T extends { uuid: string; status?: string },
>({
  open,
  onClose,
  onConfirm,
  item,
  isLoading = false,
  title = "Delete Run",
  message = "Are you sure you want to delete this run?",
}: DeleteConfirmationModalProps<T>) {
  const theme = useTheme();
  if (!item) return null;

  return (
    <Dialog open={open} onClose={onClose} {...modalConfig.deleteConfirmation}>
      <DialogTitle
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <DeleteIcon color="error" />
          {title}
        </Box>
        <IconButton
          onClick={onClose}
          size="small"
          sx={{ color: "text.secondary" }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <Typography variant="body1" gutterBottom>
          {message}
        </Typography>
        <Box
          sx={{
            mt: 2,
            p: 2,
            bgcolor: theme.palette.mode === "light" ? "#f5f5f5" : "#4A4D50",
            borderRadius: 1,
          }}
        >
          <Typography variant="body2" color="text.secondary">
            <strong>ID:</strong> {item.uuid}
          </Typography>
          {item.status && (
            <Typography variant="body2" color="text.secondary">
              <strong>Status:</strong> <RunStatusChip status={item.status} />
            </Typography>
          )}
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          This action cannot be undone.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={isLoading} sx={{ color: "white" }}>
          Cancel
        </Button>
        <Button
          onClick={onConfirm}
          variant="contained"
          color="error"
          disabled={isLoading}
          startIcon={<DeleteIcon />}
        >
          {isLoading ? "Deleting..." : "Delete"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
