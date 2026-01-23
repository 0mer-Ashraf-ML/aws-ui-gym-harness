import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  Box,
  Button,
  IconButton,
} from "@mui/material";
import {
  Close as CloseIcon,
  Edit as EditIcon,
} from "@mui/icons-material";
import { modalConfig } from "../../utils/modalConfig";

interface DetailModalProps {
  open: boolean;
  onClose: () => void;
  onEdit?: () => void;
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  editButtonText?: string;
  canEdit?: boolean;
  isEditing?: boolean;
}

export default function DetailModal({
  open,
  onClose,
  onEdit,
  title,
  icon,
  children,
  editButtonText = "Edit",
  canEdit = true,
  isEditing = false,
}: DetailModalProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      {...modalConfig.details}
    >
      <DialogTitle
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {icon}
          <Typography variant="h6">{title}</Typography>
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
        {children}
      </DialogContent>

      <DialogActions>
        <Button
          onClick={onClose}
          sx={{ color: "white" }}
        >
          Close
        </Button>
        {onEdit && canEdit && (
          <Button
            onClick={onEdit}
            variant="contained"
            startIcon={<EditIcon />}
            disabled={isEditing}
          >
            {isEditing ? "Editing..." : editButtonText}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
