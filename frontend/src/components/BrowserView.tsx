/**
 * BrowserView - Realistic browser chrome with screenshot display
 */

import { Box, CircularProgress, Typography, useTheme, ToggleButton, ToggleButtonGroup, Chip } from "@mui/material";
import { VisibilityOff, Visibility } from "@mui/icons-material";
import { useState, useEffect, useRef, useCallback } from "react";
import type { ActionEntry } from "../types";
import TabGridView from "./TabGridView";

type ScreenshotView = "before" | "after";

interface BrowserViewProps {
  currentAction?: ActionEntry;
  executionId: string;
  iterationId: string;
  showClickIndicator?: boolean;
}

interface ScaledCoordinates {
  x: number;
  y: number;
}

interface DragPathMetadata {
  start: [number, number];
  end: [number, number];
  coordinates_normalized?: boolean;
  target_coordinates_normalized?: boolean;
}

interface ScrollLineMetrics {
  top: number;
  left: number;
  length: number;
  isHorizontal: boolean;
  startPoint: ScaledCoordinates;
  endPoint: ScaledCoordinates;
}

const NORMALIZED_COORD_ACTIONS = new Set([
  "click_at",
  "type_text_at",
  "scroll_at",
  "scroll_document",
  "hover_at",
  "drag_and_drop",
]);

const POINTER_ACTION_NAMES = new Set([
  "click",
  "left_click",
  "right_click",
  "double_click",
  "triple_click",
  "mouse_click",
  "mouse_move",
  "hover",
  "hover_at",
  "mouse_down",
  "mouse_up",
  "left_mouse_down",
  "left_mouse_up",
  "type",
  "type_text",
  "type_text_at",
  "drag_and_drop",
  "left_click_drag",
  "click_and_drag",
  "drag",
  "move",
]);

export default function BrowserView({
  currentAction,
  executionId,
  iterationId,
  showClickIndicator = true,
}: BrowserViewProps) {
  const theme = useTheme();
  const [isLoading, setIsLoading] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [screenshotView, setScreenshotView] = useState<ScreenshotView>("before");
  const [scaledCoords, setScaledCoords] = useState<ScaledCoordinates | null>(null);
  const [scaledTargetCoords, setScaledTargetCoords] = useState<ScaledCoordinates | null>(null);
  const [scaledScrollStart, setScaledScrollStart] = useState<ScaledCoordinates | null>(null);
  const [scaledScrollEnd, setScaledScrollEnd] = useState<ScaledCoordinates | null>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  // Determine if action has before/after screenshots (both must exist for toggle)
  const hasBeforeAfter = currentAction?.screenshot_before && currentAction?.screenshot_after;
  const hasLegacyScreenshot = currentAction?.screenshot_path;
  const hasSingleScreenshot = currentAction?.screenshot_after && !currentAction?.screenshot_before;

  const metadata = (currentAction?.metadata ?? {}) as Record<string, unknown>;
  const coordinatesNormalizedByName =
    !!currentAction?.action_name && NORMALIZED_COORD_ACTIONS.has(currentAction.action_name);
  const coordinatesNormalized =
    typeof metadata.coordinates_normalized === "boolean"
      ? (metadata.coordinates_normalized as boolean)
      : coordinatesNormalizedByName;

  const dragPath = metadata.drag_path as DragPathMetadata | undefined;

  const baseCoords = Array.isArray(metadata.coordinates)
    ? (metadata.coordinates as [number, number])
    : null;

  const pointerCoords = dragPath && Array.isArray(dragPath.start)
    ? (dragPath.start as [number, number])
    : baseCoords;

  const pointerCoordsNormalized =
    dragPath && typeof dragPath.coordinates_normalized === "boolean"
      ? dragPath.coordinates_normalized
      : coordinatesNormalized;

  const targetCoords = dragPath && Array.isArray(dragPath.end)
    ? (dragPath.end as [number, number])
    : Array.isArray(metadata.target_coordinates)
    ? (metadata.target_coordinates as [number, number])
    : null;

  const targetCoordsNormalized =
    dragPath && typeof dragPath.target_coordinates_normalized === "boolean"
      ? dragPath.target_coordinates_normalized
      : coordinatesNormalized;

  const scrollStartCoords = Array.isArray(metadata.scroll_start)
    ? (metadata.scroll_start as [number, number])
    : currentAction?.action_type === "scroll" && pointerCoords
    ? pointerCoords
    : null;

  const scrollEndCoords = Array.isArray(metadata.scroll_end)
    ? (metadata.scroll_end as [number, number])
    : null;
  const scrollStartNormalized =
    typeof metadata.scroll_start_normalized === "boolean"
      ? (metadata.scroll_start_normalized as boolean)
      : pointerCoordsNormalized;
  const scrollEndNormalized =
    typeof metadata.scroll_end_normalized === "boolean"
      ? (metadata.scroll_end_normalized as boolean)
      : pointerCoordsNormalized;

  const rawScrollDirection =
    typeof metadata.direction === "string"
      ? (metadata.direction as string)
      : typeof metadata.scroll_direction === "string"
      ? (metadata.scroll_direction as string)
      : "";
  const normalizedScrollDirection = rawScrollDirection.toLowerCase();
  const inferredDirection =
    normalizedScrollDirection ||
    (typeof metadata.amount === "number"
      ? ((metadata.amount as number) < 0 ? "up" : "down")
      : "");
  const scrollDirection =
    inferredDirection === "up" || inferredDirection === "down" ? inferredDirection : "";
  const scrollDistanceLabel =
    typeof metadata.scroll_distance_display === "string"
      ? (metadata.scroll_distance_display as string)
      : null;

  const scalePoint = useCallback(
    (coords: [number, number] | null, normalized?: boolean | null) => {
      if (!coords || !imageRef.current) {
        return null;
      }
      const img = imageRef.current;
      const naturalWidth = img.naturalWidth || img.width;
      const naturalHeight = img.naturalHeight || img.height;
      const containerWidth = img.clientWidth || img.width;
      const containerHeight = img.clientHeight || img.height;

      if (!naturalWidth || !naturalHeight || !containerWidth || !containerHeight) {
        return null;
      }

      const useNormalized =
        typeof normalized === "boolean" ? normalized : coordinatesNormalized;
      const denomX = useNormalized ? 1000 : naturalWidth;
      const denomY = useNormalized ? 1000 : naturalHeight;
      const ratioX = Math.max(0, Math.min(1, coords[0] / denomX));
      const ratioY = Math.max(0, Math.min(1, coords[1] / denomY));

      // The <img> uses object-fit: contain, so the actual drawn image may be
      // letterboxed inside the element. Compute the rendered size and offsets
      // so we map coordinates into the true image content, not the empty bars.
      const scale = Math.min(
        containerWidth / naturalWidth,
        containerHeight / naturalHeight
      );
      const renderedWidth = naturalWidth * scale;
      const renderedHeight = naturalHeight * scale;
      const offsetX = (containerWidth - renderedWidth) / 2;
      const offsetY = (containerHeight - renderedHeight) / 2;

      return {
        x: offsetX + ratioX * renderedWidth,
        y: offsetY + ratioY * renderedHeight,
      };
    },
    [coordinatesNormalized]
  );

  const updateScaledPoints = useCallback(() => {
    setScaledCoords(scalePoint(pointerCoords, pointerCoordsNormalized));
    setScaledTargetCoords(scalePoint(targetCoords, targetCoordsNormalized));
    setScaledScrollStart(scalePoint(scrollStartCoords, scrollStartNormalized));
    setScaledScrollEnd(scalePoint(scrollEndCoords, scrollEndNormalized));
  }, [
    scalePoint,
    pointerCoords,
    pointerCoordsNormalized,
    targetCoords,
    targetCoordsNormalized,
    scrollStartCoords,
    scrollStartNormalized,
    scrollEndCoords,
    scrollEndNormalized,
  ]);

  const handleImageLoad = useCallback(() => {
    updateScaledPoints();
  }, [updateScaledPoints]);

  useEffect(() => {
    // Reset to "before" view when action changes
    setScreenshotView("before");
  }, [currentAction?.id]);

  useEffect(() => {
    updateScaledPoints();
  }, [updateScaledPoints]);

  useEffect(() => {
    const handleResize = () => updateScaledPoints();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [updateScaledPoints]);

  // Recompute scaled points whenever the rendered image element itself resizes.
  // This covers layout changes in the split pane during live mode (even when the
  // window size is unchanged), keeping the pointer/scroll overlays aligned.
  useEffect(() => {
    const img = imageRef.current;
    if (!img || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(() => {
      updateScaledPoints();
    });
    observer.observe(img);
    return () => {
      observer.disconnect();
    };
  }, [updateScaledPoints]);

  const actionNameKey = currentAction?.action_name || currentAction?.action_type || "";
  // Treat as a "drag" overlay only when we have a full path (start + end).
  // If there's just a single coordinate (e.g. failed/partial left_click_drag), we still show the pointer.
  const isDragAction = !!dragPath;
  const pointerEligible =
    !!pointerCoords &&
    (POINTER_ACTION_NAMES.has(actionNameKey) ||
      POINTER_ACTION_NAMES.has(currentAction?.action_type || ""));
  const shouldShowPointerIndicator =
    showClickIndicator &&
    pointerEligible &&
    scaledCoords &&
    !isDragAction &&
    currentAction?.action_type !== "scroll" &&
    currentAction?.action_type !== "type" &&
    (!hasBeforeAfter || screenshotView === "before");

  const scrollAxis =
    typeof metadata.scroll_axis === "string" ? (metadata.scroll_axis as string) : "vertical";
  let scrollLineMetrics: ScrollLineMetrics | null = null;
  if (
    currentAction?.action_type === "scroll" &&
    scaledScrollStart &&
    scaledScrollEnd
  ) {
    if (!imageRef.current) {
      scrollLineMetrics = null;
    } else if (scrollAxis === "horizontal") {
      const img = imageRef.current;
      const w = img.clientWidth || img.width || 0;
      const y = Math.max(0, Math.min(w, scaledScrollStart.y));
      const startX = Math.max(0, Math.min(w, scaledScrollStart.x));
      const endX = Math.max(0, Math.min(w, scaledScrollEnd.x));
      const left = Math.min(startX, endX);
      const length = Math.max(8, Math.abs(endX - startX));
      scrollLineMetrics = {
        top: y,
        left,
        length,
        isHorizontal: true,
        startPoint: { x: startX, y },
        endPoint: { x: endX, y },
      };
    } else {
      const img = imageRef.current;
      const h = img.clientHeight || img.height || 0;
      const x = Math.max(0, Math.min(img.clientWidth || img.width || 0, scaledScrollStart.x));
      const startY = Math.max(0, Math.min(h, scaledScrollStart.y));
      const endY = Math.max(0, Math.min(h, scaledScrollEnd.y));
      const top = Math.min(startY, endY);
      const length = Math.max(8, Math.abs(endY - startY));
      scrollLineMetrics = {
        top,
        left: x,
        length,
        isHorizontal: false,
        startPoint: { x, y: startY },
        endPoint: { x, y: endY },
      };
    }
  }

  const scrollLabelText = [
    scrollDirection ? scrollDirection.toUpperCase() : "SCROLL",
    scrollDistanceLabel ? `(${scrollDistanceLabel})` : null,
  ]
    .filter(Boolean)
    .join(" ");

  const scrollFooterLabel =
    currentAction?.action_type === "scroll"
      ? scrollDirection
        ? scrollDistanceLabel
          ? `${scrollDirection.toUpperCase()} ${scrollDistanceLabel}`
          : scrollDirection.toUpperCase()
        : scrollDistanceLabel
      : null;

  const dragMetrics =
    dragPath && scaledCoords && scaledTargetCoords
      ? {
          length: Math.sqrt(
            (scaledTargetCoords.x - scaledCoords.x) ** 2 +
              (scaledTargetCoords.y - scaledCoords.y) ** 2
          ),
          angle:
            (Math.atan2(
              scaledTargetCoords.y - scaledCoords.y,
              scaledTargetCoords.x - scaledCoords.x
            ) *
              180) /
            Math.PI,
        }
      : null;

  useEffect(() => {
    if (!currentAction) {
      setImageUrl(null);
      return;
    }

    // Determine which screenshot to show
    let screenshotPath: string | undefined;
    
    if (hasBeforeAfter) {
      // Use before/after screenshots based on toggle (visible effect actions)
      screenshotPath = screenshotView === "before" 
        ? currentAction.screenshot_before 
        : currentAction.screenshot_after;
    } else if (hasSingleScreenshot) {
      // Use single screenshot_after (non-visible actions like screenshot, wait)
      screenshotPath = currentAction.screenshot_after;
    } else if (hasLegacyScreenshot) {
      // Fall back to legacy screenshot_path
      screenshotPath = currentAction.screenshot_path;
    }

    if (!screenshotPath) {
      setImageUrl(null);
      return;
    }

    setIsLoading(true);
    setImageError(false);

    // Import timelineApi dynamically
    const requestedVariant: ScreenshotView = hasBeforeAfter ? screenshotView : "after";

    import("../services/api").then(({ timelineApi }) => {
      const url = timelineApi.getScreenshotUrl(
        executionId,
        iterationId,
        currentAction.id,
        requestedVariant
      );
      setImageUrl(url);
      setIsLoading(false);
    });
  }, [currentAction, executionId, iterationId, screenshotView, hasBeforeAfter, hasLegacyScreenshot, hasSingleScreenshot]);

  const currentUrl = currentAction?.current_url || "";

  // Check if this is a list_tabs action
  const isListTabsAction = currentAction?.action_name === "list_tabs";
  const tabInfo = isListTabsAction && currentAction?.metadata
    ? (currentAction.metadata as any)
    : null;
  const tabs = tabInfo?.tabs || tabInfo?.tab_info?.tabs || [];
  const tabCount = tabInfo?.tab_count || tabInfo?.tab_info?.tab_count;
  const currentTabIndex = tabInfo?.current_tab_index ?? tabInfo?.tab_info?.current_tab_index;

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        bgcolor: theme.palette.background.paper,
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 1,
        overflow: "hidden",
      }}
    >
      {/* Simple URL Bar */}
      <Box
        sx={{
          px: 2,
          py: 1,
          bgcolor: theme.palette.background.paper,
          borderBottom: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Typography
          variant="body2"
          sx={{
            fontSize: 14,
            color: theme.palette.text.primary,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            fontFamily: "monospace",
          }}
        >
          {currentUrl || "about:blank"}
        </Typography>
      </Box>

      {/* Screenshot Content Area */}
      <Box
        sx={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          bgcolor: theme.palette.mode === "dark" ? "#121212" : "#ffffff",
          position: "relative",
          overflow: "auto",
        }}
      >
        {/* Show TabGridView for list_tabs actions */}
        {isListTabsAction ? (
          <Box sx={{ width: "100%", height: "100%", p: 2, overflow: "auto" }}>
            <TabGridView
              tabs={tabs}
              tabCount={tabCount}
              currentTabIndex={currentTabIndex}
            />
          </Box>
        ) : isLoading ? (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
            <CircularProgress />
            <Typography variant="body2" color="text.secondary">
              Loading screenshot...
            </Typography>
          </Box>
        ) : imageError || !imageUrl ? (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
            <Typography variant="h6" color="text.secondary">
              {currentAction ? "Screenshot unavailable" : "Select an action to view"}
            </Typography>
            <Typography variant="body2" color="text.disabled">
              {currentAction
                ? "The screenshot for this action could not be loaded"
                : "Click on an action in the timeline to see its screenshot"}
            </Typography>
          </Box>
        ) : (
          <Box
            sx={{
              position: "relative",
              width: "100%",
              height: "100%",
              display: "inline-block",
            }}
          >
            <Box
              ref={imageRef}
              component="img"
              src={imageUrl}
              alt={currentAction?.action_name || "Screenshot"}
              onError={() => setImageError(true)}
              onLoad={handleImageLoad}
              sx={{
                width: "100%",
                height: "100%",
                objectFit: "contain",
                display: "block",
                transition: "opacity 0.3s ease-in-out",
                opacity: isLoading ? 0.5 : 1,
              }}
            />

            {/* Pointer Indicator Overlay - show for coordinate-based actions */}
            {shouldShowPointerIndicator && pointerCoords && scaledCoords && (
              <>
                {/* Pulsing ring */}
                <Box
                  sx={{
                    position: "absolute",
                    left: `${scaledCoords.x}px`,
                    top: `${scaledCoords.y}px`,
                    transform: "translate(-50%, -50%)",
                    width: 40,
                    height: 40,
                    borderRadius: "50%",
                    border: `3px solid ${theme.palette.error.main}`,
                    boxShadow: `0 0 0 8px rgba(255, 0, 0, 0.2)`,
                    animation: "pulse 1.5s infinite",
                    pointerEvents: "none",
                    zIndex: 10,
                    "@keyframes pulse": {
                      "0%": { transform: "translate(-50%, -50%) scale(0.8)", opacity: 1 },
                      "50%": { transform: "translate(-50%, -50%) scale(1.2)", opacity: 0.6 },
                      "100%": { transform: "translate(-50%, -50%) scale(0.8)", opacity: 1 },
                    },
                  }}
                />
                {/* Cursor icon */}
                <Box
                  sx={{
                    position: "absolute",
                    left: `${scaledCoords.x}px`,
                    top: `${scaledCoords.y}px`,
                    transform: "translate(-20%, -20%)",
                    pointerEvents: "none",
                    zIndex: 11,
                    filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.5))",
                  }}
                >
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M3 3L10.5 20.5L13.5 13.5L20.5 10.5L3 3Z"
                      fill="#FFFFFF"
                      stroke="#000000"
                      strokeWidth="1.5"
                    />
                  </svg>
                </Box>
                {/* Coordinate label - Show original coordinates */}
                <Box
                  sx={{
                    position: "absolute",
                    left: `${scaledCoords.x + 30}px`,
                    top: `${scaledCoords.y - 30}px`,
                    bgcolor: theme.palette.error.main,
                    color: "#fff",
                    px: 1,
                    py: 0.5,
                    borderRadius: 1,
                    fontSize: "11px",
                    fontFamily: "monospace",
                    fontWeight: "bold",
                    pointerEvents: "none",
                    zIndex: 11,
                    boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                  }}
                >
                  {`(${pointerCoords[0]}, ${pointerCoords[1]})`}
                </Box>
              </>
            )}

            {/* Drag Path Indicator */}
            {dragMetrics &&
              scaledCoords &&
              scaledTargetCoords &&
              (!hasBeforeAfter || screenshotView === "before") && (
                <>
                  <Box
                    sx={{
                      position: "absolute",
                      left: `${scaledCoords.x}px`,
                      top: `${scaledCoords.y}px`,
                      width: `${dragMetrics.length}px`,
                      height: "4px",
                      bgcolor: theme.palette.success.main,
                      transformOrigin: "0 50%",
                      transform: `translate(-0%, -50%) rotate(${dragMetrics.angle}deg)`,
                      boxShadow: "0 0 10px rgba(0,0,0,0.3)",
                      zIndex: 9,
                    }}
                  />
                  {/* Arrow head */}
                  <Box
                    sx={{
                      position: "absolute",
                      left: `${scaledTargetCoords.x}px`,
                      top: `${scaledTargetCoords.y}px`,
                      width: 0,
                      height: 0,
                      borderLeft: "8px solid transparent",
                      borderRight: "8px solid transparent",
                      borderTop: `12px solid ${theme.palette.success.main}`,
                      // Flip arrow orientation to point from start -> end along the drag line
                      transform: `translate(-50%, -50%) rotate(${dragMetrics.angle - 90}deg)`,
                      zIndex: 10,
                    }}
                  />
                  <Box
                    sx={{
                      position: "absolute",
                      left: `${(scaledCoords.x + scaledTargetCoords.x) / 2}px`,
                      top: `${(scaledCoords.y + scaledTargetCoords.y) / 2 - 20}px`,
                      transform: "translate(-50%, -50%)",
                      bgcolor: theme.palette.success.main,
                      color: theme.palette.getContrastText(theme.palette.success.main),
                      px: 1.5,
                      py: 0.5,
                      borderRadius: 1,
                      fontSize: "12px",
                      fontFamily: "monospace",
                      boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                      zIndex: 11,
                    }}
                  >
                    Drag to {targetCoords ? `(${targetCoords[0]}, ${targetCoords[1]})` : "target"}
                  </Box>
                </>
              )}

            {/* Type Indicator - Show input cursor/field highlight */}
            {currentAction?.action_type === "type" && screenshotView === "before" && (
              <>
                {scaledCoords ? (
                  <>
                    {/* ✅ CASE 1: We know WHERE text is typed - show at specific location */}
                    {/* Blinking cursor indicator */}
                    <Box
                      sx={{
                        position: "absolute",
                        left: `${scaledCoords.x}px`,
                        top: `${scaledCoords.y}px`,
                        transform: "translate(-50%, -50%)",
                        width: 2,
                        height: 24,
                        bgcolor: theme.palette.info.main,
                        animation: "blink 1s infinite",
                        "@keyframes blink": {
                          "0%, 49%": { opacity: 1 },
                          "50%, 100%": { opacity: 0 },
                        },
                        zIndex: 10,
                      }}
                    />
                    {/* Text preview label at specific location */}
                    {currentAction.metadata?.text && (
                      <Box
                        sx={{
                          position: "absolute",
                          left: `${scaledCoords.x + 20}px`,
                          top: `${scaledCoords.y - 30}px`,
                          bgcolor: theme.palette.info.main,
                          color: "#fff",
                          px: 1.5,
                          py: 0.5,
                          borderRadius: 1,
                          fontSize: "12px",
                          fontFamily: "monospace",
                          maxWidth: "200px",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          zIndex: 11,
                          boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                        }}
                      >
                        ⌨️ "{(currentAction.metadata.text as string).slice(0, 20)}{(currentAction.metadata.text as string).length > 20 ? "..." : ""}"
                      </Box>
                    )}
                  </>
                ) : (
                  <>
                    {/* ✅ CASE 2: We DON'T know where - show text at TOP of screen */}
                    {currentAction.metadata?.text && (
                      <Box
                        sx={{
                          position: "absolute",
                          top: "20px",
                          left: "50%",
                          transform: "translateX(-50%)",
                          bgcolor: theme.palette.info.main,
                          color: "#fff",
                          px: 2.5,
                          py: 1.5,
                          borderRadius: 2,
                          fontSize: "14px",
                          fontFamily: "monospace",
                          fontWeight: "bold",
                          maxWidth: "80%",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          zIndex: 11,
                          boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
                          display: "flex",
                          alignItems: "center",
                          gap: 1,
                        }}
                      >
                        <Box
                          component="span"
                          sx={{
                            width: 2,
                            height: 18,
                            bgcolor: "#fff",
                            animation: "blink 1s infinite",
                          }}
                        />
                        Typing: "{(currentAction.metadata.text as string).slice(0, 50)}{(currentAction.metadata.text as string).length > 50 ? "..." : ""}"
                      </Box>
                    )}
                  </>
                )}
              </>
            )}

            {/* Scroll Indicator - show measured path */}
            {currentAction?.action_type === "scroll" && screenshotView === "before" && imageRef.current && (
              <>
                {scrollLineMetrics ? (
                  <>
                    {/* Animated scroll path between start and end */}
                    <Box
                      sx={{
                        position: "absolute",
                        left: scrollLineMetrics.isHorizontal
                          ? `${scrollLineMetrics.left}px`
                          : `${scrollLineMetrics.left}px`,
                        top: scrollLineMetrics.isHorizontal
                          ? `${scrollLineMetrics.top}px`
                          : `${scrollLineMetrics.top}px`,
                        width: scrollLineMetrics.isHorizontal
                          ? `${scrollLineMetrics.length}px`
                          : "4px",
                        height: scrollLineMetrics.isHorizontal
                          ? "4px"
                          : `${scrollLineMetrics.length}px`,
                        transform: scrollLineMetrics.isHorizontal
                          ? "translateY(-50%)"
                          : "translateX(-50%)",
                        bgcolor: theme.palette.warning.main,
                        borderRadius: 2,
                        zIndex: 10,
                        boxShadow: "0 0 10px rgba(255,152,0,0.5)",
                        overflow: "hidden",
                        "&::after": {
                          content: '""',
                          position: "absolute",
                          left: 0,
                          top: 0,
                          width: "100%",
                          height: "100%",
                          background:
                            scrollAxis === "vertical"
                              ? "linear-gradient(to bottom, rgba(255,255,255,0.0) 0%, rgba(255,255,255,0.6) 50%, rgba(255,255,255,0.0) 100%)"
                              : "linear-gradient(to right, rgba(255,255,255,0.0) 0%, rgba(255,255,255,0.6) 50%, rgba(255,255,255,0.0) 100%)",
                          animation: "scrollPulse 1.4s infinite",
                        },
                        "@keyframes scrollPulse": {
                          "0%": {
                            opacity: 0,
                            transform: scrollAxis === "vertical"
                              ? "translateY(-50%)"
                              : "translateX(-50%)",
                          },
                          "40%": {
                            opacity: 1,
                            transform: "translate(0, 0)",
                          },
                          "100%": {
                            opacity: 0,
                            transform: scrollAxis === "vertical"
                              ? "translateY(50%)"
                              : "translateX(50%)",
                          },
                        },
                      }}
                    />
                    {/* Start marker (circle) */}
                    <Box
                      sx={{
                        position: "absolute",
                        left: `${scrollLineMetrics.startPoint.x}px`,
                        top: `${scrollLineMetrics.startPoint.y}px`,
                        width: 14,
                        height: 14,
                        borderRadius: "50%",
                        bgcolor: theme.palette.warning.main,
                        transform: "translate(-50%, -50%)",
                        border: "2px solid #fff",
                        boxShadow: "0 2px 6px rgba(0,0,0,0.4)",
                        zIndex: 11,
                      }}
                    />
                    {/* End marker (arrow in scroll direction) */}
                    {(() => {
                      const end = scrollLineMetrics.endPoint;
                      const isVertical = scrollAxis === "vertical";
                      // Prefer explicit scrollDirection; otherwise infer from geometry
                      let dir: "up" | "down" | "left" | "right";
                      // Prefer explicit vertical direction when provided; otherwise infer from geometry.
                      if (scrollDirection === "up" || scrollDirection === "down") {
                        dir = scrollDirection as "up" | "down";
                      } else if (isVertical) {
                        dir = end.y >= scrollLineMetrics.startPoint.y ? "down" : "up";
                      } else {
                        dir = end.x >= scrollLineMetrics.startPoint.x ? "right" : "left";
                      }

                      const common = {
                        position: "absolute" as const,
                        left: `${end.x}px`,
                        top: `${end.y}px`,
                        width: 0,
                        height: 0,
                        transform: "translate(-50%, -50%)",
                        zIndex: 12,
                      };

                      if (isVertical) {
                        const pointingDown = dir === "down";
                        return (
                          <Box
                            sx={{
                              ...common,
                              borderLeft: "8px solid transparent",
                              borderRight: "8px solid transparent",
                              borderTop: pointingDown ? `12px solid ${theme.palette.warning.main}` : "none",
                              borderBottom: !pointingDown ? `12px solid ${theme.palette.warning.main}` : "none",
                            }}
                          />
                        );
                      } else {
                        const pointingRight = dir === "right";
                        return (
                          <Box
                            sx={{
                              ...common,
                              borderTop: "8px solid transparent",
                              borderBottom: "8px solid transparent",
                              borderLeft: !pointingRight ? `12px solid ${theme.palette.warning.main}` : "none",
                              borderRight: pointingRight ? `12px solid ${theme.palette.warning.main}` : "none",
                            }}
                          />
                        );
                      }
                    })()}
                    <Box
                      sx={{
                        position: "absolute",
                        left: scrollLineMetrics.isHorizontal
                          ? `${(scrollLineMetrics.startPoint.x + scrollLineMetrics.endPoint.x) / 2}px`
                          : `${scrollLineMetrics.left + 30}px`,
                        top: scrollLineMetrics.isHorizontal
                          ? `${scrollLineMetrics.top - 30}px`
                          : `${(scrollLineMetrics.startPoint.y + scrollLineMetrics.endPoint.y) / 2}px`,
                        transform: "translate(-50%, -50%)",
                        bgcolor: theme.palette.warning.main,
                        color: "#fff",
                        px: 2,
                        py: 0.75,
                        borderRadius: 2,
                        fontSize: "12px",
                        fontWeight: "bold",
                        display: "flex",
                        alignItems: "center",
                        gap: 0.5,
                        zIndex: 12,
                        boxShadow: "0 2px 10px rgba(0,0,0,0.4)",
                        textTransform: "uppercase",
                      }}
                    >
                      {scrollLabelText || "SCROLL"}
                    </Box>
                  </>
            ) : (
              <>
                {/* Fallback when we only know direction (e.g. Gemini scroll_document) */}
                {imageRef.current && scrollDirection && (() => {
                  const img = imageRef.current;
                  const centerX = img.clientWidth / 2;
                  const centerY = img.clientHeight / 2;
                  const offset = Math.min(img.clientHeight * 0.2, 80);
                  const startY = scrollDirection === "up" ? centerY + offset : centerY - offset;
                  const endY = scrollDirection === "up" ? centerY - offset : centerY + offset;
                  return (
                    <>
                      <Box
                        sx={{
                          position: "absolute",
                          left: `${centerX}px`,
                          top: `${Math.min(startY, endY)}px`,
                          width: "4px",
                          height: `${Math.abs(endY - startY)}px`,
                          transform: "translateX(-50%)",
                          bgcolor: theme.palette.warning.main,
                          borderRadius: 2,
                          zIndex: 10,
                          boxShadow: "0 0 10px rgba(255,152,0,0.5)",
                        }}
                      />
                      {/* Arrow head */}
                      <Box
                        sx={{
                          position: "absolute",
                          left: `${centerX}px`,
                          top: `${endY}px`,
                          width: 0,
                          height: 0,
                          borderLeft: "8px solid transparent",
                          borderRight: "8px solid transparent",
                          // ✅ FIX: Invert arrowhead for Gemini
                          // - scroll_document is Gemini-only
                          // - scroll_at with normalized coordinates is Gemini
                          borderTop:
                            (currentAction?.action_name === "scroll_document" || 
                             (currentAction?.action_name === "scroll_at" && coordinatesNormalized))
                              ? (scrollDirection === "down" ? `12px solid ${theme.palette.warning.main}` : "none")
                              : (scrollDirection === "up" ? `12px solid ${theme.palette.warning.main}` : "none"),
                          borderBottom:
                            (currentAction?.action_name === "scroll_document" || 
                             (currentAction?.action_name === "scroll_at" && coordinatesNormalized))
                              ? (scrollDirection === "up" ? `12px solid ${theme.palette.warning.main}` : "none")
                              : (scrollDirection === "down" ? `12px solid ${theme.palette.warning.main}` : "none"),
                          transform: "translate(-50%, -50%)",
                          zIndex: 11,
                        }}
                      />
                      <Box
                        sx={{
                          position: "absolute",
                          left: `${centerX}px`,
                          top: `${startY - 20}px`,
                          transform: "translate(-50%, -50%)",
                          bgcolor: theme.palette.warning.main,
                          color: "#fff",
                          px: 2,
                          py: 0.5,
                          borderRadius: 2,
                          fontSize: "12px",
                          fontWeight: "bold",
                          boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                          zIndex: 12,
                          textTransform: "uppercase",
                        }}
                      >
                        {scrollLabelText || scrollDirection.toUpperCase()}
                      </Box>
                    </>
                  );
                })()}
              </>
            )}
              </>
            )}
          </Box>
        )}
      </Box>

      {/* Action Details Footer with Before/After Toggle */}
      {currentAction && (
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            px: 2,
            py: 1.5,
            bgcolor: theme.palette.mode === "dark" ? "#1e1e1e" : "#f5f5f5",
            borderTop: `1px solid ${theme.palette.divider}`,
            gap: 1,
            maxHeight: "35%",
            overflowY: "auto",
          }}
        >
          {/* Top Row: Action name and metadata */}
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 1 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
              <Typography variant="body2" fontWeight="medium">
                {currentAction.action_name}
              </Typography>
              
              {/* Show coordinate metadata if available */}
              {pointerCoords ? (
                <Chip
                  label={`Coords (${pointerCoords[0]}, ${pointerCoords[1]})`}
                  size="small"
                  color="primary"
                  sx={{ height: 24, fontSize: 11, fontFamily: "monospace" }}
                />
              ) : null}

              {targetCoords ? (
                <Chip
                  label={`Target (${targetCoords[0]}, ${targetCoords[1]})`}
                  size="small"
                  color="success"
                  sx={{ height: 24, fontSize: 11, fontFamily: "monospace" }}
                />
              ) : null}

              {scrollFooterLabel && currentAction.action_type === "scroll" ? (
                <Chip
                  label={`Scroll ${scrollFooterLabel}`}
                  size="small"
                  color="warning"
                  sx={{ height: 24, fontSize: 11 }}
                />
              ) : null}
              
              {/* Show typed text if available */}
              {currentAction.action_type === "type" && currentAction.metadata?.text && typeof currentAction.metadata.text === 'string' ? (
                <Chip
                  label={`Text: "${String(currentAction.metadata.text).substring(0, 30)}${String(currentAction.metadata.text).length > 30 ? '...' : ''}"`}
                  size="small"
                  color="secondary"
                  sx={{ height: 24, fontSize: 11, maxWidth: 300 }}
                />
              ) : null}
              
              {/* Show key press if available */}
              {currentAction.action_type === "key_press" && currentAction.metadata?.key ? (
                <Chip
                  label={`Key: ${Array.isArray(currentAction.metadata.key) 
                    ? currentAction.metadata.key.join('+') 
                    : String(currentAction.metadata.key)}`}
                  size="small"
                  color="info"
                  sx={{ height: 24, fontSize: 11 }}
                />
              ) : null}
              
              {/* Before/After Toggle */}
              {hasBeforeAfter && (
                <ToggleButtonGroup
                  value={screenshotView}
                  exclusive
                  onChange={(_, newView) => {
                    if (newView !== null) {
                      setScreenshotView(newView);
                    }
                  }}
                  size="small"
                  sx={{ height: 28 }}
                >
                  <ToggleButton value="before" sx={{ px: 2, py: 0.5 }}>
                    <VisibilityOff sx={{ fontSize: 16, mr: 0.5 }} />
                    <Typography variant="caption" fontWeight="medium">
                      Before
                    </Typography>
                  </ToggleButton>
                  <ToggleButton value="after" sx={{ px: 2, py: 0.5 }}>
                    <Visibility sx={{ fontSize: 16, mr: 0.5 }} />
                    <Typography variant="caption" fontWeight="medium">
                      After
                    </Typography>
                  </ToggleButton>
                </ToggleButtonGroup>
              )}
              
              {/* Indicator for what's being shown */}
              {hasBeforeAfter && (
                <Chip
                  label={screenshotView === "before" ? "What will be performed" : "What was performed"}
                  size="small"
                  color={screenshotView === "before" ? "warning" : "info"}
                  sx={{ height: 24, fontSize: 11 }}
                />
              )}
            </Box>
            
            <Box sx={{ display: "flex", gap: 2, alignItems: "center" }}>
              <Typography variant="caption" color="text.secondary">
                {new Date(currentAction.timestamp).toLocaleTimeString()}
              </Typography>
              <Box
                sx={{
                  px: 1,
                  py: 0.25,
                  borderRadius: 1,
                  bgcolor:
                    currentAction.status === "success"
                      ? theme.palette.success.main
                      : currentAction.status === "failed"
                      ? theme.palette.error.main
                      : theme.palette.warning.main,
                  color: "#fff",
                }}
              >
                <Typography variant="caption" fontWeight="medium">
                  {currentAction.status?.toUpperCase() || "PENDING"}
                </Typography>
              </Box>
            </Box>
          </Box>
          
        </Box>
      )}
    </Box>
  );
}
