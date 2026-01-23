import { useState, useMemo, useEffect, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import {
  Typography,
  Box,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Chip,
  Breadcrumbs,
  Link,
} from "@mui/material";
import {
  Add as AddIcon,
  Assignment as AssignmentIcon,
  Delete as DeleteIcon,
  Sync as SyncIcon,
  Task as TaskIcon,
  Home as HomeIcon,
  FitnessCenter as FitnessCenterIcon,
  Download as DownloadIcon,
} from "@mui/icons-material";
import { useTasks, useDeleteTask } from "../hooks/useTasks";
import { useGym } from "../hooks/useGyms";
import { useViewToggle } from "../hooks/useViewToggle";
import { useSorting, type SortOption } from "../hooks/useSorting";
import { useFiltering, type FilterCategory } from "../hooks/useFiltering";
import { useSnackbar, getCrudMessage } from "../hooks/useSnackbar";
import { taskApi, gymApi } from "../services/api";
import { useQueryClient } from "@tanstack/react-query";
import { downloadJSON } from "../utils/downloadUtils";
import SortMenu from "../components/SortMenu";
import FilterMenu from "../components/FilterMenu";
import NotificationSnackbar from "../components/NotificationSnackbar";
import type { Task } from "../types";
import TaskCard from "../components/TaskCard";
import TaskForm from "../components/TaskForm";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import PageSkeleton from "../components/PageSkeleton";
import { TasksTable } from "../components";
import { modalConfig } from "../utils/modalConfig";
import {
  DetailModal,
  DetailContent,
  DetailHeader,
  DetailSection,
  DetailFields,
  DetailField,
  DetailTimestamps,
} from "../components/shared";
import { analyzePrompt, getCharacterCountText } from "../utils/promptUtils";
import { useAuth } from "../contexts/AuthContext";

export default function GymTasks() {
  const { gymId } = useParams<{ gymId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  
  const [formOpen, setFormOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [taskToDelete, setTaskToDelete] = useState<Task | null>(null);
  const [viewDialogOpen, setViewDialogOpen] = useState(false);
  const [taskToView, setTaskToView] = useState<Task | null>(null);

  // View toggle state
  const { view, setView, isCardView } = useViewToggle("card");

  // Snackbar for notifications
  const { snackbar, showSuccess, showError, hideSnackbar } = useSnackbar();

  // Auth for role-based permissions
  const { isAdmin } = useAuth();
  
  // Query client for invalidating queries
  const queryClient = useQueryClient();

  // Fetch gym data and tasks
  const { data: gym, isLoading: gymLoading, error: gymError } = useGym(gymId || "");
  const {
    data: fetchedTasks,
    isLoading: tasksLoading,
    error: tasksError,
  } = useTasks(
    gymId ? { gym_id: gymId } : undefined
  );

  const [displayedTasks, setDisplayedTasks] = useState<Task[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isDownloadingAll, setIsDownloadingAll] = useState(false);

  const deleteTaskMutation = useDeleteTask({
    onSuccess: () => {
      showSuccess(getCrudMessage("delete", "success", "task"));
    },
    onError: (error) => {
      showError(getCrudMessage("delete", "error", "task"));
      console.error("Delete task error:", error);
    },
  });

  const handleEdit = (task: Task) => {
    setEditingTask(task);
    setFormOpen(true);
  };

  const handleDelete = (task: Task) => {
    setTaskToDelete(task);
    setDeleteConfirmOpen(true);
  };

  const handleView = (task: Task) => {
    setTaskToView(task);
    setViewDialogOpen(true);
  };

  const confirmDelete = () => {
    if (taskToDelete) {
      deleteTaskMutation.mutate(taskToDelete.uuid, {
        onSuccess: () => {
          setDeleteConfirmOpen(false);
          setTaskToDelete(null);
        },
      });
    }
  };

  const handleCloseForm = () => {
    setFormOpen(false);
    setEditingTask(null);
  };

  const handleBackToGyms = () => {
    navigate("/tasks");
  };

  useEffect(() => {
    if (fetchedTasks) {
      setDisplayedTasks(fetchedTasks);
    }
  }, [fetchedTasks]);

  const handleSyncTasks = useCallback(async () => {
    if (!gymId) {
      showError("Gym ID is unavailable. Please try again.");
      return;
    }

    setIsSyncing(true);

    try {
      const result = await taskApi.syncFromGym(gymId);
      showSuccess(result.message || "Tasks synced successfully.");
      
      // Invalidate and refetch tasks queries to show the new tasks
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["gyms", "with-task-counts"] });
    } catch (error) {
      console.error("Task sync failed:", error);
      showError("Failed to sync tasks. Please try again.");
    } finally {
      setIsSyncing(false);
    }
  }, [gymId, showError, showSuccess]);

  const handleDownloadAllTasks = useCallback(async () => {
    if (!gymId) {
      showError("Gym ID is unavailable. Please try again.");
      return;
    }

    if (!gym) {
      showError("Gym information is unavailable. Please try again.");
      return;
    }

    setIsDownloadingAll(true);

    try {
      const exportData = await gymApi.exportTasks(gymId);
      downloadJSON(exportData, `${gym.name}_tasks.json`);
      showSuccess("All tasks downloaded successfully.");
    } catch (error) {
      console.error("Download all tasks failed:", error);
      showError("Failed to download tasks. Please try again.");
    } finally {
      setIsDownloadingAll(false);
    }
  }, [gymId, gym, showError, showSuccess]);

  // Handle URL parameter for adding tasks
  useEffect(() => {
    if (searchParams.get("action") === "add-task") {
      setFormOpen(true);
      // Clean up the URL parameter
      navigate(`/gyms/${gymId}/tasks`, { replace: true });
    }
  }, [searchParams, navigate, gymId]);

  // Data processing pipeline: search -> filter -> sort
  const { searchedTasks, filterCategories } = useMemo(() => {
    const searchLower = searchTerm.toLowerCase();
    const searched =
      displayedTasks?.filter((task) =>
        task.prompt.toLowerCase().includes(searchLower),
      ) || [];

    const categories: FilterCategory<Task>[] = [];

    return { searchedTasks: searched, filterCategories: categories };
  }, [displayedTasks, searchTerm]);

  const { filteredItems, activeFilters, toggleFilter, clearFilters } =
    useFiltering(searchedTasks, filterCategories);

  const sortOptions: SortOption<Task>[] = [
    { value: "created_at", label: "Sort by Date" },
    { value: "task_id", label: "Sort by Task ID" },
    {
      value: "prompt_length",
      label: "Sort by Prompt Length",
      getValue: (task) => task.prompt.length,
    },
  ];

  const {
    sortedItems: sortedTasks,
    requestSort,
    sortConfig,
  } = useSorting(filteredItems || [], sortOptions, {
    key: "created_at",
    direction: "desc",
  });

  const isLoading = gymLoading || tasksLoading;
  const error = gymError || tasksError;

  if (isLoading) {
    return (
      <PageSkeleton
        variant="task"
        cardCount={6}
        showCardActions={true}
        cardLines={4}
      />
    );
  }

  if (error) {
    return (
      <Alert severity="error">
        Failed to load gym or tasks. Please try again later.
      </Alert>
    );
  }

  if (!gym) {
    return (
      <Alert severity="error">
        Gym not found.
      </Alert>
    );
  }

  return (
    <Box>
      {/* Breadcrumb Navigation */}
      <Breadcrumbs sx={{ mb: 3 }}>
        <Link
          component="button"
          variant="body1"
          onClick={handleBackToGyms}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 0.5,
            textDecoration: "none",
            "&:hover": {
              textDecoration: "underline",
            },
          }}
        >
          <HomeIcon sx={{ fontSize: 16 }} />
          Tasks
        </Link>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <FitnessCenterIcon sx={{ fontSize: 16 }} />
          <Typography variant="body1" color="text.primary">
            {gym.name}
          </Typography>
        </Box>
      </Breadcrumbs>

      <Box>
        <PageHeader
          icon={<AssignmentIcon sx={{ fontSize: 48 }} />}
          title={`Tasks - ${gym.name}`}
          description={`Manage tasks for ${gym.name} gym`}
          searchPlaceholder="Search tasks by prompt..."
          searchValue={searchTerm}
          onSearchChange={setSearchTerm}
          primaryButton={{
            label: "Add Task",
            icon: <AddIcon />,
            onClick: () => setFormOpen(true),
          }}
          secondaryButton={{
            label: isSyncing ? "Syncing..." : "Sync Tasks",
            icon: <SyncIcon />,
            onClick: handleSyncTasks,
            disabled: isSyncing,
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
        
        {/* Admin-only Download All Tasks button */}
        {isAdmin && (
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
            <Button
              variant="outlined"
              startIcon={isDownloadingAll ? <Box sx={{ display: 'flex', alignItems: 'center' }}><Typography component="span" sx={{ fontSize: '0.875rem' }}>⏳</Typography></Box> : <DownloadIcon />}
              onClick={handleDownloadAllTasks}
              disabled={isDownloadingAll}
              sx={{ textTransform: 'none' }}
            >
              {isDownloadingAll ? "Downloading..." : "Download All Tasks"}
            </Button>
          </Box>
        )}
      </Box>

      {sortedTasks && sortedTasks.length > 0 ? (
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
            {sortedTasks.map((task) => (
              <TaskCard task={task} onEdit={handleEdit} key={task.uuid} />
            ))}
          </Box>
        ) : (
          <TasksTable
            tasks={sortedTasks}
            gyms={[gym]}
            onEdit={handleEdit}
            onView={handleView}
        onDelete={isAdmin ? handleDelete : undefined}
            isLoading={isLoading}
          />
        )
      ) : (
        <EmptyState
          icon={<AssignmentIcon />}
          title={searchTerm ? "No tasks match your search" : "No tasks found"}
          description={
            searchTerm
              ? "Try adjusting your search terms"
              : "Get started by creating your first task"
          }
          isSearchState={!!searchTerm}
          searchTerm={searchTerm}
          onClearSearch={() => setSearchTerm("")}
          primaryAction={{
            label: searchTerm ? "Create Task" : "Create Your First Task",
            icon: <AddIcon />,
            onClick: () => setFormOpen(true),
          }}
        />
      )}

      {/* Task Form Dialog */}
      <TaskForm
        open={formOpen}
        onClose={handleCloseForm}
        task={editingTask}
        defaultGymId={gymId}
        onSuccess={() => {
          const message = editingTask
            ? getCrudMessage("update", "success", "task")
            : getCrudMessage("create", "success", "task");
          showSuccess(message);
        }}
        onError={(error) => {
          const message = editingTask
            ? getCrudMessage("update", "error", "task")
            : getCrudMessage("create", "error", "task");
          showError(message);
          console.error("Task form error:", error);
        }}
      />

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        {...modalConfig.deleteConfirmation}
      >
        <DialogTitle>Delete Task</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete this task? This action cannot be
            undone and may affect related executions.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setDeleteConfirmOpen(false)}
            sx={{ color: "white" }}
          >
            Cancel
          </Button>
          <Button
            onClick={confirmDelete}
            color="error"
            variant="contained"
            startIcon={<DeleteIcon />}
            disabled={deleteTaskMutation.isPending}
          >
            {deleteTaskMutation.isPending ? "Deleting..." : "Delete"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Task Detail Modal */}
      <DetailModal
        open={viewDialogOpen}
        onClose={() => setViewDialogOpen(false)}
        onEdit={
          taskToView
            ? () => {
                setViewDialogOpen(false);
                handleEdit(taskToView);
              }
            : undefined
        }
        title="Task Details"
        icon={<TaskIcon />}
        editButtonText="Edit Task"
        canEdit={!!taskToView}
      >
        {taskToView && (
          <DetailContent>
            <DetailHeader title={`Task ID: ${taskToView.task_id}`} />

            <DetailSection title="Basic Information">
              <DetailFields>
                <DetailField
                  label="UUID"
                  value={
                    <Typography
                      variant="body1"
                      sx={{ fontFamily: "monospace", fontWeight: 500 }}
                    >
                      {taskToView.uuid}
                    </Typography>
                  }
                />
                <DetailField
                  label="Gym ID"
                  value={
                    <Typography
                      variant="body1"
                      sx={{ fontFamily: "monospace", fontWeight: 500 }}
                    >
                      {taskToView.gym_id}
                    </Typography>
                  }
                />
                <DetailField
                  label="Verification Strategy"
                  value={
                    gym?.verification_strategy
                      ? gym.verification_strategy.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
                      : "Not Set"
                  }
                />
                <DetailField
                  label="Verifier Script"
                  value={
                    taskToView.verifier_path
                      ? (
                        <Typography
                          variant="body1"
                          sx={{ fontFamily: "monospace", fontWeight: 500 }}
                        >
                          {taskToView.verifier_path}
                        </Typography>
                      )
                      : "No script uploaded"
                  }
                />
              </DetailFields>
            </DetailSection>

            <DetailSection title="Prompt Details">
              <DetailField
                label="Prompt"
                value={
                  <Box>
                    <Box
                      sx={{
                        display: "flex",
                        gap: 1,
                        alignItems: "center",
                        mb: 1,
                      }}
                    >
                      {(() => {
                        const analysis = analyzePrompt(taskToView.prompt);
                        return (
                          <>
                            <Chip
                              label={getCharacterCountText(
                                analysis.characterCount,
                              )}
                              size="small"
                              variant="outlined"
                            />
                            <Chip
                              label={analysis.label}
                              size="small"
                              color={analysis.color}
                            />
                          </>
                        );
                      })()}
                    </Box>
                    <Typography
                      variant="body2"
                      sx={{
                        p: 2,
                        backgroundColor: "action.hover",
                        borderRadius: 1,
                        whiteSpace: "pre-wrap",
                        maxHeight: 200,
                        overflow: "auto",
                      }}
                    >
                      {taskToView.prompt}
                    </Typography>
                  </Box>
                }
                fullWidth
              />
            </DetailSection>

            <DetailTimestamps
              createdAt={taskToView.created_at}
              updatedAt={taskToView.updated_at}
            />
          </DetailContent>
        )}
      </DetailModal>

      {/* Notification Snackbar */}
      <NotificationSnackbar snackbar={snackbar} onClose={hideSnackbar} />
    </Box>
  );
}
