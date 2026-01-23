/**
 * Timeline - Displays interleaved model thinking and actions
 */

import { Box, Typography, Chip, IconButton, useTheme, Collapse } from "@mui/material";
import {
  SmartToy as AIIcon,
  Psychology as ThinkingIcon,
  Mouse as ClickIcon,
  Keyboard as TypeIcon,
  Terminal as BashIcon,
  Code as EditorIcon,
  Navigation as NavigateIcon,
  Camera as ScreenshotIcon,
  TouchApp as ActionIcon,
  ExpandMore as ExpandIcon,
  ExpandLess as CollapseIcon,
  Image as ImageIcon,
} from "@mui/icons-material";
import { useState, useEffect, useRef } from "react";
import type { TimelineEntryUnion, ActionEntry, ModelThinkingEntry, ModelResponseEntry } from "../types";

interface TimelineProps {
  entries: TimelineEntryUnion[];
  currentActionIndex?: number;
  isLive?: boolean;
  onActionSelect?: (action: ActionEntry) => void;
  shouldAutoScroll?: boolean;
}

export default function Timeline({
  entries,
  currentActionIndex,
  isLive = false,
  onActionSelect,
  shouldAutoScroll = true,
}: TimelineProps) {
  const theme = useTheme();
  const [expandedEntries, setExpandedEntries] = useState<Set<string>>(new Set());
  const actionRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [, setUpdateTick] = useState(0); // Force re-render for live timestamps

  const toggleExpand = (entryId: string) => {
    setExpandedEntries((prev) => {
      const next = new Set(prev);
      if (next.has(entryId)) {
        next.delete(entryId);
      } else {
        next.add(entryId);
      }
      return next;
    });
  };

  // ✅ Update timestamps every second for accurate "X ago" display
  useEffect(() => {
    const interval = setInterval(() => {
      setUpdateTick(prev => prev + 1);
    }, 1000); // Update every second
    
    return () => clearInterval(interval);
  }, []);

  // ✅ Auto-scroll to current action (works for both live mode and playback)
  useEffect(() => {
    if (shouldAutoScroll && currentActionIndex !== undefined && actionRefs.current.has(currentActionIndex)) {
      const actionElement = actionRefs.current.get(currentActionIndex);
      if (actionElement && scrollContainerRef.current) {
        actionElement.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
        });
      }
    }
  }, [currentActionIndex, shouldAutoScroll]);

  const getActionIcon = (actionType: string) => {
    switch (actionType) {
      case "click":
        return <ClickIcon fontSize="small" />;
      case "type":
        return <TypeIcon fontSize="small" />;
      case "key_press":
        return <TypeIcon fontSize="small" />;
      case "bash_command":
        return <BashIcon fontSize="small" />;
      case "editor_action":
        return <EditorIcon fontSize="small" />;
      case "navigate":
        return <NavigateIcon fontSize="small" />;
      case "screenshot":
        return <ScreenshotIcon fontSize="small" />;
      default:
        return <ActionIcon fontSize="small" />;
    }
  };

  const getRelativeTime = (timestamp: string) => {
    const now = new Date();
    // ✅ Handle timezone: If timestamp doesn't have 'Z' or timezone offset, treat as UTC
    let then: Date;
    if (timestamp.endsWith('Z') || timestamp.includes('+') || timestamp.match(/[+-]\d{2}:\d{2}$/)) {
      // Has timezone info, parse normally
      then = new Date(timestamp);
    } else {
      // No timezone info, assume UTC
      then = new Date(timestamp + 'Z');
    }
    
    const diffMs = now.getTime() - then.getTime();
    const diffSecs = Math.floor(diffMs / 1000);

    if (diffSecs < 1) return "Just now";
    if (diffSecs < 60) return `${diffSecs}s ago`;
    if (diffSecs < 3600) return `${Math.floor(diffSecs / 60)}m ago`;
    if (diffSecs < 86400) return `${Math.floor(diffSecs / 3600)}h ago`;
    return `${Math.floor(diffSecs / 86400)}d ago`;
  };

  // Calculate action index for each action entry
  const actionIndices = new Map<string, number>();
  let actionCount = 0;
  entries.forEach((entry) => {
    if (entry.entry_type === "action") {
      actionIndices.set(entry.id, actionCount);
      actionCount++;
    }
  });

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 2,
          borderBottom: `1px solid ${theme.palette.divider}`,
          bgcolor: theme.palette.background.paper,
        }}
      >
        {isLive && (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1,
              mb: 1,
            }}
          >
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                bgcolor: theme.palette.success.main,
                animation: "pulse 2s infinite",
                "@keyframes pulse": {
                  "0%": { opacity: 1 },
                  "50%": { opacity: 0.4 },
                  "100%": { opacity: 1 },
                },
              }}
            />
            <Typography variant="body2" color="success.main" fontWeight="medium">
              LIVE STREAMING
            </Typography>
          </Box>
        )}
        <Typography variant="h6">Timeline</Typography>
        <Typography variant="body2" color="text.secondary">
          {entries.length} entries
        </Typography>
      </Box>

      {/* Timeline Entries */}
      <Box
        ref={scrollContainerRef}
        sx={{
          flex: 1,
          overflow: "auto",
          p: 2,
        }}
      >
        {entries.length === 0 ? (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              gap: 1,
            }}
          >
            <Typography variant="h6" color="text.secondary">
              No entries yet
            </Typography>
            <Typography variant="body2" color="text.disabled">
              Actions will appear here as they are executed
            </Typography>
          </Box>
        ) : (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
            {entries.map((entry) => {
              if (entry.entry_type === "model_thinking" || entry.entry_type === "model_response") {
                const modelEntry = entry as ModelThinkingEntry | ModelResponseEntry;
                const isExpanded = expandedEntries.has(entry.id);
                const isThinking = entry.entry_type === "model_thinking";

                return (
                  <Box
                    key={entry.id}
                    sx={{
                      p: 2,
                      borderRadius: 1,
                      bgcolor: isThinking
                        ? theme.palette.mode === "dark"
                          ? "rgba(144, 202, 249, 0.08)"
                          : "rgba(33, 150, 243, 0.08)"
                        : theme.palette.mode === "dark"
                        ? "rgba(186, 104, 200, 0.08)"
                        : "rgba(156, 39, 176, 0.08)",
                      border: `1px solid ${
                        isThinking
                          ? theme.palette.info.main + "30"
                          : theme.palette.secondary.main + "30"
                      }`,
                    }}
                  >
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 1,
                        mb: 1,
                      }}
                    >
                      {isThinking ? (
                        <ThinkingIcon sx={{ color: theme.palette.info.main, fontSize: 20 }} />
                      ) : (
                        <AIIcon sx={{ color: theme.palette.secondary.main, fontSize: 20 }} />
                      )}
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="subtitle2" fontWeight="medium">
                          {isThinking ? "AI Thinking" : "AI Response"}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {getRelativeTime(entry.timestamp)}
                        </Typography>
                      </Box>
                      <IconButton
                        size="small"
                        onClick={() => toggleExpand(entry.id)}
                      >
                        {isExpanded ? <CollapseIcon fontSize="small" /> : <ExpandIcon fontSize="small" />}
                      </IconButton>
                    </Box>
                    <Collapse in={isExpanded} collapsedSize={60}>
                      <Typography
                        variant="body2"
                        sx={{
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                        }}
                      >
                        {modelEntry.content}
                      </Typography>
                    </Collapse>
                  </Box>
                );
              } else {
                const actionEntry = entry as ActionEntry;
                const actionIndex = actionIndices.get(entry.id) ?? -1;
                const isCurrent = actionIndex === currentActionIndex;
                const hasScreenshot = !!actionEntry.screenshot_path;

                return (
                  <Box
                    key={entry.id}
                    ref={(el: HTMLDivElement | null) => {
                      if (el && actionIndex !== -1) {
                        actionRefs.current.set(actionIndex, el);
                      }
                    }}
                    onClick={() => onActionSelect?.(actionEntry)}
                    sx={{
                      p: 2,
                      borderRadius: 1,
                      bgcolor: isCurrent
                        ? theme.palette.action.selected
                        : theme.palette.background.paper,
                      border: `2px solid ${
                        isCurrent
                          ? theme.palette.primary.main
                          : theme.palette.divider
                      }`,
                      cursor: "pointer",
                      transition: "all 0.2s",
                      "&:hover": {
                        bgcolor: theme.palette.action.hover,
                        borderColor: theme.palette.primary.light,
                      },
                    }}
                  >
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 1.5,
                      }}
                    >
                      <Box
                        sx={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: 32,
                          height: 32,
                          borderRadius: 1,
                          bgcolor: theme.palette.primary.main + "20",
                          color: theme.palette.primary.main,
                          flexShrink: 0,
                        }}
                      >
                        {getActionIcon(actionEntry.action_type)}
                      </Box>
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Box
                          sx={{
                            display: "flex",
                            alignItems: "center",
                            gap: 1,
                            mb: 0.5,
                          }}
                        >
                          <Typography variant="subtitle2" fontWeight="medium">
                            {actionEntry.action_name}
                          </Typography>
                          {hasScreenshot && (
                            <ImageIcon
                              sx={{ fontSize: 16, color: theme.palette.text.secondary }}
                            />
                          )}
                        </Box>
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          sx={{
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                          }}
                        >
                          {actionEntry.description}
                        </Typography>
                        <Box
                          sx={{
                            display: "flex",
                            alignItems: "center",
                            gap: 1,
                            mt: 1,
                          }}
                        >
                          <Typography variant="caption" color="text.disabled">
                            {getRelativeTime(entry.timestamp)}
                          </Typography>
                          <Chip
                            label={actionEntry.status}
                            size="small"
                            color={
                              actionEntry.status === "success"
                                ? "success"
                                : actionEntry.status === "failed"
                                ? "error"
                                : "warning"
                            }
                            sx={{ height: 20, fontSize: 11 }}
                          />
                        </Box>
                      </Box>
                    </Box>
                  </Box>
                );
              }
            })}
          </Box>
        )}
      </Box>
    </Box>
  );
}

