import { useEffect, useState, useRef, useMemo, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Box,
  Typography,
  IconButton,
  Chip,
  Paper,
  CircularProgress,
  Alert,
  useTheme,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  ToggleButtonGroup,
  ToggleButton,
  Link,
  Skeleton,
  Tooltip,
} from "@mui/material";
import {
  ArrowBack as BackIcon,
  Monitor as MonitorIcon,
  Close as CloseIcon,
  MonitorHeart as LiveMonitorIcon,
  CloudDownload as CloudDownloadIcon,
  Code as CodeIcon,
  ViewList as ViewListIcon,
} from "@mui/icons-material";
import { useIterationFiles } from "../hooks/useIterationFiles";
import { useExecutionProgress } from "../hooks/useExecutionProgress";
import { useRun } from "../hooks/useRuns";
import { useTimeline } from "../hooks/useTimeline";
import { getStatusColor } from "../utils/sharedStyles";
import { getStatusDisplayLabel } from "../utils/runUtils";
import EmptyState from "../components/EmptyState";
import IterationFileBrowser from "../components/IterationFileBrowser";
import VerificationInsightsTabs from "../components/VerificationInsightsTabs";
import ActionMonitoringModal from "../components/ActionMonitoringModal";
import { fileApi, timelineApi, getAuthToken } from "../services/api";
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
import NotificationSnackbar from "../components/NotificationSnackbar";
import StructuredLogViewer from "../components/logs/StructuredLogViewer";
import LogInsightSidebar from "../components/logs/LogInsightSidebar";
import type { ParsedLogLine, LogLevel } from "../utils/logUtils";
import { formatJsonWithSyntaxHighlighting } from "../utils/jsonFormatter";

export default function IterationDetail() {
  const { executionId, iterationId, batchId } = useParams<{ 
    executionId: string; 
    iterationId: string; 
    batchId?: string;
  }>();
  const navigate = useNavigate();
  const theme = useTheme();

  // File preview state
  const [previewFile, setPreviewFile] = useState<ExecutionFile | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  
  // Screenshot image loading and error states
  const [isImageLoading, setIsImageLoading] = useState(true);
  const [imageError, setImageError] = useState(false);
  
  // Live log streaming state
  const [isLiveStreaming, setIsLiveStreaming] = useState(false);
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);
  const [logSearchTerm, setLogSearchTerm] = useState("");
  const [logAutoScroll, setLogAutoScroll] = useState(true);
  const [minimumLogLevel, setMinimumLogLevel] = useState<LogLevel | null>(null);
  const [focusedLogRow, setFocusedLogRow] = useState<ParsedLogLine | null>(null);
  const [lastLogUpdatedAt, setLastLogUpdatedAt] = useState<number | null>(null);
  const [logViewMode, setLogViewMode] = useState<"structured" | "raw">("structured");
  
  // Video refresh state for live video streaming
  const videoRef = useRef<HTMLVideoElement>(null);
  const videoRefreshIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const videoEventListenersRef = useRef<{ 
    durationchange?: () => void; 
    timeupdate?: () => void;
    progress?: () => void;
    waiting?: () => void;
    canplay?: () => void;
  }>({});
  const [videoRefreshKey, setVideoRefreshKey] = useState<number>(0);

  // Action monitoring modal state
  const [isMonitoringModalOpen, setIsMonitoringModalOpen] = useState(false);
  
  // Download queue and notifications
  const { addDownload, downloads } = useDownloadQueue();
  const { snackbar, showSuccess, showError, showInfo, hideSnackbar } = useSnackbar();
  
  // Handle modal close - keep it super simple!
  const handleMonitoringModalClose = () => {
    setIsMonitoringModalOpen(false);
    // Let MUI Dialog and React handle all cleanup automatically
    // No DOM manipulation, no forced re-renders, no timeouts
  };

  // Data fetching hooks
  const {
    data: currentExecution,
    error: currentExecutionError,
    isLoading: currentExecutionLoading,
  } = useRun(executionId || "", {
    enableRealTimeSync: true,
  });

  const { data: progressData } = useExecutionProgress(executionId, {
    enabled: !!executionId,
    refetchIntervalMs: currentExecution?.status === "executing" ? 5000 : undefined,
  });

  // Get iteration from progress data using UUID
  const iteration = progressData?.iterations?.find(
    (iter) => iter.uuid === iterationId
  );

  // Get task information for the iteration
  const task = progressData?.tasks?.find(
    (task) => task.iterations.some((iter) => iter.uuid === iterationId)
  );

  const {
    data: filesData,
    isLoading: filesLoading,
    error: filesError,
  } = useIterationFiles(
    executionId,
    iteration?.uuid,
    "hierarchical",
    {
      enabled: !!iteration?.uuid,
      refetchIntervalMs: currentExecution?.status === "executing" ? 5000 : undefined,
    }
  );


  const iterKey = iteration ? `iteration_${iteration.iteration_number}` : `iteration_0`;
  const currentIteration = iteration; // Alias for clarity
  const isIterationLive =
    iteration?.status === "executing" || iteration?.status === "pending";
  const {
    actions: timelineActions,
    entries: timelineEntries,
    isLoading: timelineLoading,
  } = useTimeline(
    executionId,
    iteration?.uuid,
    {
      enabled: !!executionId && !!iteration?.uuid,
      refetchInterval: isIterationLive ? 3000 : undefined,
    }
  );
  const actionIndex = useMemo(
    () => buildScreenshotActionIndex(timelineActions),
    [timelineActions]
  );

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
  const matchedAction = useMemo(() => {
    if (!previewFile || previewFile.type !== "screenshot") {
      return null;
    }
    return findActionForScreenshot(previewFile, actionIndex);
  }, [previewFile, actionIndex]);
  const [previewVariant, setPreviewVariant] = useState<"file" | "before" | "after">(
    "file"
  );
  useEffect(() => {
    setPreviewVariant("file");
    // Reset image loading and error states when preview file changes
    setIsImageLoading(true);
    setImageError(false);
  }, [previewFile]);

  useEffect(() => {
    if (previewFile?.type === "log") {
      setLogSearchTerm("");
      setMinimumLogLevel(null);
      setFocusedLogRow(null);
      setLogAutoScroll(true);
      setLogViewMode("structured");
    }
  }, [previewFile?.type, previewFile?.path]);

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

      if (download.type === 'iteration' && download.url.includes(iterationId || '')) {
        if (download.status === 'completed') {
          processedDownloads.current.add(statusKey);
          showSuccess(`Download complete: ${download.filename}`);
        } else if (download.status === 'failed') {
          processedDownloads.current.add(statusKey);
          showError(`Download failed: ${download.error || 'Unknown error'}`);
        }
      }
    });
  }, [downloads, iterationId, showSuccess, showError, showInfo]);
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
  const resolvedScreenshotSrc = useMemo(() => {
    if (!previewFile || previewFile.type !== "screenshot") {
      return null;
    }
    if (
      previewVariant !== "file" &&
      matchedAction?.action &&
      iteration?.uuid &&
      executionId
    ) {
      return timelineApi.getScreenshotUrl(
        executionId,
        iteration.uuid,
        matchedAction.action.id,
        previewVariant
      );
    }
    return fileApi.getFileUrl(executionId!, previewFile.path);
  }, [
    previewFile,
    previewVariant,
    matchedAction,
    iteration?.uuid,
    executionId,
  ]);
  const relativeTimeLabel = useMemo(
    () => getRelativeTimeLabel(previewFile),
    [previewFile]
  );
  const showVariantToggle =
    variantOptions.length > 0 &&
    Boolean(matchedAction?.action && iteration?.uuid && executionId);
  const actionMetadataEntries = useMemo(() => {
    const actionMeta = matchedAction?.action?.metadata;
    if (!actionMeta) {
      return [];
    }
    return Object.entries(actionMeta)
      .filter(([key, value]) => Boolean(ACTION_METADATA_LABELS[key] && value !== null && value !== undefined && value !== ""))
      .map(([key, value]) => ({
        label: ACTION_METADATA_LABELS[key],
        value: formatMetadataValue(value),
      }));
  }, [matchedAction]);
  const getActionContextForFile = useCallback(
    (file: ExecutionFile) => findActionForScreenshot(file, actionIndex),
    [actionIndex]
  );
  const actionIntent = useMemo(() => {
    if (!matchedAction?.action || !timelineEntries?.length) {
      return null;
    }
    const actionSeq = matchedAction.action.sequence_index;
    const precedingIntent = [...timelineEntries]
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
  }, [matchedAction, timelineEntries]);

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

  // Auto-redirect if execution not found
  useEffect(() => {
    if (executionId && !currentExecutionLoading && currentExecutionError) {
      navigate("/runs");
    }
  }, [executionId, currentExecutionError, currentExecutionLoading, navigate]);

  // Cleanup polling interval on unmount
  useEffect(() => {
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
      if (videoRefreshIntervalRef.current) {
        clearInterval(videoRefreshIntervalRef.current);
        videoRefreshIntervalRef.current = null;
      }
    };
  }, [pollingInterval]);

  // Stop video refresh when execution completes
  useEffect(() => {
    if (currentExecution?.status !== "executing" && videoRefreshIntervalRef.current) {
      stopVideoRefresh();
    }
  }, [currentExecution?.status]);


  // Update document title
  useEffect(() => {
    if (task && iteration) {
      document.title = `${task.task_id}/Iteration ${iteration.iteration_number} - RL Gym Harness`;
    } else if (iteration && currentExecution) {
      const taskId = currentExecution.task_identifier || currentExecution.task_id || 'Unknown';
      document.title = `${taskId}/Iteration ${iteration.iteration_number} - RL Gym Harness`;
    } else if (iteration) {
      document.title = `Iteration ${iteration.iteration_number} - RL Gym Harness`;
    }
    
    // Cleanup on unmount
    return () => {
      document.title = 'RL Gym Harness';
    };
  }, [task, iteration, currentExecution]);

  useEffect(() => {
    if (!isIterationLive && isLiveStreaming) {
      setIsLiveStreaming(false);
      setLastLogUpdatedAt(null);
      if (pollingInterval) {
        clearInterval(pollingInterval);
        setPollingInterval(null);
      }
    }
  }, [isIterationLive, isLiveStreaming, pollingInterval]);

  if (!executionId || !iterationId) {
    return (
      <EmptyState
        icon={<MonitorIcon />}
        title="Invalid Parameters"
        description="Execution ID or iteration ID is missing"
      />
    );
  }

  if (currentExecutionLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "50vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!iteration) {
    return (
      <EmptyState
        icon={<MonitorIcon />}
        title="Iteration Not Found"
        description={`Iteration ${iterationId} not found for execution ${executionId}`}
      />
    );
  }

  const statusColor = getStatusColor(iteration.status as any) as
    | "default"
    | "primary"
    | "secondary"
    | "error"
    | "info"
    | "success"
    | "warning";

  const getFileIcon = (type: string, size = 24) => {
    const iconProps = { sx: { fontSize: size, color: theme.palette.text.secondary } };
    
    // File type specific icons
    switch (type) {
      case "screenshot":
        return <Box {...iconProps}>🖼️</Box>;
      case "video":
        return <Box {...iconProps}>🎥</Box>;
      case "log":
        return <Box {...iconProps}>📋</Box>;
      case "json":
        return <Box {...iconProps}>📄</Box>;
      case "text":
        return <Box {...iconProps}>📝</Box>;
      case "csv":
        return <Box {...iconProps}>📊</Box>;
      case "yaml":
        return <Box {...iconProps}>⚙️</Box>;
      case "xml":
        return <Box {...iconProps}>🏷️</Box>;
      case "html":
        return <Box {...iconProps}>🌐</Box>;
      case "other":
        return <Box {...iconProps}>📄</Box>;
      default:
        return <Box {...iconProps}>📄</Box>;
    }
  };

  // Load file content for preview
  const loadFileContent = async (file: ExecutionFile, isInitialLoad = true) => {
    if (isInitialLoad) {
      setIsLoadingFile(true);
      setFileError(null);
    }

    try {
      const response = await fetch(fileApi.getFileUrl(executionId!, file.path));
      if (!response.ok) {
        throw new Error(`Failed to load file: ${response.statusText}`);
      }
      
      const content = await response.text();
      setFileContent(content);
      if (file.type === "log") {
        setLastLogUpdatedAt(Date.now());
      }
    } catch (error) {
      setFileError(error instanceof Error ? error.message : "Failed to load file");
    } finally {
      if (isInitialLoad) {
        setIsLoadingFile(false);
      }
    }
  };

  // Start live streaming for log files
  const startLiveStreaming = (file: ExecutionFile) => {
    if (file.type === "log") {
      setIsLiveStreaming(true);
      setLastLogUpdatedAt(Date.now());
      
      // Clear any existing interval
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
      
      // Set up polling every 10 seconds
      const interval = setInterval(() => {
        loadFileContent(file, false);
      }, 10000);
      
      setPollingInterval(interval);
    }
  };

  // Stop live streaming
  const stopLiveStreaming = () => {
    setIsLiveStreaming(false);
    setLastLogUpdatedAt(null);
    if (pollingInterval) {
      clearInterval(pollingInterval);
      setPollingInterval(null);
    }
  };

  // Helper to check if file is a video
  const isVideoFile = (file: ExecutionFile): boolean => {
    const name = file.name.toLowerCase();
    return (
      name.endsWith(".webm") ||
      name.endsWith(".mp4") ||
      name.endsWith(".mov") ||
      name.endsWith(".avi") ||
      name.endsWith(".mkv") ||
      name.endsWith(".flv")
    );
  };

  // Start video refresh for live streaming (when execution is still running)
  // For progressive webm files, we monitor buffered ranges and automatically continue playback
  const startVideoRefresh = (file: ExecutionFile) => {
    if (!isVideoFile(file)) return;
    
    // Clear any existing interval and listeners
    stopVideoRefresh();

    // Only set up listeners if execution is still running
    if (currentExecution?.status === "executing" && videoRef.current) {
      const video = videoRef.current;
      
      // Get the end of buffered data
      const getBufferedEnd = (): number => {
        if (!video.buffered.length) return 0;
        return video.buffered.end(video.buffered.length - 1);
      };

      // Check if we need to seek forward to continue playback
      const checkAndContinuePlayback = () => {
        if (!video || currentExecution?.status !== "executing") return;
        
        const bufferedEnd = getBufferedEnd();
        const currentTime = video.currentTime;
        const duration = video.duration;
        
        // If we're within 0.5 seconds of buffered end, seek forward to catch new data
        if (bufferedEnd > 0 && bufferedEnd - currentTime < 0.5 && duration > bufferedEnd) {
          // New data might be available, seek slightly ahead
          video.currentTime = Math.min(bufferedEnd, duration);
        }
        
        // If video is paused but we have buffered data ahead, resume
        if (video.paused && bufferedEnd > currentTime + 0.1) {
          video.play().catch(() => {
            // Ignore play errors (autoplay restrictions)
          });
        }
      };

      // Listen for progress events (new data loaded)
      const handleProgress = () => {
        if (video && currentExecution?.status === "executing") {
          checkAndContinuePlayback();
        }
      };

      // Listen for waiting events (video paused waiting for data)
      const handleWaiting = () => {
        if (video && currentExecution?.status === "executing") {
          // When video is waiting, check if new data is available
          setTimeout(() => {
            checkAndContinuePlayback();
          }, 100);
        }
      };

      // Listen for canplay events (enough data to play)
      const handleCanPlay = () => {
        if (video && currentExecution?.status === "executing" && video.paused) {
          // If video was paused waiting for data, resume now
          video.play().catch(() => {
            // Ignore play errors
          });
        }
      };

      // Listen for duration changes (new content added to progressive webm)
      const handleDurationChange = () => {
        if (video && currentExecution?.status === "executing") {
          checkAndContinuePlayback();
        }
      };

      // Listen for time updates to check if we're near the end of buffered data
      const handleTimeUpdate = () => {
        if (video && currentExecution?.status === "executing") {
          const bufferedEnd = getBufferedEnd();
          const currentTime = video.currentTime;
          
          // If we're very close to the end of buffered data, check for new data
          if (bufferedEnd > 0 && bufferedEnd - currentTime < 0.3) {
            checkAndContinuePlayback();
          }
        }
      };

      video.addEventListener('progress', handleProgress);
      video.addEventListener('waiting', handleWaiting);
      video.addEventListener('canplay', handleCanPlay);
      video.addEventListener('durationchange', handleDurationChange);
      video.addEventListener('timeupdate', handleTimeUpdate);

      // Store listeners for cleanup
      videoEventListenersRef.current = {
        progress: handleProgress,
        waiting: handleWaiting,
        canplay: handleCanPlay,
        durationchange: handleDurationChange,
        timeupdate: handleTimeUpdate,
      };

      // Store interval reference for cleanup - periodically check buffered ranges
      videoRefreshIntervalRef.current = setInterval(() => {
        if (currentExecution?.status !== "executing") {
          stopVideoRefresh();
          return;
        }
        
        if (video) {
          checkAndContinuePlayback();
        }
      }, 500); // Check every 500ms for new buffered data
    }
  };

  // Stop video refresh
  const stopVideoRefresh = () => {
    // Clear interval
    if (videoRefreshIntervalRef.current) {
      clearInterval(videoRefreshIntervalRef.current);
      videoRefreshIntervalRef.current = null;
    }
    // Remove event listeners
    if (videoRef.current && videoEventListenersRef.current) {
      const video = videoRef.current;
      const listeners = videoEventListenersRef.current;
      if (listeners.progress) {
        video.removeEventListener('progress', listeners.progress);
      }
      if (listeners.waiting) {
        video.removeEventListener('waiting', listeners.waiting);
      }
      if (listeners.canplay) {
        video.removeEventListener('canplay', listeners.canplay);
      }
      if (listeners.durationchange) {
        video.removeEventListener('durationchange', listeners.durationchange);
      }
      if (listeners.timeupdate) {
        video.removeEventListener('timeupdate', listeners.timeupdate);
      }
      videoEventListenersRef.current = {};
    }
  };

const handleToggleLogStreaming = () => {
  if (!previewFile || previewFile.type !== "log") return;
  if (isLiveStreaming) {
    stopLiveStreaming();
  } else {
    startLiveStreaming(previewFile);
    loadFileContent(previewFile, false);
  }
};

const handleRefreshLog = () => {
  if (previewFile && previewFile.type === "log") {
    loadFileContent(previewFile, false);
  }
};


  const onFilePreview = (file: ExecutionFile) => {
    setPreviewFile(file);
    // Load content for text-based files
    if (["json", "log", "text", "csv", "yaml", "xml", "html"].includes(file.type)) {
      loadFileContent(file);
      
      // Start live streaming for log files
      if (file.type === "log") {
        startLiveStreaming(file);
      }
    }
    // Start video refresh for video files if execution is still running
    if (isVideoFile(file)) {
      // Set initial cache-busting parameter (only once, won't change during playback)
      setVideoRefreshKey(Date.now());
      // Start refresh after a short delay to allow video element to mount
      setTimeout(() => {
        startVideoRefresh(file);
      }, 500);
    }
  };

  const handleDownload = (file: ExecutionFile) => {
    const link = document.createElement("a");
    link.href = fileApi.getFileUrl(executionId!, file.path);
    link.download = file.name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const closePreview = () => {
    stopLiveStreaming();
    stopVideoRefresh();
    setPreviewFile(null);
    setFileContent("");
    setFileError(null);
    setIsLoadingFile(false);
    setVideoRefreshKey(0);
    setLogSearchTerm("");
    setMinimumLogLevel(null);
    setFocusedLogRow(null);
    setLastLogUpdatedAt(null);
    setLogAutoScroll(true);
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
        <Box sx={{ p: 3 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
            <IconButton 
              onClick={() => {
                // Use batch-aware URL if batch context is available
                if (batchId) {
                  navigate(`/batches/${batchId}/executions/${executionId}/monitor`);
                } else {
                  navigate(`/executions/${executionId}/monitor`);
                }
              }} 
              sx={{ mr: 1 }}
            >
              <BackIcon />
            </IconButton>
            <MonitorIcon sx={{ fontSize: 32 }} />
            <Box sx={{ flexGrow: 1 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 1 }}>
                <Typography variant="h4" component="h1" gutterBottom>
                  {currentExecution?.execution_type === "playground" 
                    ? `Iteration ${iteration.iteration_number}`
                    : `${task?.task_id || currentExecution?.task_identifier || currentExecution?.task_id || 'Unknown Task'}/Iteration ${iteration.iteration_number}`}
                </Typography>
                <Button
                  variant="contained"
                  startIcon={<LiveMonitorIcon />}
                  onClick={() => setIsMonitoringModalOpen(true)}
                  sx={{
                    bgcolor: theme.palette.primary.main,
                    "&:hover": {
                      bgcolor: theme.palette.primary.dark,
                    },
                  }}
                >
                  🎬 Live Monitor
                </Button>
                <Box sx={{ ml: 'auto' }}>
                  <Tooltip title="Download all iteration assets as ZIP archive">
                    <span>
                      <IconButton
                        onClick={async () => {
                          if (!executionId || !iterationId || !currentExecution || !currentIteration) return;
                          
                          try {
                            const url = fileApi.downloadIteration(executionId, iterationId);
                            const filename = currentExecution.execution_folder_name && currentIteration.iteration_number
                              ? `${currentExecution.execution_folder_name}_iteration_${currentIteration.iteration_number}.zip`
                              : `iteration_${iterationId}.zip`;

                            // Get token for authentication
                            const token = getAuthToken() || undefined;
                            
                            await addDownload('iteration', url, filename, token);
                          } catch (error) {
                            showError(`Failed to start download: ${error instanceof Error ? error.message : 'Unknown error'}`);
                          }
                        }}
                        disabled={!executionId || !iterationId}
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
                        {executionId && iterationId && downloads.some(
                          d => d.type === 'iteration' && d.url.includes(`/executions/${executionId}/iterations/${iterationId}/download`) && (d.status === 'downloading' || d.status === 'pending')
                        ) ? (
                          <CircularProgress size={24} sx={{ color: 'white' }} />
                        ) : (
                          <CloudDownloadIcon />
                        )}
                      </IconButton>
                    </span>
                  </Tooltip>
                </Box>
              </Box>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Chip
                  label={getStatusDisplayLabel(iteration.status, currentExecution?.execution_type)}
                  color={statusColor}
                  size="small"
                />
                {iteration.execution_time_seconds && (
                  <Chip
                    label={`${iteration.execution_time_seconds}s`}
                    variant="outlined"
                    size="small"
                  />
                )}
                {iteration.started_at && (
                  <Typography variant="body2" color="text.secondary">
                    Started: {new Date(iteration.started_at).toLocaleString()}
                  </Typography>
                )}
              </Box>
            </Box>
          </Box>
        </Box>
      </Box>

      {/* Content */}
      <Box sx={{ flex: 1, p: 3 }}>
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Execution Details
          </Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 2 }}>
            <Box>
              <Typography variant="body2" color="text.secondary">Status</Typography>
              <Chip 
                label={getStatusDisplayLabel(iteration.status, currentExecution?.execution_type)} 
                color={statusColor} 
                size="small" 
              />
            </Box>
            {iteration.execution_time_seconds && (
              <Box>
                <Typography variant="body2" color="text.secondary">Execution Time</Typography>
                <Typography variant="body1">{iteration.execution_time_seconds}s</Typography>
              </Box>
            )}
            {iteration.started_at && (
              <Box>
                <Typography variant="body2" color="text.secondary">Started At</Typography>
                <Typography variant="body1">{new Date(iteration.started_at).toLocaleString()}</Typography>
              </Box>
            )}
            {iteration.completed_at && (
              <Box>
                <Typography variant="body2" color="text.secondary">Completed At</Typography>
                <Typography variant="body1">{new Date(iteration.completed_at).toLocaleString()}</Typography>
              </Box>
            )}
          </Box>

          <VerificationInsightsTabs
            verificationComments={iteration.verification_comments || undefined}
            evalInsights={iteration.eval_insights || undefined}
          />
        </Paper>

        {/* Files Browser */}
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>
            Files
          </Typography>
          {filesError ? (
            <Alert severity="error">
              <Typography variant="h6" gutterBottom>
                Error Loading Files
              </Typography>
              <Typography variant="body2">
                {(filesError as any)?.status === 404 
                  ? `Iteration folder not found. The iteration may not have been executed yet or the files may not be available.`
                  : `Failed to load files: ${filesError.message || 'Unknown error'}`
                }
              </Typography>
            </Alert>
          ) : filesData ? (
            <IterationFileBrowser
              executionId={executionId}
              iterKey={iterKey}
              filesData={filesData}
              onPreviewFile={onFilePreview}
              onDownloadFile={handleDownload}
              getFileIcon={getFileIcon}
              getActionContext={getActionContextForFile}
            />
          ) : filesLoading ? (
            <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", py: 4 }}>
              <CircularProgress />
              <Typography sx={{ ml: 2 }}>Loading files...</Typography>
            </Box>
          ) : (
            <Alert severity="info">No files available for this iteration</Alert>
          )}
        </Paper>
      </Box>

      {/* Action Monitoring Modal */}
      <ActionMonitoringModal
        open={isMonitoringModalOpen}
        onClose={handleMonitoringModalClose}
        executionId={executionId}
        iterationId={iterationId}
        iterationNumber={iteration.iteration_number}
        isLiveIteration={iteration.status === "executing"}
      />

      {/* File Preview Modal */}
      {previewFile && (
        <Dialog
          open
          onClose={closePreview}
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
              gap: 2,
            }}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, flex: 1, minWidth: 0 }}>
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
            <Box
              sx={{
                display: "flex",
                alignItems: "flex-start",
                gap: 2,
              }}
            >
              {iteration && previewFile.type === "log" && (
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 1.5,
                    flexWrap: "wrap",
                    width: "100%",
                  }}
                >
                  <Chip
                    size="small"
                    label={getStatusDisplayLabel(iteration.status)}
                    color={getStatusColor(iteration.status)}
                  />
                  <Box sx={{ flexGrow: 1 }} />
                  <ToggleButtonGroup
                    size="small"
                    exclusive
                    value={logViewMode}
                    onChange={(_, value) => {
                      if (value) {
                        setLogViewMode(value);
                        if (value === "raw") {
                          setFocusedLogRow(null);
                        }
                      }
                    }}
                  >
                    <ToggleButton value="structured">
                      <ViewListIcon fontSize="small" sx={{ mr: 0.5 }} />
                      Structured
                    </ToggleButton>
                    <ToggleButton value="raw">
                      <CodeIcon fontSize="small" sx={{ mr: 0.5 }} />
                      Raw
                    </ToggleButton>
                  </ToggleButtonGroup>
                </Box>
              )}
              <IconButton onClick={closePreview}>
                <CloseIcon />
              </IconButton>
            </Box>
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
            ) : isVideoFile(previewFile) ? (
              <Box 
                sx={{ 
                  display: "flex",
                  justifyContent: "center",
                  alignItems: "center",
                  minHeight: "400px",
                  width: "100%"
                }}
              >
                <video
                  ref={videoRef}
                  controls
                  preload="auto"
                  style={{ 
                    maxWidth: "100%", 
                    maxHeight: "70vh",
                    width: "auto",
                    height: "auto"
                  }}
                  src={`${fileApi.getFileUrl(executionId!, previewFile.path)}${fileApi.getFileUrl(executionId!, previewFile.path).includes('?') ? '&' : '?'}_nocache=1&_t=${videoRefreshKey || Date.now()}`}
                  onLoadedMetadata={() => {
                    // When metadata loads initially, video is ready
                    // For live streaming, durationchange events will handle new content
                  }}
                  onDurationChange={() => {
                    // When duration changes (new content added), check if we should seek forward
                    if (videoRef.current && currentExecution?.status === "executing") {
                      const video = videoRef.current;
                      // If user is near the end (< 2 seconds), seek to new end to continue watching
                      const wasNearEnd = video.duration > 0 && (video.duration - video.currentTime < 2);
                      if (wasNearEnd && video.duration > video.currentTime) {
                        // Seek to near the end to continue watching new content
                        video.currentTime = Math.max(0, video.duration - 1);
                      }
                    }
                  }}
                  onError={(e) => {
                    // If video fails to load, it might still be generating
                    // Try to reload after a short delay
                    const videoElement = e.currentTarget;
                    setTimeout(() => {
                      if (videoElement && currentExecution?.status === "executing") {
                        setVideoRefreshKey(Date.now());
                        videoElement.load();
                      }
                    }, 2000);
                  }}
                >
                  Your browser does not support the video tag.
                </video>
              </Box>
            ) : previewFile.type === "json" ? (
              <Box sx={{ height: "500px" }}>
                {isLoadingFile ? (
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
                ) : fileError ? (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {fileError}
                  </Alert>
                ) : (
                  <Box
                    component="pre"
                    sx={{
                      backgroundColor: theme.palette.mode === "dark" ? "#1e1e1e" : "#f8f8f8",
                      padding: 2,
                      borderRadius: 1,
                      overflow: "auto",
                      height: "100%",
                      fontFamily: "'Fira Code', 'Monaco', 'Consolas', monospace",
                      fontSize: "0.875rem",
                      lineHeight: 1.5,
                      whiteSpace: "pre",
                      wordBreak: "break-word",
                      border: `1px solid ${theme.palette.divider}`,
                      color: theme.palette.mode === "dark" ? "#d4d4d4" : "#333",
                      "& .json-key": {
                        color: theme.palette.mode === "dark" ? "#9cdcfe" : "#0451a5",
                        fontWeight: 600,
                      },
                      "& .json-string": {
                        color: theme.palette.mode === "dark" ? "#ce9178" : "#0b8235",
                      },
                      "& .json-number": {
                        color: theme.palette.mode === "dark" ? "#b5cea8" : "#098658",
                      },
                      "& .json-boolean": {
                        color: theme.palette.mode === "dark" ? "#569cd6" : "#0000ff",
                        fontWeight: 600,
                      },
                      "& .json-null": {
                        color: theme.palette.mode === "dark" ? "#808080" : "#808080",
                        fontStyle: "italic",
                      },
                      "& .json-bracket": {
                        color: theme.palette.mode === "dark" ? "#d4d4d4" : "#000000",
                        fontWeight: 600,
                      },
                      "& .json-colon": {
                        color: theme.palette.mode === "dark" ? "#d4d4d4" : "#000000",
                      },
                      "& .json-comma": {
                        color: theme.palette.mode === "dark" ? "#d4d4d4" : "#000000",
                      },
                    }}
                    dangerouslySetInnerHTML={{
                      __html: formatJsonWithSyntaxHighlighting(fileContent)
                    }}
                  />
                )}
              </Box>
            ) : previewFile.type === "log" ? (
              <Box sx={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}>
                {isLoadingFile && !fileContent ? (
                  <Box
                    sx={{
                      display: "flex",
                      justifyContent: "center",
                      alignItems: "center",
                      height: "100%",
                    }}
                  >
                    <CircularProgress />
                    <Typography sx={{ ml: 2 }}>Loading log...</Typography>
                  </Box>
                ) : fileError ? (
                  <Alert severity="error" sx={{ mb: 2, flexShrink: 0 }}>
                    {fileError}
                  </Alert>
                ) : logViewMode === "raw" ? (
                  <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                    <Box
                      component="pre"
                      sx={{
                        backgroundColor: theme.palette.mode === "dark" 
                          ? "#1e1e1e" 
                          : "#1e1e1e",
                        color: theme.palette.mode === "dark"
                          ? "#d4d4d4"
                          : "#d4d4d4",
                        padding: 2,
                        borderRadius: 1,
                        overflow: "auto",
                        flex: 1,
                        fontFamily: "monospace",
                        fontSize: "0.875rem",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        border: `1px solid ${theme.palette.divider}`,
                      }}
                    >
                      {fileContent}
                    </Box>
                  </Box>
                ) : (
                  <>
                    <Box
                      sx={{
                        display: "grid",
                        gridTemplateColumns: focusedLogRow
                          ? { xs: "1fr", lg: "1fr 320px" }
                          : "1fr",
                        gap: 2,
                        minHeight: 360,
                        height: { xs: "85vh", lg: "80vh" },
                        maxHeight: { xs: "85vh", lg: "80vh" },
                        overflow: "hidden",
                        mb: 2,
                        flex: 1,
                        transition: "grid-template-columns 0.2s ease-in-out",
                      }}
                    >
                      <Box sx={{ minHeight: 0, height: "100%" }}>
                        <StructuredLogViewer
                          logContent={fileContent}
                          isStreaming={isLiveStreaming}
                          onToggleStreaming={handleToggleLogStreaming}
                          onRefresh={handleRefreshLog}
                          lastUpdatedAt={lastLogUpdatedAt}
                          currentLogFileName={previewFile.name}
                          autoScroll={logAutoScroll}
                          onAutoScrollChange={setLogAutoScroll}
                          onRowFocus={setFocusedLogRow}
                          minimumLevel={minimumLogLevel}
                          onMinimumLevelChange={setMinimumLogLevel}
                          searchTerm={logSearchTerm}
                          onSearchTermChange={setLogSearchTerm}
                          isSyncing={isLiveStreaming && isLoadingFile}
                          executionStatus={currentExecution?.status}
                        />
                      </Box>
                      {focusedLogRow && (
                        <Box
                          sx={{
                            display: { xs: "none", lg: "block" },
                            minHeight: 0,
                            height: "100%",
                          }}
                        >
                          <LogInsightSidebar
                            focusedRow={focusedLogRow}
                            iterationDetails={iteration}
                            timelineActions={timelineActions}
                            timelineEntries={timelineEntries}
                            timelineLoading={timelineLoading}
                            onClearFocus={() => setFocusedLogRow(null)}
                          />
                        </Box>
                      )}
                    </Box>
                    {focusedLogRow && (
                      <Box sx={{ display: { xs: "block", lg: "none" }, mt: 2 }}>
                        <LogInsightSidebar
                          focusedRow={focusedLogRow}
                          iterationDetails={iteration}
                          timelineActions={timelineActions}
                          timelineEntries={timelineEntries}
                          timelineLoading={timelineLoading}
                          onClearFocus={() => setFocusedLogRow(null)}
                        />
                      </Box>
                    )}
                  </>
                )}
              </Box>
            ) : ["text", "csv", "yaml", "xml", "html"].includes(previewFile.type) ? (
              <Box sx={{ height: "500px" }}>
                {isLoadingFile ? (
                  <Box
                    sx={{
                      display: "flex",
                      justifyContent: "center",
                      alignItems: "center",
                      height: "100%",
                    }}
                  >
                    <CircularProgress />
                    <Typography sx={{ ml: 2 }}>Loading file...</Typography>
                  </Box>
                ) : fileError ? (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {fileError}
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
                    {fileContent}
                  </Box>
                )}
              </Box>
            ) : (
              <Typography>
                Preview not available for {previewFile.type} files. Use download to view.
              </Typography>
            )}
          </DialogContent>
          {(previewFile.type !== "log" || logViewMode === "raw") && (
            <DialogActions>
              <Button onClick={closePreview}>Close</Button>
              <Button
                variant="contained"
                color="primary"
                onClick={() => handleDownload(previewFile)}
                sx={{
                  minWidth: 120,
                }}
              >
                Download
              </Button>
            </DialogActions>
          )}
        </Dialog>
      )}

      {/* Notification Snackbar - at page level so it's always visible */}
      <NotificationSnackbar
        snackbar={snackbar}
        onClose={hideSnackbar}
      />
    </Box>
  );
}
