import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { Typography, Box, Alert, Snackbar, Chip, Paper, Link, Pagination, FormControl, InputLabel, Select, MenuItem, Button } from "@mui/material";
import {
  Add as AddIcon,
  PlayArrow as PlayArrowIcon,
  DirectionsRun as RunIcon,
} from "@mui/icons-material";
import { useRuns, useRunExecution, useDeleteRun, usePlaygroundProgress } from "../hooks/useRuns";
import { useSearchParams } from "react-router-dom";
import { useGyms } from "../hooks/useGyms";
import { useTasks } from "../hooks/useTasks";
import type { IterationCounts, Execution, ModelType } from "../types";
import { useSorting } from "../hooks/useSorting";
import { useFiltering, type FilterCategory } from "../hooks/useFiltering";
import { useSnackbar, getCrudMessage } from "../hooks/useSnackbar";
import SortMenu from "../components/SortMenu";
import FilterMenu from "../components/FilterMenu";
import NotificationSnackbar from "../components/NotificationSnackbar";

import RunCard from "../components/RunCard";
import RunForm from "../components/RunForm";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import PageSkeleton from "../components/PageSkeleton";
import { RunsTable } from "../components";
import { useViewToggle } from "../hooks/useViewToggle";
import ViewToggle from "../components/ViewToggle";
import { useStickyHeader } from "../hooks/useStickyHeader";
import StickyHeader from "../components/StickyHeader";
import StickyHeaderSkeleton from "../components/StickyHeaderSkeleton";
import CollapsibleHeader from "../components/CollapsibleHeader";
import {
  DeleteConfirmationModal,
  DetailModal,
  DetailContent,
  DetailSection,
  DetailFields,
  DetailField,
  DetailTimestamps,
} from "../components/shared";

const PAGE_SIZE_OPTIONS = [30, 60, 90];

// Component to wrap RunCard with progress data from unified endpoint
function ExecutionCardWithProgress({
  execution,
  gymName,
  taskIdentifier,
  taskPrompt,
  onEdit,
  progressData,
}: {
  execution: Execution;
  gymName?: string;
  taskIdentifier?: string;
  taskPrompt?: string;
  onEdit: (run: Execution) => void;
  progressData?: {
    execution_id: string;
    total_iterations: number;
    completed_iterations: number;
    progress_percentage: number;
    summary: {
      total_iterations: number;
      pending_count: number;
      executing_count: number;
      passed_count: number;
      failed_count: number;
      crashed_count: number;
      timeout_count: number;
    };
  };
}) {
  // Calculate iteration stats from unified progress data
  const iterationStats: IterationCounts | undefined = progressData?.summary
    ? {
        pending: progressData.summary.pending_count || 0,
        executing: progressData.summary.executing_count || 0,
        passed: progressData.summary.passed_count || 0,
        failed: progressData.summary.failed_count || 0,
        crashed: progressData.summary.crashed_count || 0,
      }
    : undefined;

  return (
    <RunCard
      key={execution.uuid}
      run={execution}
      onEdit={onEdit}
      gymName={gymName}
      taskIdentifier={taskIdentifier}
      taskPrompt={taskPrompt}
      iterationStats={iterationStats}
    />
  );
}

export default function Runs() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [formOpen, setFormOpen] = useState(false);
  const [editingRun, setEditingRun] = useState<Execution | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const getValidPage = (value: string | null): number => {
    const parsed = parseInt(value ?? "", 10);
    return Number.isNaN(parsed) || parsed < 1 ? 1 : parsed;
  };
  const getValidPageSize = (value: string | null): number => {
    const parsed = parseInt(value ?? "", 10);
    return PAGE_SIZE_OPTIONS.includes(parsed) ? parsed : PAGE_SIZE_OPTIONS[0];
  };

  const [page, setPage] = useState<number>(() => getValidPage(searchParams.get("page")));
  const [pageSize, setPageSize] = useState<number>(() => getValidPageSize(searchParams.get("pageSize")));
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [runToDelete, setRunToDelete] = useState<Execution | null>(null);
  const [viewDialogOpen, setViewDialogOpen] = useState(false);
  const [runToView, setRunToView] = useState<Execution | null>(null);
  // View toggle state
  const { view, setView, isCardView } = useViewToggle("card");
  
  // Sticky header
  const { isScrolled, headerRef, stickyHeaderRef } = useStickyHeader({ threshold: 200 });
  const drawerWidth = 240;

  // Snackbar for notifications
  const { snackbar, showSuccess, showError, hideSnackbar } = useSnackbar();

  const [executionFeedback, setExecutionFeedback] = useState<{
    open: boolean;
    message: string;
    severity: "success" | "error";
  }>({ open: false, message: "", severity: "success" });

  // Initialize sorting state (for UI only, actual sorting done server-side)
  const sortOptions = [
    { value: "created_at", label: "Sort by Date" },
    { value: "status", label: "Sort by Status" },
    { value: "model", label: "Sort by Model" },
  ];
  const [availableFilters, setAvailableFilters] = useState<{
    statuses: Execution["status"][];
    models: ModelType[];
  }>({ statuses: [], models: [] });

  const filterCategories = useMemo<FilterCategory<Execution>[]>(() => {
    const categories: FilterCategory<Execution>[] = [];
    if (availableFilters.statuses.length > 0) {
      categories.push({ key: "status", label: "Status", options: availableFilters.statuses });
    }
    if (availableFilters.models.length > 0) {
      categories.push({ key: "model", label: "Model", options: availableFilters.models });
    }
    return categories;
  }, [availableFilters]);

  const skip = (page - 1) * pageSize;

  const runQueryParams = useMemo(
    () => ({
      execution_type: "playground" as const,
      skip,
      limit: pageSize,
    }),
  [page, pageSize],
  );

  const {
    data: runsResponse,
    isLoading,
    error,
  } = useRuns(runQueryParams, { enableRealTimeSync: true });

const runs = runsResponse?.executions ?? [];
const totalRuns = runsResponse?.total ?? 0;
const hasInitialRuns = runsResponse !== undefined;
const isInitialLoading = isLoading && !runsResponse;
const totalPages = totalRuns > 0 ? Math.ceil(totalRuns / pageSize) : 1;
const isSinglePage = totalPages <= 1;
const showingStart = totalRuns === 0 ? 0 : skip + 1;
const showingEnd = totalRuns === 0 ? 0 : Math.min(skip + pageSize, totalRuns);

const { filteredItems, activeFilters, toggleFilter, clearFilters } = useFiltering(runs, filterCategories);

useEffect(() => {
  const executions = runs ?? [];

  const statusSet = new Set<Execution["status"]>(
    executions.map((execution) => execution.status),
  );
  const selectedStatuses = Array.from(activeFilters.get("status") ?? []);
  selectedStatuses.forEach((status) => {
    if (typeof status === "string") {
      statusSet.add(status as Execution["status"]);
    }
  });
  const statuses = Array.from(statusSet).sort((a, b) => a.localeCompare(b));

  const modelSet = new Set(executions.map((execution) => execution.model));
  const selectedModels = Array.from(activeFilters.get("model") ?? []);
  selectedModels.forEach((model) => {
    if (typeof model === "string") {
      modelSet.add(model as Execution["model"]);
    }
  });
  const models = Array.from(modelSet).sort((a, b) => a.localeCompare(b));

  setAvailableFilters({
    statuses,
    models,
  });
}, [runs, activeFilters]);

const searchedRuns = useMemo(() => {
  if (!searchTerm.trim()) {
    return filteredItems;
  }
  const term = searchTerm.toLowerCase();
  return filteredItems.filter((execution) => {
    const url = (execution as any).playground_url || "";
    const prompt = (execution.prompt || "").toLowerCase();
    return (
      execution.uuid.toLowerCase().includes(term) ||
      execution.model.toLowerCase().includes(term) ||
      execution.status.toLowerCase().includes(term) ||
      url.toLowerCase().includes(term) ||
      prompt.includes(term)
    );
  });
}, [filteredItems, searchTerm]);

const {
  sortedItems: sortedRuns,
  requestSort,
  sortConfig,
} = useSorting(searchedRuns, sortOptions, {
  key: "created_at",
  direction: "desc",
});

const filtersKey = useMemo(() => {
  const entries = Array.from(activeFilters.entries()).map(([key, set]) => [key, Array.from(set).sort()]);
  return JSON.stringify(entries);
}, [activeFilters]);

// Reset to page 1 when filters, search, or sort change
const prevFiltersRef = useRef({
  searchTerm,
  filtersKey,
  sortKey: sortConfig.key,
  sortOrder: sortConfig.direction,
});
  useEffect(() => {
    const prev = prevFiltersRef.current;
    const hasChanged =
      prev.searchTerm !== searchTerm ||
    prev.filtersKey !== filtersKey ||
      prev.sortKey !== sortConfig.key ||
      prev.sortOrder !== sortConfig.direction;

    if (hasChanged) {
      // Only reset if we're not already on page 1
      if (page !== 1) {
        setPage(1);
        const params = new URLSearchParams(searchParams);
        params.set("page", "1");
        setSearchParams(params, { replace: true });
      }
      prevFiltersRef.current = {
        searchTerm,
      filtersKey,
        sortKey: sortConfig.key,
        sortOrder: sortConfig.direction,
      };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
}, [searchTerm, filtersKey, sortConfig.key, sortConfig.direction]);

  const progressQueryParams = useMemo(
    () => ({
      skip,
      limit: pageSize,
    }),
  [skip, pageSize],
  );

  // Fetch unified progress for the current playground page
  const { data: progressData } = usePlaygroundProgress(
    progressQueryParams,
    { enableRealTimeSync: true }
  );

  const { data: gyms } = useGyms();
  const { data: tasks } = useTasks();
  const runToViewTask = useMemo(() => {
    if (!runToView || !Array.isArray(tasks)) return undefined;
    return tasks.find((task) => task.uuid === runToView.task_id);
  }, [runToView, tasks]);
  const executeRunMutation = useRunExecution();
  const deleteRunMutation = useDeleteRun({
    onSuccess: () => {
      showSuccess(getCrudMessage("delete", "success", "run"));
    },
    onError: (error) => {
      showError(getCrudMessage("delete", "error", "run"));
      console.error("Delete run error:", error);
    },
  });

  const updatePaginationParams = useCallback((nextPage: number, nextPageSize: number) => {
    const normalizedPage = Math.max(1, nextPage);
    const normalizedPageSize = PAGE_SIZE_OPTIONS.includes(nextPageSize)
      ? nextPageSize
      : PAGE_SIZE_OPTIONS[0];
    setPage(normalizedPage);
    setPageSize(normalizedPageSize);
    const params = new URLSearchParams(searchParams);
    params.set("page", normalizedPage.toString());
    params.set("pageSize", normalizedPageSize.toString());
    setSearchParams(params, { replace: true });
  }, [searchParams, setSearchParams]);

  // Sync state from URL parameters (e.g., browser back/forward navigation)
  useEffect(() => {
    const urlPage = getValidPage(searchParams.get("page"));
    const urlPageSize = getValidPageSize(searchParams.get("pageSize"));
    // Only update if URL values differ from current state to avoid unnecessary re-renders
    if (urlPage !== page || urlPageSize !== pageSize) {
      setPage(urlPage);
      setPageSize(urlPageSize);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    if (!hasInitialRuns) {
      return;
    }
    if (page > totalPages && totalPages > 0) {
      updatePaginationParams(totalPages, pageSize);
    }
  }, [hasInitialRuns, page, totalPages, pageSize, updatePaginationParams]);

  // Debug runs data
useEffect(() => {
  console.log("🔍 Runs page data:", {
    visibleRuns: runs.length,
    totalRuns,
    page,
    skip,
    isLoading,
    hasError: !!error,
  });
}, [runs, totalRuns, page, skip, isLoading, error]);


  // Handle execution feedback
  useEffect(() => {
    if (executeRunMutation.isSuccess && executeRunMutation.data) {
      const originalExecution = executeRunMutation.variables;
      const isRerun = originalExecution?.status === "passed";

      if (isRerun) {
        setExecutionFeedback({
          open: true,
          message: `🔄 Rerun created successfully! New execution ID: ${executeRunMutation.data.uuid}`,
          severity: "success",
        });
      } else {
        setExecutionFeedback({
          open: true,
          message: `▶️ Execution started successfully! Run ID: ${executeRunMutation.data.uuid}`,
          severity: "success",
        });
      }
    }
  }, [
    executeRunMutation.isSuccess,
    executeRunMutation.data,
    executeRunMutation.variables,
  ]);

  useEffect(() => {
    if (executeRunMutation.isError) {
      setExecutionFeedback({
        open: true,
        message: `Failed to start execution: ${executeRunMutation.error?.message || "Unknown error"}`,
        severity: "error",
      });
    }
  }, [executeRunMutation.isError, executeRunMutation.error]);

  const handleEdit = (run: Execution) => {
    setEditingRun(run);
    setFormOpen(true);
  };

  const handleDelete = (run: Execution) => {
    setRunToDelete(run);
    setDeleteConfirmOpen(true);
  };

  const handleView = (run: Execution) => {
    setRunToView(run);
    setViewDialogOpen(true);
  };

  const confirmDelete = () => {
    if (runToDelete) {
      deleteRunMutation.mutate(runToDelete.uuid, {
        onSuccess: () => {
          setDeleteConfirmOpen(false);
          setRunToDelete(null);
        },
      });
    }
  };

  const handlePageChange = useCallback((_event: React.ChangeEvent<unknown>, newPage: number) => {
    updatePaginationParams(newPage, pageSize);
  }, [updatePaginationParams, pageSize]);

  const handleCloseForm = () => {
    setFormOpen(false);
    setEditingRun(null);
  };

  const handleCloseFeedback = () => {
    setExecutionFeedback({ ...executionFeedback, open: false });
  };

  // Use locally filtered/searchable/sorted runs for display

  if (isInitialLoading) {
    return (
      <Box>
        <StickyHeaderSkeleton leftOffset={drawerWidth} />
        <PageSkeleton
          variant="run"
          cardCount={pageSize}
          showCardActions={true}
          cardLines={2}
        />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error">
        Failed to load runs. Please try again later.
      </Alert>
    );
  }

  return (
    <Box>
      <StickyHeader
        ref={stickyHeaderRef}
        isScrolled={isScrolled}
        title="Playground"
        subtitle="Run prompts directly on any URL with your preferred model"
        controls={
          <>
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
            <Button
              variant="contained"
              size="small"
              startIcon={<AddIcon />}
              onClick={() => setFormOpen(true)}
            >
              Create Run
            </Button>
          </>
        }
        leftOffset={drawerWidth}
      />

      <CollapsibleHeader isScrolled={isScrolled} headerRef={headerRef}>
        <PageHeader
          icon={<PlayArrowIcon sx={{ fontSize: 48 }} />}
          title="Playground"
          description="Run prompts directly on any URL with your preferred model"
          searchPlaceholder="Search playground runs by ID, model, or URL..."
          searchValue={searchTerm}
          onSearchChange={setSearchTerm}
          primaryButton={{
            label: "Create Playground Run",
            icon: <AddIcon />,
            onClick: () => setFormOpen(true),
          }}
          viewToggle={{
            view,
            onChange: setView,
          }}
          sortMenu={
            <SortMenu
              options={sortOptions}
              onSortChange={requestSort}
              sortConfig={sortConfig}
            />
          }
          filterMenu={
            <FilterMenu
              options={filterCategories}
              activeFilters={activeFilters}
              onFilterToggle={toggleFilter}
              onClearFilters={clearFilters}
            />
          }
        />
      </CollapsibleHeader>

      {sortedRuns.length > 0 ? (
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
            {sortedRuns.map((run) => {
              // For playground executions, we don't need gym/task lookup
              const gym = (run as any).execution_type === "playground" ? null : gyms?.find((g) => g.uuid === run.gym_id);
              const task = (run as any).execution_type === "playground" ? null : (Array.isArray(tasks)
                ? tasks.find((t) => t.uuid === run.task_id)
                : undefined);
              const taskIdentifier = task?.task_id;

              // Get progress data for this execution from unified endpoint
              const executionProgress = progressData?.execution_progress?.[run.uuid];

              return (
                <ExecutionCardWithProgress
                  key={run.uuid}
                  execution={run}
                  onEdit={handleEdit}
                  gymName={gym?.name}
                  taskIdentifier={taskIdentifier}
                  taskPrompt={task?.prompt}
                  progressData={executionProgress}
                />
              );
            })}
          </Box>
        ) : (
          <RunsTable
            runs={sortedRuns}
            gyms={gyms}
            tasks={Array.isArray(tasks) ? tasks : []}
            onEdit={handleEdit}
            onView={handleView}
            onDelete={handleDelete}
            isLoading={isLoading}
          />
        )
      ) : (
        <EmptyState
          icon={<PlayArrowIcon />}
          title={searchTerm ? "No playground runs match your search" : "No playground runs found"}
          description={
            searchTerm
              ? "Try adjusting your search terms"
              : "Get started by creating your first playground run"
          }
          isSearchState={!!searchTerm}
          searchTerm={searchTerm}
          onClearSearch={() => setSearchTerm("")}
          primaryAction={{
            label: searchTerm ? "Create Playground Run" : "Create Your First Playground Run",
            icon: <AddIcon />,
            onClick: () => setFormOpen(true),
          }}
        />
      )}

      {totalRuns > 0 && (
        <Box
          sx={{
            mt: 4,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 2,
          }}
        >
          <Typography variant="body2" color="text.secondary">
            Showing {showingStart}-{showingEnd} of {totalRuns} playground runs
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel id="page-size-label">Rows per page</InputLabel>
              <Select
                labelId="page-size-label"
                value={pageSize}
                label="Rows per page"
                onChange={(event) => {
                  const value = Number(event.target.value);
                  if (!Number.isNaN(value)) {
                    updatePaginationParams(1, value);
                  }
                }}
              >
                {PAGE_SIZE_OPTIONS.map((option) => (
                  <MenuItem key={option} value={option}>
                    {option}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Box sx={{ pointerEvents: isSinglePage ? "none" : "auto", opacity: isSinglePage ? 0.5 : 1 }}>
              <Pagination
                count={Math.max(totalPages, 1)}
                page={page}
                onChange={handlePageChange}
                color="primary"
                showFirstButton
                showLastButton
                disabled={isSinglePage}
              />
            </Box>
          </Box>
        </Box>
      )}

      <RunForm
        open={formOpen}
        onClose={handleCloseForm}
        run={editingRun}
        isPlayground={true}
        onSuccess={() => {
          const message = editingRun
            ? getCrudMessage("update", "success", "run")
            : getCrudMessage("create", "success", "run");
          showSuccess(message);
        }}
        onError={(error) => {
          const message = editingRun
            ? getCrudMessage("update", "error", "run")
            : getCrudMessage("create", "error", "run");
          showError(message);
          console.error("Run form error:", error);
        }}
      />

      {/* Execution Feedback Snackbar */}
      <Snackbar
        open={executionFeedback.open}
        autoHideDuration={6000}
        onClose={handleCloseFeedback}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        <Alert
          onClose={handleCloseFeedback}
          severity={executionFeedback.severity}
          sx={{ width: "100%" }}
        >
          {executionFeedback.message}
        </Alert>
      </Snackbar>

      {/* Notification Snackbar */}
      <NotificationSnackbar snackbar={snackbar} onClose={hideSnackbar} />

      {/* Delete Confirmation Modal */}
      <DeleteConfirmationModal
        open={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        onConfirm={confirmDelete}
        item={runToDelete}
        isLoading={deleteRunMutation.isPending}
      />

      {/* View Details Modal */}
      <DetailModal
        open={viewDialogOpen}
        onClose={() => setViewDialogOpen(false)}
        onEdit={
          runToView
            ? () => {
                setViewDialogOpen(false);
                handleEdit(runToView);
              }
            : undefined
        }
        title="Run Details"
        icon={<RunIcon color="primary" />}
        editButtonText="Edit Run"
        canEdit={!!runToView}
      >
        {runToView && (
          <DetailContent>
            {/* Basic Information */}
            <DetailSection title="Basic Information">
              <DetailFields>
                <DetailField
                  label="Run ID"
                  value={
                    <Typography
                      variant="body1"
                      sx={{ fontFamily: "monospace", fontWeight: 500 }}
                    >
                      {runToView.uuid}
                    </Typography>
                  }
                  fullWidth
                />
                <DetailField label="Model" value={runToView.model} />
                <DetailField
                  label="Status"
                  value={
                    <Chip
                      label={runToView.status}
                      color={
                        runToView.status === "passed"
                          ? "success"
                          : runToView.status === "failed"
                            ? "error"
                            : runToView.status === "executing"
                              ? "info"
                              : "default"
                      }
                    />
                  }
                />
              </DetailFields>
            </DetailSection>

            {/* Configuration */}
            <DetailSection title="Configuration">
              <DetailFields>
                {(runToView as any).execution_type === "playground" ? (
                  <>
                    <DetailField
                      label="URL"
                      value={
                        <Link
                          href={(runToView as any).playground_url || ""}
                          target="_blank"
                          rel="noopener noreferrer"
                          variant="body1"
                          sx={{ fontFamily: "monospace", fontWeight: 500 }}
                        >
                          {(runToView as any).playground_url || "No URL"}
                        </Link>
                      }
                      fullWidth
                    />
                    <DetailField
                      label="Prompt"
                      value={
                        <Box>
                          <Paper
                            variant="outlined"
                            sx={{
                              p: 2,
                              backgroundColor: "action.hover",
                              maxHeight: 200,
                              overflow: "auto",
                            }}
                          >
                            <Typography
                              variant="body2"
                              sx={{ whiteSpace: "pre-wrap" }}
                            >
                              {runToView.prompt || "No prompt"}
                            </Typography>
                          </Paper>
                        </Box>
                      }
                      fullWidth
                    />
                  </>
                ) : (
                  <>
                    <DetailField
                      label="Gym"
                      value={
                        <Box>
                          <Typography
                            variant="body1"
                            sx={{ fontFamily: "monospace", fontWeight: 500 }}
                          >
                            {runToView.gym_id || "No gym"}
                          </Typography>
                          {gyms && (
                            <Typography variant="body2" color="text.secondary">
                              {gyms.find((g) => g.uuid === runToView.gym_id)
                                ?.name || "Unknown Gym"}
                            </Typography>
                          )}
                        </Box>
                      }
                    />
                    <DetailField
                      label="Task"
                      value={
                        <Box>
                          <Typography
                            variant="body1"
                            sx={{ fontFamily: "monospace", fontWeight: 500, mb: 1 }}
                          >
                            {runToViewTask?.task_id || runToView?.task_identifier || runToView?.task_id || "No task assigned"}
                          </Typography>
                          {tasks && Array.isArray(tasks) && (
                            <Box>
                              <Typography
                                variant="subtitle2"
                                color="text.secondary"
                                gutterBottom
                              >
                                Prompt:
                              </Typography>
                              <Paper
                                variant="outlined"
                                sx={{
                                  p: 2,
                                  backgroundColor: "action.hover",
                                  maxHeight: 200,
                                  overflow: "auto",
                                }}
                              >
                                <Typography
                                  variant="body2"
                                  sx={{ whiteSpace: "pre-wrap" }}
                                >
                                  {runToViewTask?.prompt || "Unknown Task"}
                                </Typography>
                              </Paper>
                            </Box>
                          )}
                        </Box>
                      }
                      fullWidth
                    />
                  </>
                )}
                {runToView.number_of_iterations && (
                  <DetailField
                    label="Number of Iterations"
                    value={runToView.number_of_iterations}
                  />
                )}
              </DetailFields>
            </DetailSection>

            <DetailTimestamps
              createdAt={runToView.created_at}
              updatedAt={runToView.updated_at}
            />
          </DetailContent>
        )}
      </DetailModal>

    </Box>
  );
}

