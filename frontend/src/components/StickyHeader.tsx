import { Box, Typography, useTheme } from "@mui/material";
import { forwardRef } from "react";
import type { ReactNode } from "react";

interface StickyHeaderProps {
  isScrolled: boolean;
  title: string;
  subtitle?: string | ReactNode;
  controls: ReactNode;
  leftOffset?: number;
  hideDrawer?: boolean;
}

const StickyHeader = forwardRef<HTMLDivElement, StickyHeaderProps>(function StickyHeader({
  isScrolled,
  title,
  subtitle,
  controls,
  leftOffset = 240,
  hideDrawer = false,
}, ref) {
  const theme = useTheme();
  const appBarHeight = theme.mixins.toolbar.minHeight || 64;

  return (
    <Box
      ref={ref}
      sx={{
        position: "fixed",
        top: appBarHeight,
        left: hideDrawer ? 0 : leftOffset,
        right: 0,
        zIndex: theme.zIndex.drawer,
        backgroundColor: theme.palette.mode === "light" ? "#F8F8F7" : "#161616",
        borderBottom: 1,
        borderColor: "divider",
        boxShadow: 2,
        backdropFilter: "blur(8px)",
        transform: isScrolled ? "translateY(0)" : "translateY(-100%)",
        opacity: isScrolled ? 1 : 0,
        transition: "transform 0.2s ease-in-out, opacity 0.2s ease-in-out",
        pointerEvents: isScrolled ? "auto" : "none",
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
        {/* Title and subtitle in sticky header */}
        <Box sx={{ display: "flex", flexDirection: "column", minWidth: 0, flex: "1 1 auto" }}>
          <Typography
            variant="h6"
            component="h1"
            noWrap
            sx={{ fontWeight: 600 }}
          >
            {title}
          </Typography>
          {subtitle && (
            <Typography
              variant="caption"
              color="text.secondary"
              noWrap
            >
              {subtitle}
            </Typography>
          )}
        </Box>

        {/* Controls in sticky header */}
        <Box display="flex" gap={1.5} alignItems="center" flexWrap="wrap" sx={{ flex: "0 0 auto" }}>
          {controls}
        </Box>
      </Box>
    </Box>
  );
});

export default StickyHeader;

