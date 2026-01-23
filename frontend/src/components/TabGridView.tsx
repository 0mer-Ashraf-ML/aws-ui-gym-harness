/**
 * TabGridView - Display browser tabs in a grid layout
 * Used for list_tabs action visualization
 */

import { Box, Typography, useTheme, Chip } from "@mui/material";
import { Tab as TabIcon, CheckCircle } from "@mui/icons-material";

interface TabData {
  index: number;
  url: string;
  is_current: boolean;
}

interface TabGridViewProps {
  tabs: TabData[];
  currentTabIndex?: number;
  tabCount?: number;
}

export default function TabGridView({ tabs, currentTabIndex, tabCount }: TabGridViewProps) {
  const theme = useTheme();

  if (!tabs || tabs.length === 0) {
    return (
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          p: 4,
          bgcolor: theme.palette.background.paper,
          borderRadius: 2,
          border: `2px dashed ${theme.palette.divider}`,
        }}
      >
        <TabIcon sx={{ fontSize: 48, color: theme.palette.text.disabled, mb: 2 }} />
        <Typography variant="body1" color="text.secondary">
          No tabs open
        </Typography>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        gap: 2,
        p: 2,
        bgcolor: theme.palette.background.default,
        borderRadius: 2,
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          pb: 1,
          borderBottom: `2px solid ${theme.palette.divider}`,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <TabIcon sx={{ fontSize: 24, color: theme.palette.primary.main }} />
          <Typography variant="h6" fontWeight="bold">
            Browser Tabs
          </Typography>
        </Box>
        <Chip
          label={`${tabCount ?? tabs.length} tab${(tabCount ?? tabs.length) !== 1 ? "s" : ""}`}
          size="small"
          color="primary"
          sx={{ fontWeight: "bold" }}
        />
      </Box>

      {/* Tab Grid */}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
          gap: 2,
        }}
      >
        {tabs.map((tab) => {
          const isCurrent = tab.is_current || tab.index === currentTabIndex;
          const url = new URL(tab.url || "about:blank");
          const displayUrl = tab.url || "about:blank";
          const hostname = url.hostname || "about:blank";

          return (
            <Box
              key={tab.index}
              sx={{
                display: "flex",
                flexDirection: "column",
                p: 2,
                bgcolor: isCurrent
                  ? theme.palette.mode === "dark"
                    ? theme.palette.primary.dark
                    : theme.palette.primary.light
                  : theme.palette.background.paper,
                borderRadius: 2,
                border: isCurrent
                  ? `3px solid ${theme.palette.primary.main}`
                  : `1px solid ${theme.palette.divider}`,
                boxShadow: isCurrent ? `0 4px 12px ${theme.palette.primary.main}40` : "none",
                transition: "all 0.2s ease-in-out",
                "&:hover": {
                  boxShadow: `0 4px 12px ${theme.palette.action.hover}`,
                  transform: "translateY(-2px)",
                },
              }}
            >
              {/* Tab Index & Status */}
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  mb: 1,
                }}
              >
                <Chip
                  label={`Tab ${tab.index + 1}`}
                  size="small"
                  color={isCurrent ? "primary" : "default"}
                  sx={{ fontWeight: "bold", fontSize: 12 }}
                />
                {isCurrent && (
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                    <CheckCircle
                      sx={{
                        fontSize: 16,
                        color: theme.palette.success.main,
                      }}
                    />
                    <Typography
                      variant="caption"
                      sx={{
                        color: theme.palette.success.main,
                        fontWeight: "bold",
                        fontSize: 11,
                      }}
                    >
                      CURRENT
                    </Typography>
                  </Box>
                )}
              </Box>

              {/* Hostname */}
              <Typography
                variant="subtitle2"
                fontWeight="bold"
                sx={{
                  mb: 0.5,
                  color: isCurrent ? theme.palette.primary.contrastText : theme.palette.text.primary,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {hostname}
              </Typography>

              {/* Full URL */}
              <Typography
                variant="caption"
                sx={{
                  fontFamily: "monospace",
                  color: isCurrent
                    ? theme.palette.mode === "dark"
                      ? theme.palette.grey[300]
                      : theme.palette.grey[700]
                    : theme.palette.text.secondary,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  fontSize: 11,
                }}
                title={displayUrl}
              >
                {displayUrl}
              </Typography>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}

