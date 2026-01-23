import {
  Box,
  Button,
  Container,
  Divider,
  Typography,
  Alert,
  CircularProgress,
  Fab,
  Tooltip,
  IconButton,
} from "@mui/material";
import {
  Download as DownloadIcon,
  CloudDownload as CloudDownloadIcon,
  Refresh as RefreshIcon,
  Warning as WarningIcon,
  ArrowUpward as ArrowUpwardIcon,
} from "@mui/icons-material";
import ViewToggle from "../components/ViewToggle";
import { useParams, useNavigate } from "react-router-dom";
import {
  useBatch,
  useBatchExecutions,
  useBatchIterationSummary,
} from "../hooks/useBatches";
import { useGyms } from "../hooks/useGyms";
import { useTasks } from "../hooks/useTasks";
import { batchApi, executionApi, getAuthToken } from "../services/api";
import { useState, useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useFiltering, type FilterCategory } from "../hooks/useFiltering";
import { useSorting } from "../hooks/useSorting";
import FilterMenu from "../components/FilterMenu";
import SortMenu from "../components/SortMenu";
import RunsTable from "../components/RunsTable";
import RunCard from "../components/RunCard";
import BatchOverallSummary from "../components/BatchOverallSummary";
import BatchInsightsTabs from "../components/BatchInsightsTabs";
import BatchRunsSkeleton from "../components/BatchRunsSkeleton";
import { useViewToggle } from "../hooks/useViewToggle";
import { useTheme } from "@mui/material/styles";
import { useLocation } from "react-router-dom";
import type { Execution } from "../types";
import { useDownloadQueue } from "../hooks/useDownloadQueue";
import { useSnackbar } from "../hooks/useSnackbar";

export default function BatchRuns() {
  const { batchId } = useParams<{ batchId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const theme = useTheme();
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [isRerunning, setIsRerunning] = useState(false);
  const [isTerminating, setIsTerminating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportReadinessInfo, setReportReadinessInfo] = useState<string | null>(null);
  const [isScrolled, setIsScrolled] = useState(false);

  // Download queue and notifications
  const { addDownload, downloads } = useDownloadQueue();
  const { showSuccess, showError, showInfo } = useSnackbar();

  // Refs for scroll detection
  const headerRef = useRef<HTMLDivElement>(null);
  const stickyHeaderRef = useRef<HTMLDivElement>(null);

  // View toggle state
  const { view, setView, isCardView } = useViewToggle("card");

  // Scroll threshold - adjust based on header height
  const SCROLL_THRESHOLD = 200;

  // Check if drawer is visible (not on report preview page)
  const hideDrawer = location.pathname.includes("/report-preview");
  const drawerWidth = 240;
  const appBarHeight = theme.mixins.toolbar.minHeight || 64;
  
  // Fetch report readiness status
  const { data: reportReadiness } = useQuery({
    queryKey: ["batch-report-readiness", batchId],
    queryFn: () => batchApi.checkReportReadiness(batchId || ""),
    enabled: !!batchId,
    refetchInterval: 10000, // Check readiness every 10 seconds
  });

  const {
    data: batch,
    isLoading: batchLoading,
    error: batchError,
  } = useBatch(batchId || "");
  const {
    data: executions = [],
    isLoading: executionsLoading,
    error: executionsError,
  } = useBatchExecutions(batchId || "");
  const { data: gyms = [] } = useGyms();
  const { data: tasks = [] } = useTasks();

  // Fetch batch iteration summary
  const {
    data: iterationSummary,
    isLoading: summaryLoading,
    error: summaryError,
  } = useBatchIterationSummary(batchId || "");

  // Batch status is now computed in real-time, no need for manual updates

  const isLoading = batchLoading || executionsLoading || summaryLoading;
  const apiError = batchError || executionsError || summaryError;

  // Determine if rerun button should be shown
  const shouldShowRerunButton = () => {
    if (!executions || executions.length === 0) return false;

    // Check if all executions are in final states (not pending or executing)
    const allExecutionsFinal = executions.every(
      (execution) =>
        execution.status !== "pending" && execution.status !== "executing"
    );

    // Check if there are any failed iterations (crashed, timeout, or failed without directory)
    const hasFailedIterations = executions.some(
      (execution) =>
        execution.status === "crashed" || execution.status === "timeout"
    );
    
    // Also check if there are failed tasks without directories (from report readiness)
    const hasFailedWithoutDirectory = (reportReadiness?.counts?.failed_without_directory || 0) > 0;

    return allExecutionsFinal && (hasFailedIterations || hasFailedWithoutDirectory);
  };

  const primaryExecution = executions[0];
  const primaryGymName = primaryExecution
    ? gyms?.find((g) => g.uuid === primaryExecution.gym_id)?.name
    : undefined;
  const primaryTaskId = primaryExecution
    ? (() => {
        const matchingTask = Array.isArray(tasks)
          ? tasks.find(
              (t) =>
                t.uuid === primaryExecution.task_id ||
                t.task_id === primaryExecution.task_id
            )
          : undefined;
        return matchingTask?.task_id || primaryExecution.task_id || undefined;
      })()
    : undefined;

  const displayTaskId = primaryTaskId || undefined;

  // Data processing pipeline: filter -> sort
  const { filterCategories } = useMemo(() => {
    const statuses = [...new Set(executions?.map((execution) => execution.status) || [])];
    const models = [...new Set(executions?.map((execution) => execution.model) || [])];
    
    // Get unique task identifiers from executions
    const taskIdentifiers = [
      ...new Set(
        executions
          ?.map((execution) => execution.task_identifier || execution.task_id)
          .filter((id): id is string => Boolean(id)) || []
      ),
    ].sort();

    const categories: FilterCategory<Execution>[] = [
      { key: "status", label: "Status", options: statuses },
      { key: "model", label: "Model", options: models },
      {
        key: "task",
        label: "Task",
        options: taskIdentifiers,
        getValue: (execution: Execution) => execution.task_identifier || execution.task_id || "",
      },
    ];

    return { filterCategories: categories };
  }, [executions, tasks]);

  const { filteredItems, activeFilters, toggleFilter, clearFilters } =
    useFiltering(executions || [], filterCategories);

  const sortOptions = [
    { value: "status", label: "Sort by Status" },
    { value: "model", label: "Sort by Model" },
    { 
      value: "execution_time", 
      label: "Sort by Execution Time",
      getValue: (execution: Execution) => {
        // Use backend-calculated duration if available
        if (execution.execution_duration_seconds != null) {
          return execution.execution_duration_seconds;
        }
        // Fallback: calculate from timestamps (for backwards compatibility)
        const created = new Date(execution.created_at).getTime();
        if (isNaN(created)) return 0;
        
        const updated = execution.status === "pending" || execution.status === "executing"
          ? Date.now()
          : new Date(execution.updated_at).getTime();
        
        if (isNaN(updated)) return 0;
        
        return Math.max(0, (updated - created) / 1000);
      }
    },
  ];

  const {
    sortedItems: sortedRuns,
    requestSort,
    sortConfig,
  } = useSorting(filteredItems || [], sortOptions, {
    key: "created_at",
    direction: "desc",
  });

  // Scroll detection
  useEffect(() => {
    const handleScroll = () => {
      const scrollY = window.scrollY || window.pageYOffset;
      setIsScrolled(scrollY > SCROLL_THRESHOLD);
    };

    // Initial check
    handleScroll();

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [SCROLL_THRESHOLD]);

  // Update report readiness info when readiness changes
  useEffect(() => {
    if (reportReadiness && !reportReadiness.ready) {
      setReportReadinessInfo(reportReadiness.reason);
    } else {
      setReportReadinessInfo(null);
    }
  }, [reportReadiness]);

  const handleGenerateReport = async () => {
    if (!batchId) return;

    // Check report readiness before attempting to generate report
    if (!reportReadiness?.ready) {
      setError(
        reportReadiness?.reason || "Report is not ready yet. Please wait for all tasks to complete."
      );
      return;
    }

    setIsGeneratingReport(true);
    setError(null);

    try {
      const report = await batchApi.generateReport(batchId);

      // Use the same download function as executions endpoint for consistency
      await executionApi.downloadExport(report.download_url);
    } catch (error) {
      setError("Failed to generate batch report");
      console.error("Error generating batch report:", error);
    } finally {
      setIsGeneratingReport(false);
    }
  };

  const handleDownloadBatch = async () => {
    if (!batchId || !batch) return;

    try {
      const url = batchApi.downloadBatch(batchId);
      const sanitizedBatchName = batch.name.replace(/ /g, "_").replace(/\//g, "-").replace(/\\/g, "-");
      const filename = `batch_${sanitizedBatchName}.zip`;

      // Get token for authentication
      const token = getAuthToken() || undefined;
      
      await addDownload('batch', url, filename, token);
    } catch (error) {
      showError(`Failed to start download: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  // Check if this specific batch is downloading (for visual feedback only)
  // Include both 'pending' and 'downloading' status, and ensure batchId exists
  const isThisBatchDownloading = batchId ? downloads.some(
    d => d.type === 'batch' && d.url.includes(`/batches/${batchId}/download`) && (d.status === 'downloading' || d.status === 'pending')
  ) : false;

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

      if (download.type === 'batch') {
        if (download.status === 'completed') {
          processedDownloads.current.add(statusKey);
          showSuccess(`Download complete: ${download.filename}`);
        } else if (download.status === 'failed') {
          processedDownloads.current.add(statusKey);
          showError(`Download failed: ${download.error || 'Unknown error'}`);
        }
      }
    });
  }, [downloads, showSuccess, showError, showInfo]);

  const handleRerunFailedIterations = async () => {
    if (!batchId) return;

    setIsRerunning(true);
    setError(null);

    try {
      const result = await batchApi.rerunFailedIterations(batchId);

      // Show success message
      setError(null);

      // Show success message
      const successMessage = `Successfully queued ${result.rerun_iterations} failed iterations for rerun.`;
      if (
        result.failed_cleanups > 0 ||
        result.failed_resets > 0 ||
        result.failed_queues > 0
      ) {
        const failureDetails = [];
        if (result.failed_cleanups > 0)
          failureDetails.push(`${result.failed_cleanups} cleanup failures`);
        if (result.failed_resets > 0)
          failureDetails.push(`${result.failed_resets} reset failures`);
        if (result.failed_queues > 0)
          failureDetails.push(`${result.failed_queues} queue failures`);
        alert(
          `${successMessage}\n\nNote: ${failureDetails.join(", ")} occurred.`
        );
      } else {
        alert(successMessage);
      }
    } catch (error) {
      setError("Failed to rerun failed iterations");
      console.error("Error rerunning failed iterations:", error);
    } finally {
      setIsRerunning(false);
    }
  };

  const handleTerminateBatch = async () => {
    console.log("DEBUG: handleTerminateBatch called, batchId:", batchId);
    if (!batchId) {
      console.log("DEBUG: No batchId, returning");
      return;
    }
    if (!window.confirm("Terminate this batch immediately? This will crash running iterations and clean up resources.")) {
      console.log("DEBUG: User cancelled termination");
      return;
    }

    console.log("DEBUG: Starting termination for batchId:", batchId);
    setIsTerminating(true);
    setError(null);
    try {
      console.log("DEBUG: Calling batchApi.terminate");
      const result = await batchApi.terminate(batchId);
      console.log("DEBUG: Terminate result:", result);
      alert(result.message);
      // Refresh data after termination
      window.location.reload();
    } catch (e) {
      console.error("DEBUG: Error terminating batch:", e);
      setError("Failed to terminate batch");
    } finally {
      setIsTerminating(false);
    }
  };

  const handleViewExecution = (execution: Execution) => {
    // Use batch-aware URL to preserve navigation context
    navigate(`/batches/${batchId}/executions/${execution.uuid}/monitor`);
  };

  const handleEditExecution = (execution: Execution) => {
    // For batch executions, editing is disabled
    console.log("Edit execution disabled for batch runs:", execution.uuid);
  };

  const handlePreviewReport = () => {
    // Check report readiness before preview
    if (!reportReadiness?.ready) {
      setError(
        reportReadiness?.reason || "Report is not ready yet. Please wait for all tasks to complete."
      );
      return;
    }
    
    if (batchId) {
      window.open(`/batches/${batchId}/report-preview`, "_blank");
    }
  };

  const handleScrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  };

  if (isLoading) {
    return (
      <Container maxWidth="xl">
        <BatchRunsSkeleton />
      </Container>
    );
  }

  if (apiError) {
    return (
      <Container maxWidth="xl">
        <Box sx={{ py: 4 }}>
          <Alert severity="error">
            {(apiError as Error)?.message || "An error occurred"}
          </Alert>
        </Box>
      </Container>
    );
  }

  return (
    <>
      {/* Full-width sticky header that appears when scrolled */}
      <Box
        ref={stickyHeaderRef}
        sx={{
          position: "fixed",
          top: appBarHeight,
          left: hideDrawer ? 0 : drawerWidth,
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
              {batch?.name || "Batch Runs"}
            </Typography>
            {(primaryGymName || displayTaskId) && (
              <Typography
                variant="caption"
                color="text.secondary"
                noWrap
              >
                {[
                  primaryGymName && `Gym: ${primaryGymName}`,
                  displayTaskId && `Task ID: ${displayTaskId}`,
                ]
                  .filter(Boolean)
                  .join(" • ")}
              </Typography>
            )}
          </Box>

          {/* Controls in sticky header */}
          <Box display="flex" gap={1.5} alignItems="center" flexWrap="wrap" sx={{ flex: "0 0 auto" }}>
            <FilterMenu
              options={filterCategories}
              activeFilters={activeFilters}
              onFilterToggle={toggleFilter}
              onClearFilters={clearFilters}
            />
            <SortMenu
              options={sortOptions}
              onSortChange={requestSort}
              sortConfig={sortConfig}
            />
            <ViewToggle view={view} onChange={setView} size="small" />
            {shouldShowRerunButton() && (
              <Button
                variant="contained"
                color="warning"
                size="small"
                startIcon={
                  isRerunning ? <CircularProgress size={16} /> : <RefreshIcon />
                }
                onClick={handleRerunFailedIterations}
                disabled={isRerunning}
                title={
                  !batch?.rerun_enabled
                    ? "Rerun was disabled after termination. Clicking will re-enable rerun and proceed."
                    : "Rerun crashed iterations and failed tasks without execution directories"
                }
              >
                {isRerunning ? "Rerunning..." : "Rerun"}
              </Button>
            )}
            {(() => {
              const shouldShow = batch?.status === "pending" || batch?.status === "executing";
              return shouldShow && (
                <Button
                  variant="contained"
                  color="error"
                  size="small"
                  startIcon={isTerminating ? <CircularProgress size={16} /> : <WarningIcon />}
                  onClick={handleTerminateBatch}
                  disabled={isTerminating}
                  title="Immediately terminate running/pending iterations and cleanup"
                >
                  {isTerminating ? "Terminating..." : "Terminate"}
                </Button>
              );
            })()}
            <Button
              variant="outlined"
              size="small"
              onClick={handlePreviewReport}
              disabled={!reportReadiness?.ready}
              title={
                !reportReadiness?.ready
                  ? reportReadiness?.reason || "Report is not ready yet"
                  : "Preview batch report in new tab"
              }
            >
              Preview
            </Button>
            <Button
              variant="contained"
              size="small"
              startIcon={
                isGeneratingReport ? (
                  <CircularProgress size={16} />
                ) : (
                  <DownloadIcon />
                )
              }
              onClick={handleGenerateReport}
              disabled={isGeneratingReport || !reportReadiness?.ready}
              title={
                !reportReadiness?.ready
                  ? reportReadiness?.reason || "Report is not ready yet"
                  : "Download batch report"
              }
            >
              {isGeneratingReport ? "Generating..." : "Download"}
            </Button>
            {batchId && (
              <Box sx={{ ml: 'auto' }}>
                <Tooltip title="Download all batch assets as ZIP archive">
                  <span>
                    <IconButton
                      onClick={handleDownloadBatch}
                      disabled={!batchId}
                      size="small"
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
                      {isThisBatchDownloading ? (
                        <CircularProgress size={20} sx={{ color: 'white' }} />
                      ) : (
                        <CloudDownloadIcon />
                      )}
                    </IconButton>
                  </span>
                </Tooltip>
              </Box>
            )}
          </Box>
        </Box>
      </Box>

      <Container maxWidth="xl">
        <Box sx={{ py: 4 }}>
          {/* Normal header section - hides when scrolled */}
          <Box
            ref={headerRef}
            sx={{
              transform: isScrolled ? "translateY(-100%)" : "translateY(0)",
              opacity: isScrolled ? 0 : 1,
              transition: "transform 0.2s ease-in-out, opacity 0.2s ease-in-out",
              height: isScrolled ? 0 : "auto",
              overflow: isScrolled ? "hidden" : "visible",
              mb: 3,
            }}
          >
            <Box
              display="flex"
              justifyContent="space-between"
              alignItems="flex-start"
              mb={3}
            >
          <Box>
            <Typography variant="h4" component="h1">
              Batch Runs: {batch?.name}
            </Typography>
            {(primaryGymName || displayTaskId) && (
              <Typography variant="subtitle1" color="text.secondary">
                {[
                  primaryGymName && `Gym: ${primaryGymName}`,
                  displayTaskId && `Task ID: ${displayTaskId}`,
                ]
                  .filter(Boolean)
                  .join(" • ")}
              </Typography>
            )}
          </Box>
          <Box display="flex" gap={2} alignItems="center" flexWrap="wrap">
            <FilterMenu
              options={filterCategories}
              activeFilters={activeFilters}
              onFilterToggle={toggleFilter}
              onClearFilters={clearFilters}
            />
            <SortMenu
              options={sortOptions}
              onSortChange={requestSort}
              sortConfig={sortConfig}
            />
            <ViewToggle view={view} onChange={setView} size="small" />
            {shouldShowRerunButton() && (
              <Button
                variant="contained"
                color="warning"
                startIcon={
                  isRerunning ? <CircularProgress size={16} /> : <RefreshIcon />
                }
                onClick={handleRerunFailedIterations}
                disabled={isRerunning}
                title={
                  !batch?.rerun_enabled
                    ? "Rerun was disabled after termination. Clicking will re-enable rerun and proceed."
                    : "Rerun crashed iterations and failed tasks without execution directories"
                }
              >
                {isRerunning ? "Rerunning..." : "Rerun Failed Iterations"}
              </Button>
            )}
            {(() => {
              console.log("DEBUG: Batch status:", batch?.status, "Should show terminate button:", batch?.status === "pending" || batch?.status === "executing");
              const shouldShow = batch?.status === "pending" || batch?.status === "executing";
              console.log("DEBUG: Rendering terminate button:", shouldShow);
              return shouldShow && (
                <Button
                  variant="contained"
                  color="error"
                  startIcon={isTerminating ? <CircularProgress size={16} /> : <WarningIcon />}
                  onClick={() => {
                    console.log("DEBUG: Button clicked!");
                    handleTerminateBatch();
                  }}
                  disabled={isTerminating}
                  title="Immediately terminate running/pending iterations and cleanup"
                >
                  {isTerminating ? "Terminating..." : "Terminate Batch"}
                </Button>
              );
            })()}
            <Button
              variant="outlined"
              onClick={handlePreviewReport}
              disabled={!reportReadiness?.ready}
              title={
                !reportReadiness?.ready
                  ? reportReadiness?.reason || "Report is not ready yet"
                  : "Preview batch report in new tab"
              }
            >
              Preview Report
            </Button>
            <Button
              variant="contained"
              startIcon={
                isGeneratingReport ? (
                  <CircularProgress size={16} />
                ) : (
                  <DownloadIcon />
                )
              }
              onClick={handleGenerateReport}
              disabled={isGeneratingReport || !reportReadiness?.ready}
              title={
                !reportReadiness?.ready
                  ? reportReadiness?.reason || "Report is not ready yet"
                  : "Download batch report"
              }
            >
              {isGeneratingReport ? "Generating..." : "Download Report"}
            </Button>
            {batchId && (
              <Box sx={{ ml: 'auto' }}>
                <Tooltip title="Download all batch assets as ZIP archive">
                  <span>
                    <IconButton
                      onClick={handleDownloadBatch}
                      disabled={!batchId}
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
                      {isThisBatchDownloading ? (
                        <CircularProgress size={24} sx={{ color: 'white' }} />
                      ) : (
                        <CloudDownloadIcon />
                      )}
                    </IconButton>
                  </span>
                </Tooltip>
              </Box>
            )}
          </Box>
        </Box>
      </Box>

          <Divider sx={{ my: 3, opacity: isScrolled ? 0 : 1, transition: "opacity 0.2s ease-in-out" }} />

          {error && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
              {error}
            </Alert>
          )}
          
          {/* Report Readiness Info */}
          {reportReadinessInfo && !reportReadiness?.ready && (
            <Alert severity="info" sx={{ mb: 2 }}>
              <Typography variant="body2" fontWeight={600} gutterBottom>
                Report Not Ready
              </Typography>
              <Typography variant="body2">
                {reportReadinessInfo}
              </Typography>
              {reportReadiness?.counts && (
                <Box sx={{ mt: 1 }}>
                  <Typography variant="caption" display="block">
                    Blocking items: 
                    {reportReadiness.counts.pending > 0 && ` ${reportReadiness.counts.pending} pending`}
                    {reportReadiness.counts.executing > 0 && ` ${reportReadiness.counts.executing} executing`}
                    {reportReadiness.counts.crashed > 0 && ` ${reportReadiness.counts.crashed} crashed`}
                    {reportReadiness.counts.failed_without_directory > 0 && ` ${reportReadiness.counts.failed_without_directory} failed (no directory)`}
                  </Typography>
                </Box>
              )}
            </Alert>
          )}
          
          {/* Report Ready Notification */}
          {reportReadiness?.ready && (
            <Alert severity="success" sx={{ mb: 2 }}>
              <Typography variant="body2" fontWeight={600}>
                ✓ Report Ready for Download
              </Typography>
              <Typography variant="body2">
                All tasks have completed. You can now download or preview the batch report.
              </Typography>
            </Alert>
          )}

          {/* Iteration Summary */}
          <BatchOverallSummary
            summary={iterationSummary?.overall_summary}
            isLoading={summaryLoading}
            error={summaryError as Error | null}
            batchName={batch?.name}
            batchId={batchId}
          />

          {/* Batch Insights */}
          <BatchInsightsTabs evalInsights={batch?.eval_insights} />

          {/* Executions Display */}
          {executions && executions.length > 0 ? (
          sortedRuns && sortedRuns.length > 0 ? (
            isCardView ? (
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
                {sortedRuns.map((execution) => {
                  const gym = gyms?.find((g) => g.uuid === execution.gym_id);
                  const task = Array.isArray(tasks)
                    ? tasks.find((t) => t.task_id === (execution.task_identifier || execution.task_id))
                    : undefined;
                  const taskIdentifier = task?.task_id || execution.task_identifier || execution.task_id;

                  // Find iteration stats for this execution from the summary
                  const executionBreakdown =
                    iterationSummary?.execution_breakdowns.find(
                      (breakdown) => breakdown.execution_id === execution.uuid
                    );

                  return (
                    <RunCard
                      key={execution.uuid}
                      run={execution}
                      onEdit={handleEditExecution}
                      gymName={gym?.name}
                      taskIdentifier={taskIdentifier || undefined}
                      taskPrompt={task?.prompt}
                      hideEditButton={true}
                      iterationStats={executionBreakdown?.iteration_counts}
                    />
                  );
                })}
              </Box>
            ) : (
              <RunsTable
                runs={sortedRuns}
                gyms={gyms}
                tasks={tasks}
                onRowClick={handleViewExecution}
                onEdit={handleEditExecution}
                isLoading={executionsLoading}
              />
            )
          ) : (
            <Box
              sx={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                minHeight: "200px",
                textAlign: "center",
              }}
            >
              <Typography variant="h6" color="text.secondary" gutterBottom>
                {activeFilters.size > 0
                  ? "No executions match your filters"
                  : "No executions found"}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {activeFilters.size > 0
                  ? "Try adjusting your filters."
                  : "This batch doesn't have any executions yet."}
              </Typography>
            </Box>
          )
        ) : (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              minHeight: "200px",
              textAlign: "center",
            }}
          >
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No executions found
            </Typography>
            <Typography variant="body2" color="text.secondary">
              This batch doesn't have any executions yet.
            </Typography>
          </Box>
        )}
      </Box>
    </Container>

      {/* Scroll to Top Button */}
      <Tooltip title="Scroll to top" placement="left">
        <Fab
          size="small"
          color="primary"
          aria-label="scroll to top"
          onClick={handleScrollToTop}
          sx={{
            position: "fixed",
            bottom: 24,
            // Position at absolute right edge of viewport, outside container
            // Use minimal offset to be at the extreme right edge
            right: hideDrawer ? 4 : drawerWidth + 4,
            zIndex: theme.zIndex.speedDial + 1, // Ensure it's above cards
            opacity: isScrolled ? 1 : 0,
            transform: isScrolled ? "scale(1)" : "scale(0)",
            transition: "opacity 0.15s ease-in-out, transform 0.15s ease-in-out",
            pointerEvents: isScrolled ? "auto" : "none",
            boxShadow: 4,
            "&:hover": {
              boxShadow: 6,
              transform: "scale(1.1)",
            },
          }}
        >
          <ArrowUpwardIcon />
        </Fab>
      </Tooltip>
    </>
  );
}
