/**
 * ActionMonitoringView - Split-pane layout combining Timeline and BrowserView
 */

import { Box, IconButton, Tooltip, Slider, Typography, useTheme, Button } from "@mui/material";
import {
  PlayArrow,
  Pause,
  SkipNext,
  SkipPrevious,
  Speed,
  PlayCircle,
} from "@mui/icons-material";
import { useState, useMemo, useEffect } from "react";
import Timeline from "./Timeline";
import BrowserView from "./BrowserView";
import { usePlayback } from "../hooks/usePlayback";
import type { TimelineEntryUnion, ActionEntry } from "../types";

interface ActionMonitoringViewProps {
  executionId: string;
  iterationId: string;
  timelineEntries: TimelineEntryUnion[];
  isLive?: boolean;
  autoPlayCompleted?: boolean;
}

export default function ActionMonitoringView({
  executionId,
  iterationId,
  timelineEntries,
  isLive = false,
  autoPlayCompleted = false,
}: ActionMonitoringViewProps) {
  const theme = useTheme();
  const [splitPosition, setSplitPosition] = useState(35); // Percentage for left pane
  const [isManuallyPaused, setIsManuallyPaused] = useState(false); // Track if user manually paused
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true); // Track if auto-scroll should be enabled

  // Extract only actions for playback (memoized to prevent infinite loops)
  const actionEntries = useMemo(
    () => timelineEntries.filter((entry): entry is ActionEntry => entry.entry_type === "action"),
    [timelineEntries]
  );

  const playback = usePlayback(
    actionEntries,
    isLive ? "executing" : "passed",
    {
      autoStart: autoPlayCompleted && !isLive,
      defaultSpeed: 1, // 1x speed
    }
  );

  const {
    currentAction,
    currentIndex,
    isPlaying,
    speed: playbackSpeed,
    controls,
    progress,
  } = playback;

  const { play, pause, next, previous, setSpeed } = controls;

  // ✅ Auto-follow latest action when live and not manually paused
  useEffect(() => {
    if (isLive && !isManuallyPaused && actionEntries.length > 0) {
      const latestIndex = actionEntries.length - 1;
      if (currentIndex !== latestIndex) {
        controls.jumpTo(latestIndex);
      }
    }
  }, [isLive, isManuallyPaused, actionEntries.length, currentIndex, controls]);

  // ✅ Reset manual pause when iteration is no longer live
  useEffect(() => {
    if (!isLive) {
      setIsManuallyPaused(false);
    }
  }, [isLive]);

  // ✅ Enable auto-scroll when playback is playing
  useEffect(() => {
    if (isPlaying) {
      setShouldAutoScroll(true);
    }
  }, [isPlaying]);

  const handleActionSelect = useMemo(
    () => (action: ActionEntry) => {
      // ✅ Mark as manually paused when user clicks an action
      if (isLive) {
        setIsManuallyPaused(true);
      }
      pause();
      // Disable auto-scroll when user manually selects an action
      setShouldAutoScroll(false);
      // Find this action in the actions-only array and jump to it
      const actionIndex = actionEntries.findIndex((a) => a.id === action.id);
      if (actionIndex !== -1) {
        controls.jumpTo(actionIndex);
      }
    },
    [pause, actionEntries, controls, isLive]
  );

  const handleContinueLive = () => {
    setIsManuallyPaused(false);
    // Enable auto-scroll when continuing live
    setShouldAutoScroll(true);
    // Jump to latest action
    if (actionEntries.length > 0) {
      controls.jumpTo(actionEntries.length - 1);
    }
  };

  // Wrapper functions to enable auto-scroll when using playback controls
  const handlePlay = () => {
    setShouldAutoScroll(true);
    play();
  };

  const handleNext = () => {
    setShouldAutoScroll(true);
    next();
  };

  const handlePrevious = () => {
    setShouldAutoScroll(true);
    previous();
  };

  const handlePause = () => {
    pause();
    // Don't change auto-scroll state on pause
  };

  const handleSliderChange = (_: Event, value: number | number[]) => {
    pause();
    // Enable auto-scroll when using slider
    setShouldAutoScroll(true);
    controls.jumpTo(value as number);
  };

  const speeds = [
    { label: "0.5x", value: 0.5 },
    { label: "1x", value: 1 },
    { label: "1.5x", value: 1.5 },
    { label: "2x", value: 2 },
    { label: "3x", value: 3 },
  ];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* ✅ Continue Live Button (only when live and manually paused) */}
      {isLive && isManuallyPaused && (
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            px: 3,
            py: 1.5,
            bgcolor: theme.palette.warning.main,
            color: "#fff",
            borderBottom: `2px solid ${theme.palette.warning.dark}`,
          }}
        >
          <Button
            variant="contained"
            startIcon={<PlayCircle />}
            onClick={handleContinueLive}
            sx={{
              bgcolor: "#fff",
              color: theme.palette.warning.dark,
              fontWeight: "bold",
              "&:hover": {
                bgcolor: theme.palette.grey[100],
              },
            }}
          >
            Continue Live
          </Button>
        </Box>
      )}

      {/* Playback Controls (only for completed iterations with actions) */}
      {actionEntries.length > 0 && !isLive && (
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            px: 3,
            py: 1.5,
            bgcolor: theme.palette.background.paper,
            borderBottom: `1px solid ${theme.palette.divider}`,
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Tooltip title="Previous Action">
              <span>
                <IconButton
                  size="small"
                  onClick={handlePrevious}
                  disabled={currentIndex === 0}
                >
                  <SkipPrevious />
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title={isPlaying ? "Pause" : "Play"}>
              <IconButton
                size="medium"
                onClick={isPlaying ? handlePause : handlePlay}
                sx={{
                  bgcolor: theme.palette.primary.main,
                  color: "#fff",
                  "&:hover": {
                    bgcolor: theme.palette.primary.dark,
                  },
                }}
              >
                {isPlaying ? <Pause /> : <PlayArrow />}
              </IconButton>
            </Tooltip>
            <Tooltip title="Next Action">
              <span>
                <IconButton
                  size="small"
                  onClick={handleNext}
                  disabled={currentIndex >= actionEntries.length - 1}
                >
                  <SkipNext />
                </IconButton>
              </span>
            </Tooltip>
          </Box>

          {/* Progress Indicator */}
          <Box sx={{ flex: 1, mx: 3, display: "flex", alignItems: "center", gap: 2 }}>
            <Typography variant="body2" color="text.secondary" sx={{ minWidth: 60 }}>
              {progress.current} / {progress.total}
            </Typography>
            <Slider
              value={currentIndex}
              min={0}
              max={actionEntries.length - 1}
              onChange={handleSliderChange}
              sx={{ flex: 1 }}
              disabled={actionEntries.length === 0}
            />
          </Box>

          {/* Speed Control */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Speed sx={{ color: theme.palette.text.secondary }} />
            <Box
              sx={{
                display: "flex",
                gap: 0.5,
                bgcolor: theme.palette.background.default,
                borderRadius: 1,
                p: 0.5,
              }}
            >
              {speeds.map((speedOption) => (
                <Box
                  key={speedOption.label}
                  onClick={() => setSpeed(speedOption.value)}
                  sx={{
                    px: 1.5,
                    py: 0.5,
                    borderRadius: 0.5,
                    cursor: "pointer",
                    bgcolor:
                      playbackSpeed === speedOption.value
                        ? theme.palette.primary.main
                        : "transparent",
                    color:
                      playbackSpeed === speedOption.value
                        ? "#fff"
                        : theme.palette.text.secondary,
                    transition: "all 0.2s",
                    "&:hover": {
                      bgcolor:
                        playbackSpeed === speedOption.value
                          ? theme.palette.primary.dark
                          : theme.palette.action.hover,
                    },
                  }}
                >
                  <Typography variant="caption" fontWeight="medium">
                    {speedOption.label}
                  </Typography>
                </Box>
              ))}
            </Box>
          </Box>
        </Box>
      )}

      {/* Split Pane Content */}
      <Box sx={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Left Pane - Timeline */}
        <Box
          sx={{
            width: `${splitPosition}%`,
            borderRight: `1px solid ${theme.palette.divider}`,
            overflow: "hidden",
          }}
        >
          <Timeline
            entries={timelineEntries}
            currentActionIndex={currentIndex}
            isLive={isLive && !isManuallyPaused}
            onActionSelect={handleActionSelect}
            shouldAutoScroll={shouldAutoScroll}
          />
        </Box>

        {/* Resizer Handle */}
        <Box
          sx={{
            width: 4,
            cursor: "col-resize",
            bgcolor: theme.palette.divider,
            "&:hover": {
              bgcolor: theme.palette.primary.main,
            },
            transition: "background-color 0.2s",
          }}
          onMouseDown={(e) => {
            e.preventDefault();
            const startX = e.clientX;
            const startSplit = splitPosition;

            const handleMouseMove = (moveEvent: MouseEvent) => {
              const deltaX = moveEvent.clientX - startX;
              const containerWidth = window.innerWidth;
              const deltaPercent = (deltaX / containerWidth) * 100;
              const newSplit = Math.min(Math.max(startSplit + deltaPercent, 20), 60);
              setSplitPosition(newSplit);
            };

            const handleMouseUp = () => {
              document.removeEventListener("mousemove", handleMouseMove);
              document.removeEventListener("mouseup", handleMouseUp);
            };

            document.addEventListener("mousemove", handleMouseMove);
            document.addEventListener("mouseup", handleMouseUp);
          }}
        />

        {/* Right Pane - Browser View */}
        <Box
          sx={{
            flex: 1,
            overflow: "hidden",
          }}
        >
          <BrowserView
            currentAction={currentAction}
            executionId={executionId}
            iterationId={iterationId}
            showClickIndicator={true}
          />
        </Box>
      </Box>
    </Box>
  );
}

