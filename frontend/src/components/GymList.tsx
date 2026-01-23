import {
  Box,
  Typography,
  Alert,
} from "@mui/material";
import { FitnessCenter as FitnessCenterIcon } from "@mui/icons-material";
import { useGymsWithTaskCounts } from "../hooks/useGyms";
import type { GymWithTaskCount } from "../types";
import GymListCard from "./GymListCard";
import PageSkeleton from "./PageSkeleton";
import EmptyState from "./EmptyState";

interface GymListProps {
  onSelectGym: (gym: GymWithTaskCount) => void;
  onAddTask: (gym: GymWithTaskCount) => void;
}

export default function GymList({ onSelectGym, onAddTask }: GymListProps) {
  const { data: gyms, isLoading, error } = useGymsWithTaskCounts();

  if (isLoading) {
    return (
      <PageSkeleton
        variant="task"
        cardCount={6}
        showCardActions={true}
        cardLines={4}
      />
    );
  }

  if (error) {
    return (
      <Alert severity="error">
        Failed to load gyms. Please try again later.
      </Alert>
    );
  }

  if (!gyms || gyms.length === 0) {
    return (
      <EmptyState
        icon={<FitnessCenterIcon />}
        title="No gyms found"
        description="Get started by creating your first gym"
        primaryAction={{
          label: "Create Your First Gym",
          icon: <FitnessCenterIcon />,
          onClick: () => {
            // This would typically open a gym creation dialog
            console.log("Create gym clicked");
          },
        }}
      />
    );
  }

  return (
    <Box>
      <Typography
        variant="h4"
        component="h1"
        sx={{
          fontWeight: 600,
          mb: 3,
          color: "text.primary",
        }}
      >
        Select a Gym
      </Typography>
      
      <Typography
        variant="body1"
        color="text.secondary"
        sx={{ mb: 4 }}
      >
        Choose a gym to view and manage its tasks
      </Typography>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            sm: "1fr",
            md: "repeat(2, 1fr)",
            lg: "repeat(2, 1fr)",
            xl: "repeat(2, 1fr)",
          },
          gap: 3,
        }}
      >
        {gyms.map((gym) => (
          <GymListCard
            key={gym.uuid}
            gym={gym}
            onSelect={onSelectGym}
            onAddTask={onAddTask}
          />
        ))}
      </Box>
    </Box>
  );
}
