import React from "react";
import {
  Card,
  CardContent,
  CardActions,
  Typography,
  Box,
  Chip,
  Button,
  IconButton,
  Tooltip,
} from "@mui/material";
import {
  FitnessCenter as FitnessCenterIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Launch as LaunchIcon,
} from "@mui/icons-material";
import type { Gym } from "../types";

interface GymCardProps {
  gym: Gym;
  onEdit: (gym: Gym) => void;
  onDelete?: (gym: Gym) => void;
  onView?: (gym: Gym) => void;
}

export default function GymCard({ gym, onEdit, onDelete, onView }: GymCardProps) {
  const handleEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    onEdit(gym);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete?.(gym);
  };

  const handleView = (e: React.MouseEvent) => {
    e.stopPropagation();
    onView?.(gym);
  };

  return (
    <Card
      sx={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        transition: "all 0.2s ease-in-out",
        "&:hover": {
          transform: "translateY(-2px)",
          boxShadow: (theme) => theme.shadows[4],
        },
      }}
    >
      <CardContent sx={{ flexGrow: 1, pb: 1 }}>
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            mb: 2,
          }}
        >
          <FitnessCenterIcon
            sx={{
              fontSize: 32,
              color: "primary.main",
            }}
          />
          <Box sx={{ flexGrow: 1 }}>
            <Typography
              variant="h6"
              component="h3"
              sx={{
                fontWeight: 600,
                lineHeight: 1.2,
                mb: 0.5,
              }}
            >
              {gym.name}
            </Typography>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{
                lineHeight: 1.3,
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              {gym.description || "No description available"}
            </Typography>
          </Box>
        </Box>

        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            mb: 1,
          }}
        >
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.75rem" }}>
            Base URL:
          </Typography>
          <Typography
            variant="body2"
            sx={{
              fontSize: "0.75rem",
              fontFamily: "monospace",
              backgroundColor: "action.hover",
              px: 1,
              py: 0.25,
              borderRadius: 0.5,
              maxWidth: "100%",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {gym.base_url}
          </Typography>
        </Box>

        <Chip
          label={gym.verification_strategy.replace("_", " ").toUpperCase()}
          size="small"
          variant="outlined"
          sx={{
            fontSize: "0.7rem",
            height: 20,
          }}
        />
      </CardContent>

      <CardActions
        sx={{
          px: 2,
          pb: 2,
          pt: 0,
          justifyContent: "space-between",
        }}
      >
        <Box sx={{ display: "flex", gap: 0.5 }}>
          <Tooltip title="Edit Gym">
            <IconButton
              size="small"
              onClick={handleEdit}
              sx={{
                color: "primary.main",
                "&:hover": {
                  backgroundColor: "primary.light",
                  color: "white",
                },
              }}
            >
              <EditIcon />
            </IconButton>
          </Tooltip>
          
          {onDelete && (
            <Tooltip title="Delete Gym">
              <IconButton
                size="small"
                onClick={handleDelete}
                sx={{
                  color: "error.main",
                  "&:hover": {
                    backgroundColor: "error.light",
                    color: "white",
                  },
                }}
              >
                <DeleteIcon />
              </IconButton>
            </Tooltip>
          )}
        </Box>

        {onView && (
          <Button
            size="small"
            endIcon={<LaunchIcon />}
            sx={{
              textTransform: "none",
              fontWeight: 500,
            }}
            onClick={handleView}
          >
            View Details
          </Button>
        )}
      </CardActions>
    </Card>
  );
}