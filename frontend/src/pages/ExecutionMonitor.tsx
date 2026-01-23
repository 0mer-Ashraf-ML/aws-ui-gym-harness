import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Box,
  Typography,
  IconButton,
  Chip,
  Paper,
  Fab,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Alert,
  CircularProgress,
  Tabs,
  Tab,
  Tooltip,
  useTheme,
  ToggleButtonGroup,
  ToggleButton,
  Link,
  Skeleton,
} from "@mui/material";
import {
  ArrowBack as BackIcon,
  CloudDownload as CloudDownloadIcon,
  Close as CloseIcon,
  Monitor as MonitorIcon,
  Speed as SpeedIcon,
  Refresh as RefreshIcon,
  Terminal as TerminalIcon,
  OpenInFull as FullScreenIcon,
  CloseFullscreen as ExitFullScreenIcon,
  DragIndicator as DragIcon,
  KeyboardArrowUp as KeyboardArrowUpIcon,
  KeyboardArrowDown as KeyboardArrowDownIcon,
  Assignment as AssignmentIcon,
} from "@mui/icons-material";
import { useExecutionFilesRealtime,
  useDriveStructure,
  useFileSelection,
  useFileDownload,
  useExecutionSummary,
} from "../hooks/useExecutionFiles";
import { useExecutionProgress } from "../hooks/useExecutionProgress";
import { useRun } from "../hooks/useRuns";
import { useGyms } from "../hooks/useGyms";
import { useTasks } from "../hooks/useTasks";
import { useTimeline } from "../hooks/useTimeline";
import { fileApi, timelineApi, getAuthToken } from "../services/api";
import ExecutionInsights from "../components/ExecutionInsights";
import { useSorting, type SortOption } from "../hooks/useSorting";
import { useFiltering, type FilterCategory } from "../hooks/useFiltering";
import { getStatusColor } from "../utils/sharedStyles";
import { getStatusDisplayLabel } from "../utils/runUtils";
import EmptyState from "../components/EmptyState";
import ExecutionOverallSummary from "../components/ExecutionOverallSummary";
import IterationCard from "../components/IterationCard";
import {
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
} from "@mui/icons-material";
import type { ExecutionFile } from "../types";
import {
  getAllScreenshots,
  getScreenshotNavigation,
  parseScreenshotMetadata,
  buildScreenshotActionIndex,
  findActionForScreenshot,
  getRelativeTimeLabel,
  ACTION_METADATA_LABELS,
  formatMetadataValue,
} from "../utils/screenshotUtils";
import {
  ArrowBack as ArrowBackIcon,
  ArrowForward as ArrowForwardIcon,
  ContentCopy as ContentCopyIcon,
  OpenInNew as OpenInNewIcon,
  Keyboard as KeyboardIcon,
} from "@mui/icons-material";
import { useDownloadQueue } from "../hooks/useDownloadQueue";
import { useSnackbar } from "../hooks/useSnackbar";

// Constants
const SIDEBAR_WIDTH = 240; // Must match Layout.tsx drawerWidth

export default function ExecutionMonitor() {
  const { executionId, batchId } = useParams<{ executionId: string; batchId?: string }>();
  const navigate = useNavigate();
  const theme = useTheme();

  // State management
  const [tabValue, setTabValue] = useState(0);
  const [previewFile, setPreviewFile] = useState<ExecutionFile | null>(null);
  const [jsonContent, setJsonContent] = useState<string>("");
  const [isLoadingJson, setIsLoadingJson] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);
  
  // Screenshot image loading and error states
  const [isImageLoading, setIsImageLoading] = useState(true);
  const [imageError, setImageError] = useState(false);

  // Iteration tracking state (used for log viewer context)
  const [currentIteration, setCurrentIteration] = useState<string | null>(null);
  const [availableIterations, setAvailableIterations] = useState<string[]>([]);

  // Download queue and notifications
  const { addDownload, downloads } = useDownloadQueue();
  const { showSuccess, showError, showInfo } = useSnackbar();

  const [isManualRefreshing] = useState(false);
  const [logViewerContent, setLogViewerContent] = useState<string>("");
  const [logViewerOpen, setLogViewerOpen] = useState(false);

  // Log panel state
  const [logPanelOpen, setLogPanelOpen] = useState(false);
  const [logPanelHeight, setLogPanelHeight] = useState(300);
  const [isLogFullScreen, setIsLogFullScreen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  // Log content visibility (default to showing full content)
  const [showLogContent, setShowLogContent] = useState(true);
  // Removed: Per-task open state (no longer using accordion)
  const [dragStartY, setDragStartY] = useState(0);
  const [dragStartHeight, setDragStartHeight] = useState(0);
  const [currentLogFile, setCurrentLogFile] = useState<ExecutionFile | null>(
    null,
  );
  const [isStreamingLogs, setIsStreamingLogs] = useState(false);

  // Refs for log viewer auto-scroll and panel
  const logContainerRef = useRef<HTMLDivElement>(null);
  const logPanelRef = useRef<HTMLDivElement>(null);
  const previousContentRef = useRef<string>("");

  // Data fetching hooks - get execution data first
  const {
    data: currentExecution,
    error: currentExecutionError,
    isLoading: currentExecutionLoading,
  } = useRun(executionId || "", {
    enableRealTimeSync: true,
  });

  const {
    data: filesData,
    isSyncing,
  } = useExecutionFilesRealtime(
    executionId,
    "hierarchical",
    currentExecution?.status,
    {
      // Use defaults for live syncing of all files
    },
  );

  const { data: summaryData, isLoading: summaryLoading } =
    useExecutionSummary(executionId);

  // Handle back navigation with context awareness
  const handleBackNavigation = useCallback(() => {
    // First check URL params for batch context (most reliable)
    if (batchId) {
      navigate(`/batches/${batchId}/runs`);
    } else if (currentExecution?.batch_id) {
      // Fallback: check if execution is part of a batch
      navigate(`/batches/${currentExecution.batch_id}/runs`);
    } else {
      // Otherwise, go back to runs page
      navigate('/runs');
    }
  }, [navigate, batchId, currentExecution]);

  // Per-iteration progress (poll only during active executions)
  const isExecutionActive =
    currentExecution?.status === "pending" ||
    currentExecution?.status === "executing";

  const { data: progressData, refetch: refetchProgress } = useExecutionProgress(executionId, {
    // Always enable to show iteration statuses even after completion.
    enabled: !!executionId,
    // Poll during active runs and for 10 seconds after completion to catch final updates
    refetchIntervalMs: isExecutionActive ? 5000 : undefined,
  });

  // Force refetch when execution status changes to ensure we get final state
  useEffect(() => {
    if (currentExecution && !isExecutionActive) {
      // Execution just completed, force a final refetch
      refetchProgress();
    }
  }, [currentExecution?.status, isExecutionActive, refetchProgress]);

  // Initialize currentIteration when progress data arrives (latest iteration)
  useEffect(() => {
    if (!progressData) return;
    if (!currentIteration && progressData.iterations.length > 0) {
      const latest = `iteration_${Math.max(
        ...progressData.iterations.map((i) => i.iteration_number),
      )}`;
      setCurrentIteration(latest);
    }
  }, [progressData, currentIteration]);

  // Fallback: if no progressData (e.g., execution finished), initialize from availableIterations
  useEffect(() => {
    if (progressData) return; // handled above
    if (!currentIteration && availableIterations.length > 0) {
      const latest = availableIterations[availableIterations.length - 1];
      setCurrentIteration(latest);
    }
  }, [progressData, availableIterations, currentIteration]);

  // Track processed download IDs to avoid duplicate notifications
  const processedDownloads = useRef<Set<string>>(new Set());

  // Monitor download status changes for notifications
  useEffect(() => {
    downloads.forEach((download) => {
      // Only show notification once per download status change
      const statusKey = `${download.id}-${download.status}`;
      if (processedDownloads.current.has(statusKey)) {
        return;
      }

      if (download.type === 'execution' && download.url.includes(executionId || '')) {
        if (download.status === 'completed') {
          processedDownloads.current.add(statusKey);
          showSuccess(`Download complete: ${download.filename}`);
        } else if (download.status === 'failed') {
          processedDownloads.current.add(statusKey);
          showError(`Download failed: ${download.error || 'Unknown error'}`);
        }
      }
    });
  }, [downloads, executionId, showSuccess, showError, showInfo]);

  // Fetch gym and task data for context
  const { data: gyms } = useGyms();
  const { data: tasks } = useTasks();

  // Get current gym and task info
  const currentGym = gyms?.find((gym) => gym.uuid === currentExecution?.gym_id);
  const currentTask = tasks?.find(
    (task) => task.task_id === (currentExecution?.task_identifier || currentExecution?.task_id),
  );

  // Drive structure and navigation
  const {
    getCurrentItems,
  } = useDriveStructure(filesData);

  // File operations
  const { selectedFiles, clearSelection, selectedCount } =
    useFileSelection();

  const {
    downloadFile,
    downloadMultipleFiles,
  } = useFileDownload();


  // Helper function to get log files for a specific iteration
  const getLogFilesForIteration = useCallback(
    (iteration: string | null): ExecutionFile[] => {
      if (!filesData) return [];

      // Handle hierarchical format
      if (filesData.structure) {
        if (!iteration) {
          // Return all log files from all iterations
          const allLogs: ExecutionFile[] = [];
          Object.values(filesData.structure).forEach(
            (iterationData: {
              logs?: ExecutionFile[];
              [category: string]: ExecutionFile[] | undefined;
            }) => {
              if (iterationData.logs && Array.isArray(iterationData.logs)) {
                allLogs.push(...iterationData.logs);
              }
            },
          );
          return allLogs;
        }

        // Return log files for specific iteration
        const iterationData:
          | {
              logs?: ExecutionFile[];
              [category: string]: ExecutionFile[] | undefined;
            }
          | undefined = filesData.structure[iteration];
        return iterationData?.logs || [];
      }

      // Handle flat format as fallback
      if (filesData.files) {
        const allFiles = filesData.files;
        return allFiles.filter((file) => {
          if (file.type !== "log") return false;
          if (!iteration) return true; // Show all if no specific iteration

          // Extract iteration from file path for flat format
          const pathParts = file.path.split("/");
          if (pathParts.length >= 2 && pathParts[1].startsWith("iteration_")) {
            return pathParts[1] === iteration;
          }
          return false;
        });
      }

      return [];
    },
    [filesData],
  );

  // Helper function to get the latest log file for a specific iteration
  const getLatestLogFileForIteration = useCallback(
    (iteration: string | null): ExecutionFile | null => {
      const logFiles = getLogFilesForIteration(iteration);
      if (logFiles.length === 0) return null;

      return logFiles.reduce((latest, file) => {
        return new Date(file.created_at) > new Date(latest.created_at)
          ? file
          : latest;
      });
    },
    [getLogFilesForIteration],
  );

  // Track available iterations and set current iteration
  useEffect(() => {
    if (!filesData) return;

    console.log("Debug - Raw filesData structure:", filesData);

    let iterations: string[] = [];

    try {
      // Extract iterations from hierarchical structure
      if (filesData.structure) {
        console.log(
          "Debug - Structure keys:",
          Object.keys(filesData.structure),
        );
        console.log("Debug - Full structure:", filesData.structure);

        // Log each iteration's contents
        Object.entries(filesData.structure).forEach(([key, value]) => {
          if (key.startsWith("iteration_")) {
            console.log(`Debug - ${key} contents:`, value);
            if (value && typeof value === "object" && value.logs && Array.isArray(value.logs)) {
              console.log(
                `  - ${key} logs:`,
                value.logs.map((f: any) => f.name),
              );
            } else {
              console.log(`  - ${key} logs:`, value?.logs || "No logs array");
            }
          }
        });

        iterations = Object.keys(filesData.structure).filter((key) =>
          key.startsWith("iteration_"),
        );
      }
      // Fallback to flat format
      else if (filesData.files) {
        const iterationSet = new Set<string>();
        filesData.files.forEach((file) => {
          const pathParts = file.path.split("/");
          if (pathParts.length >= 2 && pathParts[1].startsWith("iteration_")) {
            iterationSet.add(pathParts[1]);
          }
        });
        iterations = Array.from(iterationSet);
      }

      const sortedIterations = iterations.sort((a, b) => {
        // Sort iterations numerically (iteration_1, iteration_2, etc.)
        const aNum = parseInt(a.replace("iteration_", ""));
        const bNum = parseInt(b.replace("iteration_", ""));
        return aNum - bNum;
      });

      setAvailableIterations(sortedIterations);

      // Set current iteration to the latest one if not already set or if it doesn't exist
      if (sortedIterations.length > 0) {
        if (!currentIteration || !sortedIterations.includes(currentIteration)) {
          // Default to the latest iteration (highest number)
          const latestIteration = sortedIterations[sortedIterations.length - 1];
          setCurrentIteration(latestIteration);
        }
      } else {
        setCurrentIteration(null);
      }
    } catch (error) {
      console.error("Error processing iterations:", error);
      setAvailableIterations([]);
      setCurrentIteration(null);
    }
  }, [filesData, currentIteration]);

  // Get current execution details - now using specific useRun hook for real-time updates
  // const currentExecution is now fetched directly above with useRun hook

  // Auto-redirect if execution not found - updated to work with useRun hook
  useEffect(() => {
    if (executionId && !currentExecutionLoading && currentExecutionError) {
      // If we have an executionId but got an error (like 404), redirect
      handleBackNavigation();
    }
  }, [executionId, currentExecutionError, currentExecutionLoading, handleBackNavigation]);

  // No embedded per-iteration browser; we navigate the main file view instead

  // (No per-iteration filtering via chips; chips only set current iteration for logs)

  // Update previous content ref when content changes externally
  useEffect(() => {
    previousContentRef.current = logViewerContent;
  }, [logViewerContent]);

  // Drag handlers for log panel resize
  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStartY(e.clientY);
    setDragStartHeight(logPanelHeight);
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging) return;
    const deltaY = dragStartY - e.clientY;
    const newHeight = Math.min(
      Math.max(100, dragStartHeight + deltaY),
      window.innerHeight * 0.7,
    );
    setLogPanelHeight(newHeight);
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  useEffect(() => {
    if (isDragging) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      return () => {
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
      };
    }
  }, [isDragging, dragStartY, dragStartHeight, logPanelHeight]);

  // Get latest log file for streaming (iteration-aware)

  // Stream log content
  const streamLogContent = useCallback(async () => {
    // Only stream when a user-selected log file is present
    const targetLog = currentLogFile;
    if (!targetLog) return;

    try {
      const response = await fetch(
        fileApi.getFileUrl(executionId!, targetLog.path),
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const content = await response.text();

      // Only update if content has actually changed to prevent blinking
      if (content !== previousContentRef.current) {
        setLogViewerContent(content);
        previousContentRef.current = content;
      }
    } catch (error) {
      console.error("Failed to stream log:", error);
    }
  }, [executionId, currentLogFile]);

  // Auto-stream logs when panel is open and execution is active (only when streaming mode)
  useEffect(() => {
    if (!logPanelOpen || !currentExecution) return;

    const isExecutionActive =
      currentExecution.status === "pending" ||
      currentExecution.status === "executing";
    const shouldContinueStreaming = (isExecutionActive || isSyncing) && !!currentLogFile;

    // If execution and syncing are complete, just show final content (no streaming)
    if (!shouldContinueStreaming) {
      if (isStreamingLogs && currentLogFile) {
        setIsStreamingLogs(false);
        // Load final log content once
        streamLogContent();
      }
      return;
    }

    // Only start streaming if we're not already streaming
    if (!isStreamingLogs || !currentLogFile) return;

    // Initial stream attempt
    streamLogContent();

    // Set up interval for continued streaming (every 2 seconds for fast updates)
    const interval = setInterval(streamLogContent, 2000);

    return () => clearInterval(interval);
  }, [
    logPanelOpen,
    currentExecution?.status,
    currentExecution,
    filesData,
    isStreamingLogs,
    isSyncing,
    streamLogContent,
    currentLogFile,
  ]);

  // Retry streaming when files data changes (helps with timing issues)
  useEffect(() => {
    if (!logPanelOpen || !isStreamingLogs || !filesData || !currentLogFile || logViewerContent)
      return;

    const retryTimer = setTimeout(streamLogContent, 500);
    return () => clearTimeout(retryTimer);
  }, [
    logPanelOpen,
    isStreamingLogs,
    filesData,
    logViewerContent,
    streamLogContent,
    currentLogFile,
  ]);

  // Reload logs when iteration changes
  useEffect(() => {
    if (!currentIteration) return;

    // Clear current log content (keep the selected file if any)
    setLogViewerContent("");

    // If execution is active, enable streaming for the new iteration only when a file is selected
    const isExecutionActive =
      currentExecution?.status === "pending" ||
      currentExecution?.status === "executing";

    if (isExecutionActive && logPanelOpen && currentLogFile) {
      setIsStreamingLogs(true);
      // Trigger immediate content load for selected file
      setTimeout(() => {
        streamLogContent();
      }, 100);
    } else {
      // Do not auto-load any log; require explicit selection
      setLogViewerContent("");
    }
  }, [
    currentIteration,
    currentExecution?.status,
    logPanelOpen,
    getLatestLogFileForIteration,
    streamLogContent,
    executionId,
    currentLogFile,
  ]);

  // Auto-enable streaming when component mounts if execution is active
  useEffect(() => {
    if (!currentExecution) return;

    const isExecutionActive =
      currentExecution.status === "pending" ||
      currentExecution.status === "executing";
    const shouldStream = (isExecutionActive || isSyncing) && !!currentLogFile;

    if (shouldStream) {
      setIsStreamingLogs(true);
      // Only stream selected file
      setTimeout(streamLogContent, 100);
    } else {
      setIsStreamingLogs(false);
    }
  }, [
    currentExecution?.uuid,
    currentExecution?.status,
    isSyncing,
    streamLogContent,
    currentLogFile,
  ]);

  // Fallback: if log panel is open and no selected log yet, auto-select latest for current iteration
  useEffect(() => {
    if (!logPanelOpen) return;
    if (currentLogFile) return;
    if (!currentIteration) return;
    const latest = getLatestLogFileForIteration(currentIteration);
    if (latest) {
      setCurrentLogFile(latest);
    }
  }, [logPanelOpen, currentLogFile, currentIteration, getLatestLogFileForIteration]);

  // Toggle between panel and modal
  const toggleLogView = () => {
    if (isLogFullScreen) {
      setIsLogFullScreen(false);
      setLogViewerOpen(false);
      setLogPanelOpen(true);
    } else {
      setLogPanelOpen(false);
      setLogViewerOpen(true);
      setIsLogFullScreen(true);
    }
  };




  // Get all screenshots for navigation
  const allScreenshots = useMemo(() => getAllScreenshots(filesData), [filesData]);
  const screenshotNav = useMemo(() => {
    if (!previewFile || previewFile.type !== "screenshot") {
      return null;
    }
    const nav = getScreenshotNavigation(previewFile, allScreenshots);
    const metadata = parseScreenshotMetadata(previewFile.name);
    return { ...nav, metadata };
  }, [previewFile, allScreenshots]);
  const previewIteration = useMemo(() => {
    if (!previewFile || previewFile.type !== "screenshot") {
      return null;
    }
    const iterations = progressData?.iterations;
    if (!iterations?.length) {
      return null;
    }
    const pathMatch =
      previewFile.path.match(/iteration_(\d+)/i) ||
      previewFile.name.match(/iteration_(\d+)/i);
    let iterationNumber = pathMatch ? parseInt(pathMatch[1], 10) : undefined;
    if (!iterationNumber) {
      const metadata = parseScreenshotMetadata(previewFile.name);
      iterationNumber = metadata.iteration;
    }
    if (!iterationNumber) {
      return null;
    }
    return (
      iterations.find(
        (iter) => iter.iteration_number === iterationNumber
      ) || null
    );
  }, [previewFile, progressData]);
  const {
    actions: previewTimelineActions,
    entries: previewTimelineEntries,
  } = useTimeline(executionId, previewIteration?.uuid, {
    enabled: !!executionId && !!previewIteration?.uuid,
    refetchInterval:
      previewIteration?.status === "executing" ||
      previewIteration?.status === "pending"
        ? 3000
        : undefined,
  });
  const previewActionIndex = useMemo(
    () => buildScreenshotActionIndex(previewTimelineActions),
    [previewTimelineActions]
  );
  const matchedAction = useMemo(() => {
    if (!previewFile || previewFile.type !== "screenshot") {
      return null;
    }
    return findActionForScreenshot(previewFile, previewActionIndex);
  }, [previewFile, previewActionIndex]);
  const [previewVariant, setPreviewVariant] = useState<"file" | "before" | "after">(
    "file"
  );
  useEffect(() => {
    setPreviewVariant("file");
    // Reset image loading and error states when preview file changes
    setIsImageLoading(true);
    setImageError(false);
  }, [previewFile]);
  const variantOptions = useMemo(() => {
    const action = matchedAction?.action;
    if (!action) return [];
    const options: Array<{ value: "before" | "after"; label: string }> = [];
    if (action.screenshot_before) {
      options.push({ value: "before", label: "Before" });
    }
    if (action.screenshot_after) {
      options.push({ value: "after", label: "After" });
    }
    return options;
  }, [matchedAction]);
  const showVariantToggle =
    variantOptions.length > 0 &&
    Boolean(matchedAction?.action && previewIteration?.uuid && executionId);
  const resolvedScreenshotSrc = useMemo(() => {
    if (!previewFile || previewFile.type !== "screenshot") {
      return null;
    }
    if (
      previewVariant !== "file" &&
      matchedAction?.action &&
      previewIteration?.uuid &&
      executionId
    ) {
      return timelineApi.getScreenshotUrl(
        executionId,
        previewIteration.uuid,
        matchedAction.action.id,
        previewVariant
      );
    }
    return fileApi.getFileUrl(executionId!, previewFile.path);
  }, [
    previewFile,
    previewVariant,
    matchedAction,
    previewIteration?.uuid,
    executionId,
  ]);
  const relativeTimeLabel = useMemo(
    () => getRelativeTimeLabel(previewFile),
    [previewFile]
  );
  const actionMetadataEntries = useMemo(() => {
    const actionMeta = matchedAction?.action?.metadata;
    if (!actionMeta) {
      return [];
    }
    return Object.entries(actionMeta)
      .filter(
        ([key, value]) =>
          Boolean(ACTION_METADATA_LABELS[key] && value !== null && value !== undefined && value !== "")
      )
      .map(([key, value]) => ({
        label: ACTION_METADATA_LABELS[key],
        value: formatMetadataValue(value),
      }));
  }, [matchedAction]);
  const actionIntent = useMemo(() => {
    if (!matchedAction?.action || !previewTimelineEntries?.length) {
      return null;
    }
    const actionSeq = matchedAction.action.sequence_index;
    const precedingIntent = [...previewTimelineEntries]
      .filter(
        (entry) =>
          (entry.entry_type === "model_thinking" ||
            entry.entry_type === "model_response") &&
          entry.sequence_index < actionSeq
      )
      .sort((a, b) => b.sequence_index - a.sequence_index)[0];
    if (!precedingIntent) {
      return null;
    }
    if (
      precedingIntent.entry_type === "model_thinking" ||
      precedingIntent.entry_type === "model_response"
    ) {
      return precedingIntent.content;
    }
    return null;
  }, [matchedAction, previewTimelineEntries]);

  // Handle keyboard navigation
  useEffect(() => {
    if (!previewFile || previewFile.type !== "screenshot" || !screenshotNav) {
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft" && screenshotNav.previous) {
        e.preventDefault();
        setPreviewFile(screenshotNav.previous);
      } else if (e.key === "ArrowRight" && screenshotNav.next) {
        e.preventDefault();
        setPreviewFile(screenshotNav.next);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [previewFile, screenshotNav]);

  const handleDownload = async (file: ExecutionFile) => {
    try {
      await downloadFile(executionId!, file);
    } catch (error) {
      console.error("Download failed:", error);
    }
  };

  const handleBulkDownload = async () => {
    const filesToDownload = getCurrentItems.files.filter((file) =>
      selectedFiles.has(file.path),
    );

    try {
      await downloadMultipleFiles(executionId!, filesToDownload);
      clearSelection();
    } catch (error) {
      console.error("Bulk download failed:", error);
    }
  };


  const { files: unsortedFiles } = getCurrentItems;

  const { filterCategories, filteredFiles } = useMemo(() => {
    const types = [...new Set(unsortedFiles.map((file) => file.type))];
    const categories: FilterCategory<ExecutionFile>[] = [
      { key: "type", label: "File Type", options: types },
    ];
    return { filterCategories: categories, filteredFiles: unsortedFiles };
  }, [unsortedFiles]);

  const { filteredItems } =
    useFiltering(filteredFiles, filterCategories);

  const sortOptions: SortOption<ExecutionFile>[] = [
    { value: "name", label: "Sort by Name" },
    { value: "created_at", label: "Sort by Date" },
    { value: "size", label: "Sort by Size" },
    { value: "type", label: "Sort by Type" },
  ];

  useSorting(filteredItems, sortOptions, {
    key: "created_at",
    direction: "desc",
  });

  if (!executionId) {
    return (
      <EmptyState
        icon={<MonitorIcon />}
        title="No Execution ID"
        description="No execution ID was provided"
      />
    );
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
        <Box sx={{ p: 3 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 4 }}>
            <IconButton onClick={handleBackNavigation} sx={{ mr: 1 }}>
              <BackIcon />
            </IconButton>
            <MonitorIcon sx={{ fontSize: 48 }} />
            <Box sx={{ flexGrow: 1 }}>
              <Typography variant="h3" component="h1" gutterBottom>
                Execution Monitor
              </Typography>

              {/* Run Context Information */}
              {currentExecution && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="h6" color="text.primary" gutterBottom>
                    {currentExecution.execution_type === "playground" 
                      ? "Playground"
                      : (currentGym?.name || "Unknown Gym")}
                    {(currentExecution.execution_type === "playground" && currentExecution.prompt) || (currentTask && currentExecution.execution_type !== "playground") ? (
                      <>
                        {" • "}
                        <Typography
                          component="span"
                          variant="h6"
                          color="text.secondary"
                          sx={{
                            maxWidth: "400px",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            display: "inline-block",
                            verticalAlign: "bottom",
                          }}
                          title={currentExecution.execution_type === "playground" ? (currentExecution.prompt || "") : (currentTask?.prompt || "")}
                        >
                          {currentExecution.execution_type === "playground" ? (currentExecution.prompt || "") : (currentTask?.prompt || "")}
                        </Typography>
                      </>
                    ) : null}
                  </Typography>
                  
                  
                  <Typography variant="body2" color="text.disabled">
                    {currentExecution.model.toUpperCase()} •{" "}
                    {currentExecution.number_of_iterations} iterations
                  </Typography>
                  
                  
                  {/* Execution Insights */}
                  <ExecutionInsights evalInsights={currentExecution.eval_insights} />
                </Box>
              )}

              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                {currentExecution && (
                  <Chip
                    label={getStatusDisplayLabel(currentExecution.status, currentExecution.execution_type)}
                    color={
                      getStatusColor(currentExecution.status) as
                        | "default"
                        | "primary"
                        | "secondary"
                        | "error"
                        | "info"
                        | "success"
                        | "warning"
                    }
                    size="small"
                  />
                )}
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ fontFamily: "monospace" }}
                >
                  {executionId}
                </Typography>
              </Box>
            </Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, ml: 'auto' }}>
              {executionId && (
                <Tooltip title="Download all execution assets as ZIP archive">
                  <span>
                    <IconButton
                      onClick={async () => {
                        if (!executionId || !currentExecution) return;
                        
                        try {
                          const url = fileApi.downloadExecution(executionId);
                          const filename = currentExecution.execution_folder_name 
                            ? `${currentExecution.execution_folder_name}.zip`
                            : `execution_${executionId}.zip`;

                          // Get token for authentication
                          const token = getAuthToken() || undefined;
                          
                          await addDownload('execution', url, filename, token);
                        } catch (error) {
                          showError(`Failed to start download: ${error instanceof Error ? error.message : 'Unknown error'}`);
                        }
                      }}
                      disabled={!executionId}
                      sx={{ 
                        color: 'white',
                        backgroundColor: 'rgba(255, 255, 255, 0.1)',
                        '&:hover': {
                          backgroundColor: 'rgba(255, 255, 255, 0.2)',
                        },
                        '&:disabled': {
                          backgroundColor: 'rgba(255, 255, 255, 0.05)',
                        }
                      }}
                    >
                      {executionId && downloads.some(
                        d => d.type === 'execution' && d.url.includes(`/executions/${executionId}/download`) && (d.status === 'downloading' || d.status === 'pending')
                      ) ? (
                        <CircularProgress size={24} sx={{ color: 'white' }} />
                      ) : (
                        <CloudDownloadIcon />
                      )}
                    </IconButton>
                  </span>
                </Tooltip>
              )}
              {(isSyncing || isManualRefreshing) && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  <CircularProgress size={16} />
                  <Typography variant="caption" color="text.secondary">
                    {isManualRefreshing ? "Refreshing..." : "Syncing files..."}
                  </Typography>
                </Box>
              )}
            </Box>
          </Box>

          {filesData && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <Chip
                label={
                  isManualRefreshing
                    ? `Refreshing... (${filesData.total_files} files)`
                    : isSyncing
                      ? `Syncing... (${filesData.total_files} files)`
                      : `${filesData.total_files} files`
                }
                size="small"
                color={isSyncing || isManualRefreshing ? "primary" : "default"}
                icon={
                  isSyncing || isManualRefreshing ? (
                    <CircularProgress size={12} />
                  ) : undefined
                }
              />
              <Chip
                label={filesData.execution_folder}
                size="small"
                variant="outlined"
                sx={{
                  borderColor: theme.palette.divider,
                  color: theme.palette.text.secondary,
                }}
              />
            </Box>
          )}

          {/* Iteration Status (global progress bar removed) */}
          {progressData && (
            <Box sx={{ mt: 1, display: "flex", flexDirection: "column", gap: 1 }}>
              {/* Placeholder for future status items if needed */}
            </Box>
          )}
        </Box>
      </Box>

      {/* Main Content */}
      <Box
        sx={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Tabs */}
        <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
          <Tabs
            value={tabValue}
            onChange={(_, newValue) => setTabValue(newValue)}
            sx={{
              "& .MuiTabs-indicator": {
                backgroundColor: `${theme.palette.text.secondary} !important`,
                display: "block !important",
              },
              "& .MuiTabs-root": {
                "& .MuiTabs-flexContainer": {
                  "& .MuiTab-root": {
                    color: `${theme.palette.text.disabled} !important`,
                    minHeight: "auto !important",
                    "&.Mui-selected": {
                      color: `${theme.palette.text.primary} !important`,
                      backgroundColor: "transparent !important",
                    },
                    "&:hover": {
                      color: `${theme.palette.text.secondary} !important`,
                      backgroundColor: "transparent !important",
                    },
                    "& .MuiTab-iconWrapper": {
                      color: `${theme.palette.text.disabled} !important`,
                      "& svg": {
                        color: `${theme.palette.text.disabled} !important`,
                      },
                    },
                    "&.Mui-selected .MuiTab-iconWrapper": {
                      color: `${theme.palette.text.primary} !important`,
                      "& svg": {
                        color: `${theme.palette.text.primary} !important`,
                      },
                    },
                    "& .MuiTouchRipple-root": {
                      color: `${theme.palette.text.secondary} !important`,
                    },
                  },
                },
              },
              "& .MuiTab-root": {
                color: `${theme.palette.text.disabled} !important`,
                "&.Mui-selected": {
                  color: `${theme.palette.text.primary} !important`,
                },
                "&:hover": {
                  color: `${theme.palette.text.secondary} !important`,
                },
                "& .MuiTab-iconWrapper": {
                  color: `${theme.palette.text.disabled} !important`,
                },
                "&.Mui-selected .MuiTab-iconWrapper": {
                  color: `${theme.palette.text.primary} !important`,
                },
              },
            }}
          >
            <Tab icon={<SpeedIcon />} label="Progress" />
            <Tab icon={<SpeedIcon />} label="Summary" />
          </Tabs>
        </Box>

        {/* Tab Content */}
        <Box sx={{ flex: 1 }}>
          {tabValue === 0 && (
            <Box
              sx={{
                display: "flex",
                flexDirection: "column",
                p: 3,
              }}
            >
              {/* Execution Overall Summary */}
              <ExecutionOverallSummary
                execution={currentExecution}
                isLoading={currentExecutionLoading}
                error={currentExecutionError as Error | null}
                progressData={progressData}
              />

              {/* Iterations Grid */}
              {progressData && progressData.tasks && (
                <Box>
                  {progressData.tasks.map((task) => (
                    <Box key={task.task_uuid} sx={{ mb: 4 }}>
                      {/* Task Header */}
                      {currentExecution?.execution_type !== "playground" && (
                        <Box sx={{ mb: 2 }}>
                          <Typography variant="h6" sx={{ fontWeight: 600, mb: 1.5 }}>
                            {task.task_id}
                          </Typography>
                        </Box>
                      )}
                      
                      {/* Task Prompt Card */}
                      <Paper
                        elevation={0}
                        sx={{
                          p: 2.5,
                          mb: 3,
                          backgroundColor: theme.palette.mode === "dark" 
                            ? "rgba(255,255,255,0.02)" 
                            : "rgba(0,0,0,0.02)",
                          borderLeft: "4px solid",
                          borderLeftColor: "primary.main",
                          borderRadius: 1,
                        }}
                      >
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
                          <AssignmentIcon sx={{ fontSize: 18, color: "primary.main" }} />
                          <Typography 
                            variant="overline" 
                            sx={{ 
                              fontWeight: 700, 
                              letterSpacing: 1,
                              color: "primary.main"
                            }}
                          >
                            Task Prompt
                          </Typography>
                        </Box>
                        <Typography
                          variant="body2"
                          sx={{
                            lineHeight: 1.7,
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                            fontFamily: theme.palette.mode === "dark" 
                              ? "monospace" 
                              : "inherit",
                          }}
                        >
                          {task.prompt}
                        </Typography>
                      </Paper>

                      {/* Iteration Cards Grid */}
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
                        {task.iterations.map((iteration) => (
                          <IterationCard
                            executionType={currentExecution?.execution_type}
                            key={iteration.uuid}
                            iteration={iteration}
                            executionId={executionId!}
                            taskId={task.task_id}
                            batchId={batchId}
                          />
                        ))}
                      </Box>
                    </Box>
                  ))}
                </Box>
              )}

              {/* Empty State */}
              {(!progressData || !progressData.tasks || progressData.tasks.length === 0) && (
                <EmptyState
                  icon={<SpeedIcon />}
                  title="No iterations found"
                  description="This execution doesn't have any iterations yet"
                />
              )}
            </Box>
          )}

          {tabValue === 1 && (
            <Box sx={{ p: 3 }}>
              {summaryLoading ? (
                <CircularProgress />
              ) : summaryData ? (
                <Paper sx={{ p: 3 }}>
                  <Typography variant="h6" gutterBottom>
                    Execution Summary
                  </Typography>
                  <pre>{JSON.stringify(summaryData.summary, null, 2)}</pre>
                </Paper>
              ) : (
                <Alert severity="info">No summary data available yet</Alert>
              )}
            </Box>
          )}
        </Box>
      </Box>

      {/* Floating Action Button for bulk actions */}
      {selectedCount > 0 && (
        <Fab
          color="default"
          sx={{ position: "fixed", bottom: 20, right: 20 }}
          onClick={handleBulkDownload}
        >
          <CloudDownloadIcon />
        </Fab>
      )}

      {/* File Preview Modal */}
      {previewFile && (
        <Dialog
          open
          onClose={() => {
            setPreviewFile(null);
            setJsonContent("");
            setJsonError(null);
            setIsLoadingJson(false);
          }}
          maxWidth={false}
          fullWidth
          PaperProps={{
            sx: {
              width: "78vw",
              maxWidth: "none",
              height: "80vh",
              m: 2,
            },
          }}
        >
          <DialogTitle
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, flex: 1 }}>
              <Typography variant="h6" sx={{ flex: 1 }}>{previewFile.name}</Typography>
              {previewFile.type === "screenshot" && screenshotNav && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  {screenshotNav.metadata && (
                    <Box sx={{ display: "flex", gap: 1, mr: 1 }}>
                      {screenshotNav.metadata.iteration !== undefined && (
                        <Chip
                          label={`Iteration ${screenshotNav.metadata.iteration}`}
                          size="small"
                          variant="outlined"
                        />
                      )}
                      {screenshotNav.metadata.step !== undefined && (
                        <Chip
                          label={`Step ${screenshotNav.metadata.step}`}
                          size="small"
                          variant="outlined"
                        />
                      )}
                      {screenshotNav.metadata.actionType && (
                        <Chip
                          label={screenshotNav.metadata.actionType}
                          size="small"
                          variant="outlined"
                          color="primary"
                        />
                      )}
                    </Box>
                  )}
                  <Typography variant="caption" color="text.secondary">
                    {screenshotNav.index} / {screenshotNav.total}
                  </Typography>
                  <Typography 
                    variant="caption" 
                    color="text.disabled" 
                    sx={{ 
                      ml: 1,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.5,
                      px: 1,
                      py: 0.5,
                      backgroundColor: theme.palette.mode === 'dark'
                        ? 'rgba(255,255,255,0.05)'
                        : 'rgba(0,0,0,0.03)',
                      borderRadius: 1,
                      fontSize: '0.7rem',
                    }}
                  >
                    <KeyboardIcon fontSize="small" />
                    Use ← → to navigate
                  </Typography>
                </Box>
              )}
            </Box>
            <IconButton
              onClick={() => {
                setPreviewFile(null);
                setJsonContent("");
                setJsonError(null);
                setIsLoadingJson(false);
              }}
            >
              <CloseIcon />
            </IconButton>
          </DialogTitle>
          <DialogContent sx={{ minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            {previewFile.type === "screenshot" ? (
              <Box
                sx={{
                  display: "flex",
                  flexDirection: { xs: "column", md: "row" },
                  gap: 3,
                  flex: 1,
                  minHeight: 0,
                  overflow: 'hidden',
                }}
              >
                <Box
                  sx={{
                    flex: 1,
                    display: "flex",
                    alignItems: "center",
                    gap: 2,
                  }}
                >
                  {screenshotNav && (
                    <IconButton
                      onClick={() => {
                        screenshotNav.previous && setPreviewFile(screenshotNav.previous);
                      }}
                      disabled={!screenshotNav.previous}
                      sx={{
                        flexShrink: 0,
                        width: 48,
                        height: 48,
                        backgroundColor: "rgba(0,0,0,0.55)",
                        color: "common.white",
                        borderRadius: "50%",
                        boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                        backdropFilter: "blur(4px)",
                        transition: 'all 0.2s ease',
                        "&:hover": {
                          backgroundColor: "rgba(0,0,0,0.75)",
                          transform: 'scale(1.1)',
                          boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
                        },
                        "&:active": {
                          transform: 'scale(0.95)',
                        },
                        "&.Mui-disabled": {
                          opacity: 0.3,
                          backgroundColor: "rgba(0,0,0,0.4)",
                        },
                      }}
                      title="Previous (←)"
                    >
                      <ArrowBackIcon />
                    </IconButton>
                  )}
                  <Box sx={{ flex: 1 }}>
                    {/* Always reserve space for toggle buttons to prevent layout shift */}
                    <Box sx={{ minHeight: showVariantToggle ? 'auto' : 40, mb: showVariantToggle ? 2 : 0 }}>
                      {showVariantToggle && (
                        <ToggleButtonGroup
                          exclusive
                          size="small"
                          value={previewVariant}
                          onChange={(_, value) => {
                            if (value) {
                              setPreviewVariant(value);
                            }
                          }}
                          sx={{ justifyContent: "center" }}
                        >
                          <ToggleButton value="file">Saved</ToggleButton>
                          {variantOptions.map((option) => (
                            <ToggleButton key={option.value} value={option.value}>
                              {option.label}
                            </ToggleButton>
                          ))}
                        </ToggleButtonGroup>
                      )}
                    </Box>
                    <Box 
                      sx={{ 
                        textAlign: "center", 
                        position: "relative", 
                        minHeight: 200,
                        backgroundColor: theme.palette.mode === 'dark' 
                          ? 'rgba(0,0,0,0.2)' 
                          : 'rgba(0,0,0,0.02)',
                        borderRadius: 2,
                        p: 2,
                        border: `1px solid ${theme.palette.divider}`,
                        transition: 'all 0.2s ease-in-out',
                        '&:hover': {
                          borderColor: theme.palette.primary.main,
                        }
                      }}
                    >
                      {isImageLoading && !imageError && (
                        <Skeleton
                          variant="rectangular"
                          sx={{
                            position: "absolute",
                            top: 16,
                            left: 16,
                            right: 16,
                            width: "calc(100% - 32px)",
                            height: "70vh",
                            maxHeight: "70vh",
                            borderRadius: 1,
                            zIndex: 1,
                            backgroundColor: theme.palette.background.paper,
                          }}
                          animation="wave"
                        />
                      )}
                      {imageError ? (
                        <Box
                          sx={{
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                            gap: 2,
                            p: 3,
                          }}
                        >
                          <Typography variant="body2" color="error">
                            Failed to load screenshot
                          </Typography>
                          <Button
                            variant="outlined"
                            size="small"
                            onClick={() => {
                              setImageError(false);
                              setIsImageLoading(true);
                            }}
                          >
                            Retry
                          </Button>
                        </Box>
                      ) : (
                        <img
                            src={
                              resolvedScreenshotSrc ??
                              fileApi.getFileUrl(executionId!, previewFile.path)
                            }
                            alt={previewFile.name}
                            style={{
                              maxWidth: "100%",
                              maxHeight: "70vh",
                              opacity: isImageLoading ? 0 : 1,
                              transition: 'opacity 0.3s ease-in-out',
                              borderRadius: 1,
                              boxShadow: theme.palette.mode === 'dark' 
                                ? '0 4px 20px rgba(0,0,0,0.5)' 
                                : '0 2px 8px rgba(0,0,0,0.1)',
                            }}
                            onLoadStart={() => setIsImageLoading(true)}
                            onLoad={() => setIsImageLoading(false)}
                            onError={() => {
                              setIsImageLoading(false);
                              setImageError(true);
                            }}
                          />
                      )}
                    </Box>
                    {relativeTimeLabel && (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ display: "block", textAlign: "center", mt: 1 }}
                      >
                        Captured {relativeTimeLabel}
                      </Typography>
                    )}
                  </Box>
                  {screenshotNav && (
                    <IconButton
                      onClick={() => {
                        screenshotNav.next && setPreviewFile(screenshotNav.next);
                      }}
                      disabled={!screenshotNav.next}
                      sx={{
                        flexShrink: 0,
                        width: 48,
                        height: 48,
                        backgroundColor: "rgba(0,0,0,0.55)",
                        color: "common.white",
                        borderRadius: "50%",
                        boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                        backdropFilter: "blur(4px)",
                        transition: 'all 0.2s ease',
                        "&:hover": {
                          backgroundColor: "rgba(0,0,0,0.75)",
                          transform: 'scale(1.1)',
                          boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
                        },
                        "&:active": {
                          transform: 'scale(0.95)',
                        },
                        "&.Mui-disabled": {
                          opacity: 0.3,
                          backgroundColor: "rgba(0,0,0,0.4)",
                        },
                      }}
                      title="Next (→)"
                    >
                      <ArrowForwardIcon />
                    </IconButton>
                  )}
                </Box>
              <Box
                sx={{
                  flexBasis: { xs: "100%", md: 320 },
                  maxWidth: { md: 320 },
                  minWidth: { md: 320 },
                  flexShrink: 0,
                  display: "flex",
                  flexDirection: "column",
                  minHeight: 0,
                  height: { md: "100%" },
                  maxHeight: { md: "100%" },
                  position: { md: "sticky" },
                  top: 0,
                  alignSelf: { md: "stretch" },
                }}
              >
                {matchedAction?.action ? (
                  <Paper
                    elevation={0}
                    sx={{
                      p: 0,
                      flex: 1,
                      display: "flex",
                      flexDirection: "column",
                      backgroundColor: theme.palette.background.paper,
                      border: `1px solid ${theme.palette.divider}`,
                      borderRadius: 0,
                      overflow: "hidden",
                      height: "100%",
                    }}
                  >
                    <Typography
                      variant="subtitle2"
                      color="text.secondary"
                      sx={{
                        position: { md: "sticky" },
                        top: 0,
                        zIndex: 3,
                        px: 3,
                        py: 2,
                        borderBottom: `1px solid ${theme.palette.divider}`,
                        backgroundColor: theme.palette.background.paper,
                      }}
                    >
                      Action Context
                    </Typography>
                    <Box
                      sx={{
                        display: "flex",
                        flexDirection: "column",
                        flex: 1,
                        minHeight: 0,
                        overflow: "auto",
                        px: 3,
                        py: 3,
                      }}
                    >
                      <Typography variant="h6" gutterBottom>
                        {matchedAction.action.action_name || "Unnamed Action"}
                      </Typography>
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.5, mb: 2 }}>
                        {matchedAction.action.action_type && (
                          <Chip
                            label={matchedAction.action.action_type.toUpperCase()}
                            size="small"
                            color="primary"
                          />
                        )}
                        <Chip
                          label={matchedAction.action.status.toUpperCase()}
                          size="small"
                          color={matchedAction.action.status === "success" ? "success" : "warning"}
                          variant="filled"
                        />
                        {previewIteration && (
                          <Chip
                            label={`Iteration ${previewIteration.iteration_number}`}
                            size="small"
                            variant="outlined"
                          />
                        )}
                        {relativeTimeLabel && (
                          <Chip label={relativeTimeLabel} size="small" variant="outlined" />
                        )}
                        {typeof matchedAction.action.sequence_index === "number" && (
                          <Chip
                            label={`Sequence ${matchedAction.action.sequence_index}`}
                            size="small"
                            color="default"
                            variant="outlined"
                          />
                        )}
                      </Box>
                    {actionIntent && (
                      <>
                        <Box
                          sx={{
                            mt: 2,
                            mb: 2,
                            borderTop: `1px solid ${theme.palette.divider}`,
                            pt: 2,
                          }}
                        >
                          <Box 
                            sx={{ 
                              p: 1.5,
                              backgroundColor: theme.palette.mode === 'dark' 
                                ? 'rgba(255,255,255,0.03)' 
                                : 'rgba(0,0,0,0.02)',
                              borderRadius: 1,
                              borderLeft: `3px solid ${theme.palette.primary.main}`,
                            }}
                          >
                        <Typography 
                          variant="caption" 
                          color="text.secondary" 
                          sx={{ 
                            fontWeight: 600,
                            textTransform: 'uppercase',
                            letterSpacing: 0.5,
                            mb: 1,
                            display: 'block'
                          }}
                        >
                          Reasoning
                        </Typography>
                        <Typography 
                          variant="body2" 
                          sx={{ 
                            lineHeight: 1.6,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                          }}
                        >
                          {actionIntent}
                        </Typography>
                          </Box>
                        </Box>
                      </>
                    )}
                    {(matchedAction.action.current_url || actionMetadataEntries.length > 0) && (
                      <Box
                        sx={{
                          mt: actionIntent ? 2 : 0,
                          borderTop: `1px solid ${theme.palette.divider}`,
                          pt: 2,
                          display: "flex",
                          flexDirection: "column",
                          gap: 1,
                        }}
                      >
                        {matchedAction.action.current_url && (
                          <Box
                            sx={{
                              display: "flex",
                              flexDirection: "column",
                              gap: 0.5,
                            }}
                          >
                            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                              <Typography variant="caption" color="text.secondary">
                                URL
                              </Typography>
                              <IconButton
                                size="small"
                                onClick={() => {
                                  navigator.clipboard.writeText(matchedAction.action.current_url!);
                                }}
                                sx={{ ml: 1 }}
                              >
                                <ContentCopyIcon fontSize="small" />
                              </IconButton>
                            </Box>
                            <Link
                              href={matchedAction.action.current_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              sx={{
                                fontFamily: "monospace",
                                fontSize: "0.75rem",
                                wordBreak: "break-all",
                                display: "flex",
                                alignItems: "center",
                                gap: 0.5,
                              }}
                            >
                              {matchedAction.action.current_url}
                              <OpenInNewIcon fontSize="small" />
                            </Link>
                          </Box>
                        )}
                        {actionMetadataEntries.length > 0 && (
                          <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mt: matchedAction.action.current_url ? 2 : 0 }}>
                            <Typography 
                              variant="caption" 
                              color="text.secondary"
                              sx={{ 
                                fontWeight: 600,
                                textTransform: 'uppercase',
                                letterSpacing: 0.5,
                              }}
                            >
                              Action Details
                            </Typography>
                            {actionMetadataEntries.map((entry, idx) => (
                              <Box
                                key={`${entry.label}-${idx}`}
                                sx={{
                                  display: "flex",
                                  justifyContent: "space-between",
                                  alignItems: "flex-start",
                                  gap: 2,
                                  borderBottom: idx === actionMetadataEntries.length - 1
                                    ? "none"
                                    : `1px solid ${theme.palette.divider}`,
                                  pb: 1,
                                }}
                              >
                                <Typography
                                  variant="caption"
                                  color="text.secondary"
                                  sx={{ 
                                    minWidth: 140,
                                  }}
                                >
                                  {entry.label}
                                </Typography>
                                <Typography
                                  variant="body2"
                                  sx={{
                                    fontFamily: "monospace",
                                    wordBreak: "break-word",
                                    textAlign: "right",
                                    flex: 1,
                                  }}
                                >
                                  {entry.value}
                                </Typography>
                                {entry.label.includes('URL') && (
                                  <IconButton
                                    size="small"
                                    onClick={() => navigator.clipboard.writeText(entry.value)}
                                    sx={{ ml: 0.5 }}
                                  >
                                    <ContentCopyIcon fontSize="small" />
                                  </IconButton>
                                )}
                              </Box>
                            ))}
                          </Box>
                        )}
                      </Box>
                    )}
                    </Box>
                  </Paper>
                ) : (
                  // Empty placeholder to maintain layout when no action context
                  <Box sx={{ minHeight: { md: 200 } }} />
                )}
              </Box>
              </Box>
            ) : previewFile.type === "json" ? (
              <Box sx={{ height: "500px" }}>
                {isLoadingJson ? (
                  <Box
                    sx={{
                      display: "flex",
                      justifyContent: "center",
                      alignItems: "center",
                      height: "100%",
                    }}
                  >
                    <CircularProgress />
                    <Typography sx={{ ml: 2 }}>Loading JSON...</Typography>
                  </Box>
                ) : jsonError ? (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {jsonError}
                  </Alert>
                ) : (
                  <Box
                    component="pre"
                    sx={{
                      backgroundColor: theme.palette.grey[50],
                      padding: 2,
                      borderRadius: 1,
                      overflow: "auto",
                      height: "100%",
                      fontFamily: "monospace",
                      fontSize: "0.875rem",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      border: `1px solid ${theme.palette.divider}`,
                      ...(theme.palette.mode === "dark" && {
                        backgroundColor: theme.palette.grey[900],
                        color: theme.palette.grey[100],
                      }),
                    }}
                  >
                    {jsonContent}
                  </Box>
                )}
              </Box>
            ) : (
              <Typography>
                Preview not available for {previewFile.type} files. Use download
                to view.
              </Typography>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setPreviewFile(null)}>Close</Button>
            <Button
              variant="contained"
              color="primary"
              onClick={() => handleDownload(previewFile)}
              sx={{ minWidth: 120 }}
            >
              Download
            </Button>
          </DialogActions>
        </Dialog>
      )}

      {/* Draggable Log Panel */}
      {logPanelOpen && (
        <Box
          ref={logPanelRef}
          sx={{
            position: "fixed",
            bottom: 0,
            left: SIDEBAR_WIDTH, // Account for sidebar width
            right: 0,
            height: logPanelHeight,
            backgroundColor:
              theme.palette.mode === "light" ? "#f5f5f5" : "#1e1e1e",
            borderTop: `1px solid ${theme.palette.divider}`,
            zIndex: 1000,
            display: "flex",
            flexDirection: "column",
            // Responsive behavior for mobile
            "@media (max-width: 600px)": {
              left: 0,
            },
          }}
        >
          {/* Drag Handle */}
          <Box
            onMouseDown={handleMouseDown}
            sx={{
              height: 8,
              backgroundColor:
                theme.palette.mode === "light" ? "#e0e0e0" : "#333",
              cursor: "ns-resize",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              "&:hover": {
                backgroundColor:
                  theme.palette.mode === "light" ? "#d0d0d0" : "#444",
              },
              userSelect: "none",
            }}
          >
            <DragIcon
              sx={{
                color:
                  theme.palette.mode === "light"
                    ? theme.palette.text.disabled
                    : "#666",
                fontSize: 16,
              }}
            />
          </Box>

          {/* Panel Header */}
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              px: 2,
              py: 1,
              backgroundColor:
                theme.palette.mode === "light" ? "#e0e0e0" : "#2d2d2d",
              borderBottom: `1px solid ${theme.palette.divider}`,
              minHeight: 48,
            }}
          >
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1,
                flex: 1,
                minWidth: 0,
              }}
            >
              <TerminalIcon
                sx={{
                  color:
                    theme.palette.mode === "light"
                      ? theme.palette.text.primary
                      : "#fff",
                  fontSize: 20,
                  flexShrink: 0,
                }}
              />
              <Box
                sx={{
                  display: "flex",
                  flexDirection: "column",
                  minWidth: 0,
                  flex: 1,
                }}
              >
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 1,
                    mb: 0.5,
                  }}
                >
                  {isStreamingLogs &&
                    (currentExecution?.status === "executing" ||
                      currentExecution?.status === "pending" ||
                      isSyncing) && (
                      <Chip
                        label={
                          currentExecution?.status === "executing"
                            ? "🔴 LIVE"
                            : isSyncing
                              ? "📁 SYNCING"
                              : "⏳ PENDING"
                        }
                        size="small"
                        sx={{
                          backgroundColor:
                            currentExecution?.status === "executing"
                              ? "#f44336"
                              : isSyncing
                                ? "#ff9800"
                                : "#2196f3",
                          color: "white",
                          fontSize: "0.7rem",
                          height: 20,
                          fontWeight: "bold",
                        }}
                      />
                    )}
                </Box>

                {/* Iteration titles removed: log panel shows only the selected log */}

                {/* Selected Log Title */}
                <Typography
                  variant="subtitle1"
                  sx={{
                    fontWeight: 600,
                    mb: 0.5,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {(() => {
                    const iterationPrefix = currentIteration
                      ? `[${currentIteration.replace("iteration_", "Iter ")}] `
                      : "";
                    return currentLogFile
                      ? `${iterationPrefix}${currentLogFile.name}`
                      : "No log selected yet";
                  })()}
                </Typography>

                {(() => {
                  const fileToShow = currentLogFile;
                  if (fileToShow && availableIterations.length === 0) {
                    return (
                      <Typography
                        variant="caption"
                        sx={{
                          color:
                            theme.palette.mode === "light"
                              ? theme.palette.text.secondary
                              : "#999",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {`${(fileToShow.size / 1024).toFixed(1)}KB • ${new Date(fileToShow.created_at).toLocaleTimeString()}`}
                      </Typography>
                    );
                  }
                  return null;
                })()}
              </Box>
            </Box>
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1,
                flexShrink: 0,
              }}
            >
              <Tooltip title={showLogContent ? "Hide content" : "Show content"}>
                <IconButton
                  size="small"
                  onClick={() => setShowLogContent((v) => !v)}
                  sx={{
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.primary
                        : "#fff",
                  }}
                >
                  {showLogContent ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
              <Tooltip title="Scroll to Top">
                <IconButton
                  size="small"
                  onClick={() => {
                    if (logContainerRef.current) {
                      logContainerRef.current.scrollTop = 0;
                    }
                  }}
                  sx={{
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.primary
                        : "#fff",
                  }}
                >
                  <KeyboardArrowUpIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Scroll to Bottom">
                <IconButton
                  size="small"
                  onClick={() => {
                    if (logContainerRef.current) {
                      logContainerRef.current.scrollTop =
                        logContainerRef.current.scrollHeight;
                    }
                  }}
                  sx={{
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.primary
                        : "#fff",
                  }}
                >
                  <KeyboardArrowDownIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Refresh Logs">
                <IconButton
                  size="small"
                  onClick={streamLogContent}
                  sx={{
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.primary
                        : "#fff",
                  }}
                >
                  <RefreshIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Fullscreen">
                <IconButton
                  size="small"
                  onClick={toggleLogView}
                  sx={{
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.primary
                        : "#fff",
                  }}
                >
                  <FullScreenIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Close">
                <IconButton
                  size="small"
                  onClick={() => setLogPanelOpen(false)}
                  sx={{
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.primary
                        : "#fff",
                  }}
                >
                  <CloseIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>

          {/* Log Content: title-only by default; toggle can show full content */}
          <Box
            ref={logContainerRef}
            sx={{
              flex: 1,
              overflow: "auto",
              p: 2,
              backgroundColor:
                theme.palette.mode === "light" ? "#f5f5f5" : "#1e1e1e",
              transition: "all 0.15s ease-in-out",
            }}
          >
            {showLogContent && logViewerContent ? (
              <pre
                style={{
                  fontFamily: "monospace",
                  whiteSpace: "pre-wrap",
                  color:
                    theme.palette.mode === "light"
                      ? theme.palette.text.primary
                      : "#ffffff",
                  margin: 0,
                  fontSize: "13px",
                  lineHeight: 1.4,
                  padding: "8px",
                  width: "100%",
                  boxSizing: "border-box",
                  overflowX: "auto",
                }}
              >
                {logViewerContent}
              </pre>
            ) : (
              <Box sx={{ textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%" }}>
                <TerminalIcon
                  sx={{
                    fontSize: 40,
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.disabled
                        : "#777",
                    mb: 1,
                  }}
                />
                <Typography variant="h6" sx={{ mb: 0.5 }}>
                  {(() => {
                    const iterationPrefix = currentIteration
                      ? `[${currentIteration.replace("iteration_", "Iter ")}] `
                      : "";
                    if (currentLogFile) return `${iterationPrefix}${currentLogFile.name}`;
                    return "No log selected yet";
                  })()}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {(() => {
                    const selected = currentLogFile;
                    if (selected) {
                      return `${(selected.size / 1024).toFixed(1)}KB • ${new Date(selected.created_at).toLocaleTimeString()}`;
                    }
                    return currentExecution?.status === "executing"
                      ? "Logs will appear here during execution"
                      : "Select a log file to view its title";
                  })()}
                </Typography>
              </Box>
            )}
          </Box>
        </Box>
      )}

      {/* Log Viewer Modal */}
      <Dialog
        open={logViewerOpen}
        onClose={() => setLogViewerOpen(false)}
        maxWidth="xl"
        fullWidth
      >
        <DialogTitle
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <Typography variant="h6">
              {(() => {
                const iterationPrefix = currentIteration
                  ? `[${currentIteration.replace("iteration_", "Iter ")}] `
                  : "";

                if (currentLogFile) {
                  return `${iterationPrefix}${currentLogFile.name}`;
                }
                return `${iterationPrefix}Log Viewer`;
              })()}
            </Typography>
            {isStreamingLogs &&
              (currentExecution?.status === "executing" ||
                currentExecution?.status === "pending" ||
                isSyncing) && (
                <Chip
                  label={
                    currentExecution?.status === "executing"
                      ? "LIVE"
                      : isSyncing
                        ? "SYNCING"
                        : "PENDING"
                  }
                  size="small"
                  sx={{
                    backgroundColor:
                      currentExecution?.status === "executing"
                        ? "#f44336"
                        : isSyncing
                          ? "#ff9800"
                          : "#2196f3",
                    color: "white",
                  }}
                />
              )}
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Tooltip title="Exit Full Screen">
              <IconButton onClick={toggleLogView}>
                <ExitFullScreenIcon />
              </IconButton>
            </Tooltip>
            <IconButton onClick={() => setLogViewerOpen(false)}>
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>

        <DialogContent>
          <Paper
            ref={logContainerRef}
            sx={{
              backgroundColor:
                theme.palette.mode === "light" ? "#f5f5f5" : "#1e1e1e",
              color:
                theme.palette.mode === "light"
                  ? theme.palette.text.primary
                  : "#ffffff",
              p: 2,
              maxHeight: "70vh",
              overflow: "auto",
              position: "relative",
            }}
          >
            <Box
              sx={{
                position: "absolute",
                top: 8,
                right: 8,
                display: "flex",
                gap: 1,
                zIndex: 1,
              }}
            >
              <IconButton
                size="small"
                onClick={() => {
                  if (logContainerRef.current) {
                    logContainerRef.current.scrollTop = 0;
                  }
                }}
                sx={{
                  backgroundColor:
                    theme.palette.mode === "light"
                      ? "rgba(0, 0, 0, 0.1)"
                      : "rgba(255, 255, 255, 0.1)",
                  color:
                    theme.palette.mode === "light"
                      ? theme.palette.text.primary
                      : "#ffffff",
                  "&:hover": {
                    backgroundColor:
                      theme.palette.mode === "light"
                        ? "rgba(0, 0, 0, 0.2)"
                        : "rgba(255, 255, 255, 0.2)",
                  },
                }}
                title="Scroll to top"
              >
                ⬆️
              </IconButton>
              <IconButton
                size="small"
                onClick={() => {
                  if (logContainerRef.current) {
                    logContainerRef.current.scrollTop =
                      logContainerRef.current.scrollHeight;
                  }
                }}
                sx={{
                  backgroundColor:
                    theme.palette.mode === "light"
                      ? "rgba(0, 0, 0, 0.1)"
                      : "rgba(255, 255, 255, 0.1)",
                  color:
                    theme.palette.mode === "light"
                      ? theme.palette.text.primary
                      : "#ffffff",
                  "&:hover": {
                    backgroundColor:
                      theme.palette.mode === "light"
                        ? "rgba(0, 0, 0, 0.2)"
                        : "rgba(255, 255, 255, 0.2)",
                  },
                }}
                title="Scroll to bottom"
              >
                ⬇️
              </IconButton>
            </Box>
            {logViewerContent ? (
              <pre
                style={{
                  fontFamily: "monospace",
                  whiteSpace: "pre-wrap",
                  paddingTop: "40px",
                }}
              >
                {logViewerContent}
              </pre>
            ) : availableIterations.length > 1 && !currentIteration ? (
              <Box sx={{ textAlign: "center", py: 8, paddingTop: "60px" }}>
                <TerminalIcon
                  sx={{
                    fontSize: 64,
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.disabled
                        : "#444",
                    mb: 3,
                  }}
                />
                <Typography
                  variant="h5"
                  sx={{
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.secondary
                        : "#999",
                    mb: 2,
                  }}
                >
                  Multiple Iterations Available
                </Typography>
                <Typography
                  variant="body1"
                  sx={{
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.secondary
                        : "#999",
                    mb: 3,
                  }}
                >
                  Select an iteration tab above to view its logs
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.disabled
                        : "#666",
                  }}
                >
                  {availableIterations.length} iterations found
                </Typography>
              </Box>
            ) : (
              <Box sx={{ textAlign: "center", py: 8, paddingTop: "60px" }}>
                <TerminalIcon
                  sx={{
                    fontSize: 64,
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.disabled
                        : "#444",
                    mb: 3,
                  }}
                />
                <Typography
                  variant="h6"
                  sx={{
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.secondary
                        : "#999",
                    mb: 2,
                  }}
                >
                  No logs available yet
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    color:
                      theme.palette.mode === "light"
                        ? theme.palette.text.disabled
                        : "#666",
                  }}
                >
                  Logs will appear here once the execution starts
                </Typography>
              </Box>
            )}
          </Paper>
        </DialogContent>
      </Dialog>
    </Box>
  );
}
