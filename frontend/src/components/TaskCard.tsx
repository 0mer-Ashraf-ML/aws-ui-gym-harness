import { useState } from "react";
import {
  Card,
  CardContent,
  CardActions,
  Typography,
  Box,
  Chip,
  CircularProgress,
} from "@mui/material";
import {
  Edit as EditIcon,
  Delete as DeleteIcon,
  Assignment as TaskIcon,
  Download as DownloadIcon,
} from "@mui/icons-material";
import type { Task } from "../types";
import { useDeleteTask } from "../hooks/useTasks";
import { useGyms } from "../hooks/useGyms";
import { useAuth } from "../contexts/AuthContext";
import { sharedTheme } from "../utils/sharedStyles";
import { ActionButton } from "../utils/runUtils";
import {
  analyzePrompt,
  getCharacterCountText,
  truncatePrompt,
} from "../utils/promptUtils";
import { downloadJSON } from "../utils/downloadUtils";
import { taskApi } from "../services/api";
import {
  DetailModal,
  DeleteConfirmationModal,
  DetailContent,
  DetailSection,
  DetailFields,
  DetailField,
  DetailTimestamps,
} from "./shared";

interface TaskCardProps {
  task: Task;
  onEdit: (task: Task) => void;
}

export default function TaskCard({ task, onEdit }: TaskCardProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const deleteTaskMutation = useDeleteTask();
  const { data: gyms = [] } = useGyms();
  const { isAdmin } = useAuth();

  const gym = gyms.find((g) => g.uuid === task.gym_id);

  const handleDelete = () => {
    deleteTaskMutation.mutate(task.uuid, {
      onSuccess: () => {
        setDeleteConfirmOpen(false);
      },
    });
  };

  const handleDownload = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsDownloading(true);
    try {
      const exportData = await taskApi.export(task.uuid);
      downloadJSON(exportData, `${task.task_id}.json`);
    } catch (error) {
      console.error("Error downloading task:", error);
      alert("Failed to download task. Please try again.");
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <>
      <Card
        sx={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
          cursor: "pointer",
          "&:hover": {
            boxShadow: 4,
          },
        }}
        onClick={() => setDetailsOpen(true)}
      >
        <CardContent
          sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
            <TaskIcon color="primary" />
            <Typography variant="h6" component="h2">
              Task #{task.task_id}
            </Typography>
          </Box>

          <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ mb: 1, lineHeight: 1.4, flexGrow: 1 }}
            >
              {truncatePrompt(task.prompt)}
            </Typography>

            <Box
              sx={{
                display: "flex",
                flexWrap: "wrap",
                gap: 1,
                mt: "auto",
                justifyContent: "center",
                alignItems: "center",
                pt: 2,
              }}
            >
              <Chip
                label={gym?.name || "Unknown Gym"}
                variant="outlined"
                size="small"
                sx={{
                  ...sharedTheme.actionButton,
                  fontSize: "0.75rem",
                  fontWeight: 500,
                }}
              />
            </Box>
          </Box>
        </CardContent>

        <CardActions sx={{ justifyContent: "flex-end", px: 2, pb: 2 }}>
          <Box>
            <ActionButton
              icon={<EditIcon />}
              onClick={(e) => {
                e.stopPropagation();
                onEdit(task);
              }}
              tooltip="Edit"
              color="inherit"
            />
            <ActionButton
              icon={isDownloading ? <CircularProgress size={20} /> : <DownloadIcon />}
              onClick={handleDownload}
              tooltip="Download JSON"
              color="inherit"
              disabled={isDownloading}
            />
            {isAdmin && (
              <ActionButton
                icon={<DeleteIcon />}
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteConfirmOpen(true);
                }}
                tooltip="Delete"
                color="error"
              />
            )}
          </Box>
        </CardActions>
      </Card>

      {/* Details Modal */}
      <DetailModal
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        onEdit={() => {
          setDetailsOpen(false);
          onEdit(task);
        }}
        title={`Task #${task.task_id}`}
        icon={<TaskIcon />}
        editButtonText="Edit"
        canEdit={true}
      >
        <DetailContent>
          <DetailSection title="Basic Information">
            <DetailFields>
              <DetailField
                label="Task ID"
                value={
                  <Typography
                    variant="body1"
                    sx={{ fontFamily: "monospace", fontWeight: 500 }}
                  >
                    {task.task_id}
                  </Typography>
                }
              />
              <DetailField
                label="UUID"
                value={
                  <Typography
                    variant="body1"
                    sx={{ fontFamily: "monospace", fontWeight: 500 }}
                  >
                    {task.uuid}
                  </Typography>
                }
              />
              <DetailField
                label="Gym"
                value={gym?.name || "Unknown Gym"}
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
                  task.verifier_path
                    ? (
                      <Typography
                        variant="body1"
                        sx={{ fontFamily: "monospace", fontWeight: 500 }}
                      >
                        {task.verifier_path}
                      </Typography>
                    )
                    : "No script uploaded"
                }
              />
            </DetailFields>
          </DetailSection>

          <DetailSection title="Task Details">
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
                      const analysis = analyzePrompt(task.prompt);
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
                    {task.prompt}
                  </Typography>
                </Box>
              }
              fullWidth
            />
          </DetailSection>

          <DetailTimestamps
            createdAt={task.created_at}
            updatedAt={task.updated_at}
          />
        </DetailContent>
      </DetailModal>

      {/* Delete Confirmation Modal */}
      <DeleteConfirmationModal
        open={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        onConfirm={handleDelete}
        item={{ uuid: task.uuid }}
        isLoading={deleteTaskMutation.isPending}
        title="Delete Task"
        message={`Are you sure you want to delete Task #${task.task_id}? This action cannot be undone.`}
      />
    </>
  );
}
