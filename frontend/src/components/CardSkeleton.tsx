import {
  Card,
  CardContent,
  CardActions,
  Skeleton,
  Box,
  useTheme,
} from "@mui/material";

interface CardSkeletonProps {
  variant?: "gym" | "task" | "run" | "model" | "default";
  showActions?: boolean;
  lines?: number;
}

export default function CardSkeleton({
  variant = "default",
  showActions = true,
  lines = 2,
}: CardSkeletonProps) {
  const theme = useTheme();

  return (
    <Card
      sx={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: theme.palette.mode === "light" ? "#f5f5f5" : "#202020",
        border: `1px solid ${theme.palette.divider}`,
      }}
    >
      <CardContent sx={{ flexGrow: 1 }}>
        {/* Header area with title and optional icon */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            mb: 2,
          }}
        >
          <Skeleton
            variant="text"
            width="70%"
            height={32}
            sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
          />
          {variant === "gym" && (
            <Skeleton
              variant="circular"
              width={20}
              height={20}
              sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
            />
          )}
        </Box>

        {/* Content/Description area */}
        <Box sx={{ mb: 2 }}>
          {Array.from({ length: lines }, (_, index) => (
            <Skeleton
              key={index}
              variant="text"
              width={index === lines - 1 ? "60%" : "100%"}
              height={20}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                mb: 0.5,
              }}
            />
          ))}
        </Box>

        {/* Additional content based on variant */}
        {variant === "gym" && (
          <Box sx={{ mt: "auto" }}>
            <Skeleton
              variant="text"
              width="80%"
              height={16}
              sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
            />
          </Box>
        )}

        {variant === "run" && (
          <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
            <Skeleton
              variant="rectangular"
              width={60}
              height={20}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                borderRadius: 1,
              }}
            />
            <Skeleton
              variant="rectangular"
              width={80}
              height={20}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                borderRadius: 1,
              }}
            />
          </Box>
        )}
      </CardContent>

      {/* Action buttons area */}
      {showActions && (
        <CardActions sx={{ justifyContent: "space-between", px: 2, pb: 2 }}>
          <Skeleton
            variant="rectangular"
            width={60}
            height={32}
            sx={{
              bgcolor: "rgba(255, 255, 255, 0.1)",
              borderRadius: 1,
            }}
          />
          <Box sx={{ display: "flex", gap: 1 }}>
            <Skeleton
              variant="circular"
              width={32}
              height={32}
              sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
            />
            <Skeleton
              variant="circular"
              width={32}
              height={32}
              sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
            />
          </Box>
        </CardActions>
      )}
    </Card>
  );
}
