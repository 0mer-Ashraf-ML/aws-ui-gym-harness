import React from "react";
import { useNavigate } from "react-router-dom";
import {
  Card,
  CardContent,
  CardActions,
  Typography,
  Box,
  Chip,
  Button,
  Tooltip,
} from "@mui/material";
import {
  FitnessCenter as FitnessCenterIcon,
  Assignment as AssignmentIcon,
  Add as AddIcon,
  ArrowForward as ArrowForwardIcon,
} from "@mui/icons-material";
import type { GymWithTaskCount } from "../types";

interface GymCardProps {
  gym: GymWithTaskCount;
  onSelect: (gym: GymWithTaskCount) => void;
  onAddTask: (gym: GymWithTaskCount) => void;
}

export default function GymCard({ gym }: GymCardProps) {
  const navigate = useNavigate();

  const handleCardClick = () => {
    navigate(`/gyms/${gym.uuid}/tasks`);
  };

  const handleAddTaskClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click
    navigate(`/gyms/${gym.uuid}/tasks?action=add-task`);
  };

  return (
    <Card
      sx={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        cursor: "pointer",
        transition: "all 0.2s ease-in-out",
        "&:hover": {
          transform: "translateY(-4px)",
          boxShadow: (theme) => theme.shadows[8],
        },
      }}
      onClick={handleCardClick}
    >
      <CardContent sx={{ flexGrow: 1, pb: 2 }}>
        {/* Header Section */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 2,
            mb: 3,
          }}
        >
          <Box
            sx={{
              width: 48,
              height: 48,
              borderRadius: 2,
              backgroundColor: "primary.main",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <FitnessCenterIcon
              sx={{
                fontSize: 24,
                color: "white",
              }}
            />
          </Box>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography
              variant="h6"
              component="h3"
              sx={{
                fontWeight: 600,
                lineHeight: 1.2,
                mb: 0.5,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
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

        {/* Stats Section */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            mb: 2,
            p: 2,
            backgroundColor: "action.hover",
            borderRadius: 1,
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1,
            }}
          >
            <AssignmentIcon
              sx={{
                fontSize: 16,
                color: "primary.main",
              }}
            />
            <Typography variant="body2" color="text.primary" sx={{ fontWeight: 600 }}>
              {gym.task_count} {gym.task_count === 1 ? "Task" : "Tasks"}
            </Typography>
          </Box>

          <Chip
            label={gym.verification_strategy.replace("_", " ").toUpperCase()}
            size="small"
            variant="outlined"
            sx={{
              fontSize: "0.7rem",
              height: 24,
              fontWeight: 500,
            }}
          />
        </Box>

        {/* URL Section */}
        <Box
          sx={{
            p: 1.5,
            backgroundColor: "action.hover",
            borderRadius: 1,
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <Typography 
            variant="caption" 
            color="text.secondary" 
            sx={{ 
              fontSize: "0.75rem", 
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: 0.5,
              display: "block",
              mb: 0.5,
            }}
          >
            Base URL
          </Typography>
          <Typography
            variant="body2"
            sx={{
              fontSize: "0.8rem",
              fontFamily: "monospace",
              color: "text.primary",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {gym.base_url}
          </Typography>
        </Box>
      </CardContent>

      <CardActions
        sx={{
          px: 3,
          pb: 3,
          pt: 0,
          gap: 1,
        }}
      >
        <Button
          variant="contained"
          size="medium"
          endIcon={<ArrowForwardIcon />}
          onClick={handleCardClick}
          sx={{
            textTransform: "none",
            fontWeight: 500,
            flexGrow: 1,
          }}
        >
          View Tasks
        </Button>
        
        <Tooltip title="Add Task">
          <Button
            variant="outlined"
            size="medium"
            startIcon={<AddIcon />}
            onClick={handleAddTaskClick}
            sx={{
              textTransform: "none",
              fontWeight: 500,
              minWidth: "auto",
              px: 2,
            }}
          >
            Add Task
          </Button>
        </Tooltip>
      </CardActions>
    </Card>
  );
}