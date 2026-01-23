import { Box, Skeleton, Divider } from "@mui/material";
import GridSkeleton from "./GridSkeleton";
import BatchOverallSummary from "./BatchOverallSummary";

export default function BatchRunsSkeleton() {
  return (
    <Box sx={{ py: 4 }}>
      {/* Header Section Skeleton */}
      <Box
        sx={{
          mb: 3,
        }}
      >
        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="flex-start"
          mb={3}
        >
          {/* Title and Subtitle */}
          <Box>
            <Skeleton
              variant="text"
              width={300}
              height={40}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                mb: 1,
              }}
            />
            <Skeleton
              variant="text"
              width={250}
              height={24}
              sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
            />
          </Box>

          {/* Toolbar Controls */}
          <Box display="flex" gap={2} alignItems="center" flexWrap="wrap">
            {/* Search Field */}
            <Skeleton
              variant="rectangular"
              width={300}
              height={40}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                borderRadius: 1,
              }}
            />
            {/* Filter Menu */}
            <Skeleton
              variant="circular"
              width={40}
              height={40}
              sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
            />
            {/* Sort Menu */}
            <Skeleton
              variant="circular"
              width={40}
              height={40}
              sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
            />
            {/* View Toggle */}
            <Skeleton
              variant="rectangular"
              width={80}
              height={36}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                borderRadius: 1,
              }}
            />
            {/* Action Buttons */}
            <Skeleton
              variant="rectangular"
              width={120}
              height={36}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                borderRadius: 1,
              }}
            />
            <Skeleton
              variant="rectangular"
              width={100}
              height={36}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                borderRadius: 1,
              }}
            />
            <Skeleton
              variant="rectangular"
              width={140}
              height={36}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                borderRadius: 1,
              }}
            />
          </Box>
        </Box>
      </Box>

      {/* Divider */}
      <Divider sx={{ my: 3 }} />

      {/* Batch Overall Summary - Uses its own skeleton */}
      <BatchOverallSummary
        summary={undefined}
        isLoading={true}
        error={null}
      />

      {/* Batch Insights Tabs Skeleton */}
      <Box sx={{ mt: 2, mb: 3 }}>
        {/* Header with icon */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1 }}>
          <Skeleton
            variant="circular"
            width={16}
            height={16}
            sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
          />
          <Skeleton
            variant="text"
            width={120}
            height={20}
            sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
          />
        </Box>

        {/* Tabs Bar */}
        <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
          <Box sx={{ display: "flex", gap: 2 }}>
            <Skeleton
              variant="rectangular"
              width={100}
              height={40}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                borderRadius: "4px 4px 0 0",
              }}
            />
            <Skeleton
              variant="rectangular"
              width={100}
              height={40}
              sx={{
                bgcolor: "rgba(255, 255, 255, 0.1)",
                borderRadius: "4px 4px 0 0",
              }}
            />
          </Box>
        </Box>

        {/* Tab Content */}
        <Box sx={{ p: 3 }}>
          <Box
            sx={{
              bgcolor: "rgba(255, 255, 255, 0.05)",
              border: 1,
              borderColor: "divider",
              borderRadius: 1,
              p: 2,
            }}
          >
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <Skeleton
                variant="text"
                width="100%"
                height={20}
                sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
              />
              <Skeleton
                variant="text"
                width="90%"
                height={20}
                sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
              />
              <Skeleton
                variant="text"
                width="95%"
                height={20}
                sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
              />
              <Skeleton
                variant="text"
                width="85%"
                height={20}
                sx={{ bgcolor: "rgba(255, 255, 255, 0.1)" }}
              />
            </Box>
          </Box>
        </Box>
      </Box>

      {/* Executions Grid Skeleton */}
      <GridSkeleton
        count={6}
        variant="run"
        showActions={false}
        lines={3}
      />
    </Box>
  );
}

