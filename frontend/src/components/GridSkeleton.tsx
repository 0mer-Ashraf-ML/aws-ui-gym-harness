import { Box, Fade } from "@mui/material";
import CardSkeleton from "./CardSkeleton";

interface GridSkeletonProps {
  count?: number;
  variant?: "gym" | "task" | "run" | "model" | "default";
  showActions?: boolean;
  lines?: number;
}

export default function GridSkeleton({
  count = 6,
  variant = "default",
  showActions = true,
  lines = 2,
}: GridSkeletonProps) {
  return (
    <Fade in timeout={300}>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            sm: "repeat(auto-fill, minmax(350px, 1fr))",
            lg: "repeat(auto-fill, minmax(320px, 1fr))",
            xl: "repeat(auto-fill, minmax(300px, 1fr))",
          },
          gap: 3,
        }}
      >
        {Array.from({ length: count }, (_, index) => (
          <CardSkeleton
            key={index}
            variant={variant}
            showActions={showActions}
            lines={lines}
          />
        ))}
      </Box>
    </Fade>
  );
}
