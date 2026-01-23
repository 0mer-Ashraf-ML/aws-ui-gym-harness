import { Box, Skeleton } from "@mui/material";
import GridSkeleton from "./GridSkeleton";

interface PageSkeletonProps {
  variant?: "gym" | "task" | "run" | "model" | "default";
  cardCount?: number;
  showCardActions?: boolean;
  cardLines?: number;
}

export default function PageSkeleton({
  variant = "default",
  cardCount = 6,
  showCardActions = true,
  cardLines = 2,
}: PageSkeletonProps) {
  return (
    <Box>
      {/* Header Section Skeleton */}
      <Box sx={{ mb: 4 }}>
        {/* Title Section */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 6 }}>
          {/* Icon */}
          <Skeleton
            variant="rectangular"
            width={48}
            height={48}
            sx={{
              bgcolor: "rgba(255, 255, 255, 0.1)",
              borderRadius: 1,
            }}
          />

          {/* Title and Description */}
          <Box sx={{ flexGrow: 1 }}>
            <Skeleton
              variant="text"
              width={200}
              height={40}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                mb: 1,
              }}
            />
            <Skeleton
              variant="text"
              width={350}
              height={24}
              sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
            />
          </Box>
        </Box>

        {/* Controls Section */}
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 2,
          }}
        >
          {/* Search Bar */}
          <Box sx={{ minWidth: { xs: "100%", md: 400 }, maxWidth: 500 }}>
            <Skeleton
              variant="rectangular"
              width="100%"
              height={40}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                borderRadius: 1,
              }}
            />
          </Box>

          {/* Action Buttons */}
          <Box sx={{ display: "flex", gap: 1 }}>
            <Skeleton
              variant="rectangular"
              width={120}
              height={36}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                borderRadius: 1,
              }}
            />
          </Box>
        </Box>
      </Box>

      {/* Content Grid Skeleton */}
      <GridSkeleton
        count={cardCount}
        variant={variant}
        showActions={showCardActions}
        lines={cardLines}
      />
    </Box>
  );
}
