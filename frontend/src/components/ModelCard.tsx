import { Card, CardContent, Typography, Box, Chip } from "@mui/material";
import {
  Edit as EditIcon,
  Delete as DeleteIcon,
  SmartToy as ModelIcon,
} from "@mui/icons-material";
import type { Model } from "../types";
import { sharedTheme } from "../utils/sharedStyles";
import { ActionButton } from "../utils/runUtils";

interface ModelCardProps {
  model: Model;
  onEdit: (model: Model) => void;
  onDelete: (model: Model) => void;
  onView?: (model: Model) => void;
}

export default function ModelCard({
  model,
  onEdit,
  onDelete,
  onView,
}: ModelCardProps) {
  const maskApiKey = (apiKey: string) => {
    if (apiKey.length <= 8) return apiKey;
    return (
      apiKey.substring(0, 4) + "***...***" + apiKey.substring(apiKey.length - 4)
    );
  };

  return (
    <Card
      onClick={() => onView?.(model)}
      sx={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        cursor: onView ? "pointer" : "default",
        transition: "transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out",
        "&:hover": {
          transform: "translateY(-2px)",
          boxShadow: 4,
        },
      }}
    >
      <CardContent
        sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}
      >
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            mb: 2,
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <ModelIcon color="primary" />
            <Typography variant="h6" component="h3">
              {model.name}
            </Typography>
          </Box>
          <Box>
            <ActionButton
              icon={<EditIcon />}
              onClick={(e) => {
                e.stopPropagation();
                onEdit(model);
              }}
              tooltip="Edit model"
              color="inherit"
            />
            <ActionButton
              icon={<DeleteIcon />}
              onClick={(e) => {
                e.stopPropagation();
                onDelete(model);
              }}
              tooltip="Delete model"
              color="error"
            />
          </Box>
        </Box>

        <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mb: 2, minHeight: 40, flexGrow: 1 }}
          >
            {model.description}
          </Typography>

          <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mb: 2 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between" }}>
              <Typography variant="body2" color="text.secondary">
                API Key:
              </Typography>
              <Typography
                variant="body2"
                sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}
              >
                {maskApiKey(model.api_key)}
              </Typography>
            </Box>
          </Box>

          <Box
            sx={{
              display: "flex",
              justifyContent: "flex-end",
              alignItems: "center",
              mt: "auto",
              pt: 2,
            }}
          >
            <Chip
              label={model.type}
              variant="outlined"
              size="small"
              sx={{
                ...sharedTheme.actionButton,
                textTransform: "capitalize",
                fontWeight: 500,
                fontSize: "0.75rem",
              }}
            />
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}
