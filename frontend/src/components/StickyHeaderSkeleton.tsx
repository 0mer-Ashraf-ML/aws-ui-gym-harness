import { Box, Skeleton, useTheme } from "@mui/material";

interface StickyHeaderSkeletonProps {
  leftOffset?: number;
  hideDrawer?: boolean;
}

export default function StickyHeaderSkeleton({
  leftOffset = 240,
  hideDrawer = false,
}: StickyHeaderSkeletonProps) {
  const theme = useTheme();
  const appBarHeight = theme.mixins.toolbar.minHeight || 64;

  return (
    <Box
      sx={{
        position: "fixed",
        top: appBarHeight,
        left: hideDrawer ? 0 : leftOffset,
        right: 0,
        zIndex: theme.zIndex.drawer,
        backgroundColor: theme.palette.mode === "light" ? "#F8F8F7" : "#161616",
        borderBottom: 1,
        borderColor: "divider",
        px: 3,
        py: 2,
      }}
    >
      <Box
        display="flex"
        alignItems="center"
        gap={2}
        flexWrap="wrap"
        sx={{
          maxWidth: 1600,
          mx: "auto",
        }}
      >
        <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, flex: "1 1 auto", gap: 0.5 }}>
          <Skeleton variant="text" width={120} height={28} />
          <Skeleton variant="text" width={300} height={16} />
        </Box>
        <Box display="flex" gap={1.5} alignItems="center" flexWrap="wrap" sx={{ flex: "0 0 auto" }}>
          <Skeleton variant="rectangular" width={80} height={32} sx={{ borderRadius: 1 }} />
          <Skeleton variant="rectangular" width={80} height={32} sx={{ borderRadius: 1 }} />
          <Skeleton variant="rectangular" width={60} height={32} sx={{ borderRadius: 1 }} />
          <Skeleton variant="rectangular" width={100} height={32} sx={{ borderRadius: 1 }} />
        </Box>
      </Box>
    </Box>
  );
}

