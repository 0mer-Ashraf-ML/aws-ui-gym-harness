import { Box, Fade } from "@mui/material";
import CardSkeleton from "./CardSkeleton";

interface ContentSkeletonProps {
  variant?: "gym" | "task" | "run" | "model" | "default";
  count?: number;
  showActions?: boolean;
  lines?: number;
  layout?: "grid" | "list";
}

export default function ContentSkeleton({
  variant = "default",
  count = 6,
  showActions = true,
  lines = 2,
  layout = "grid",
}: ContentSkeletonProps) {
  if (layout === "list") {
    return (
      <Fade in timeout={300}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
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
