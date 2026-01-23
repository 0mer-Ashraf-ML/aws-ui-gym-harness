import { useState } from "react";
import {
  Box,
  Alert,
  Typography,
  Fade,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Divider,
  Chip,
} from "@mui/material";
import {
  Add as AddIcon,
  FitnessCenter as GymIcon,
  Delete as DeleteIcon,
  CheckCircle as CheckCircleIcon,
  Launch as LaunchIcon,
} from "@mui/icons-material";
import { useGyms, useDeleteGym } from "../hooks/useGyms";
import { useViewToggle } from "../hooks/useViewToggle";
import { useSnackbar, getCrudMessage } from "../hooks/useSnackbar";
import NotificationSnackbar from "../components/NotificationSnackbar";

import type { Gym } from "../types";
import GymCard from "../components/GymCard";
import GymForm from "../components/GymForm";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import PageSkeleton from "../components/PageSkeleton";
import { GymsTable } from "../components";
import { modalConfig } from "../utils/modalConfig";
import { DetailModal } from "../components/shared";

export default function Gyms() {
  const [formOpen, setFormOpen] = useState(false);
  const [editingGym, setEditingGym] = useState<Gym | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [gymToDelete, setGymToDelete] = useState<Gym | null>(null);
  const [viewDialogOpen, setViewDialogOpen] = useState(false);
  const [gymToView, setGymToView] = useState<Gym | null>(null);
  // View toggle state
  const { view, setView, isCardView } = useViewToggle("card");

  // Snackbar for notifications
  const { snackbar, showSuccess, showError, hideSnackbar } = useSnackbar();

  // Fetch gyms data
  const { data: gyms, isLoading, error } = useGyms();
  const deleteGymMutation = useDeleteGym({
    onSuccess: () => {
      showSuccess(getCrudMessage("delete", "success", "gym"));
    },
    onError: (error) => {
      showError(getCrudMessage("delete", "error", "gym"));
      console.error("Delete gym error:", error);
    },
  });

  const handleEdit = (gym: Gym) => {
    setEditingGym(gym);
    setFormOpen(true);
  };

  const handleDelete = (gym: Gym) => {
    setGymToDelete(gym);
    setDeleteConfirmOpen(true);
  };

  const handleView = (gym: Gym) => {
    setGymToView(gym);
    setViewDialogOpen(true);
  };

  const confirmDelete = () => {
    if (gymToDelete) {
      deleteGymMutation.mutate(gymToDelete.uuid, {
        onSuccess: () => {
          setDeleteConfirmOpen(false);
          setGymToDelete(null);
        },
      });
    }
  };

  const handleCloseForm = () => {
    setFormOpen(false);
    setEditingGym(null);
  };

  // Filter gyms based on search term
  const filteredGyms = gyms?.filter((gym) => {
    if (!searchTerm.trim()) return true;

    const term = searchTerm.toLowerCase().trim();
    return (
      gym.name.toLowerCase().includes(term) ||
      gym.description?.toLowerCase().includes(term) ||
      gym.base_url.toLowerCase().includes(term) ||
      gym.uuid.toLowerCase().includes(term)
    );
  });

  const sortedGyms = filteredGyms;

  // Loading state
  if (isLoading) {
    return (
      <PageSkeleton
        variant="gym"
        cardCount={6}
        showCardActions={true}
        cardLines={3}
      />
    );
  }

  // Error state
  if (error) {
    return (
      <Box sx={{ p: 2 }}>
        <Alert severity="error">
          <Typography variant="h6" gutterBottom>
            Failed to load gyms
          </Typography>
          <Typography variant="body2">
            {error.message ||
              "Please try again later or check your connection."}
          </Typography>
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <PageHeader
        icon={<GymIcon sx={{ fontSize: 48 }} />}
        title="Gym Environments"
        description="Manage your AI testing environments and automation targets"
        searchPlaceholder="Search gyms by name, description, URL, or UUID..."
        searchValue={searchTerm}
        onSearchChange={setSearchTerm}
        viewToggle={{
          view,
          onChange: setView,
        }}
        primaryButton={{
          label: "Create Gym",
          icon: <AddIcon />,
          onClick: () => setFormOpen(true),
        }}
      />

      {/* Gyms Content */}
      {sortedGyms && sortedGyms.length > 0 ? (
        isCardView ? (
          <Fade in timeout={300}>
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
              {sortedGyms.map((gym) => (
                <GymCard gym={gym} onEdit={handleEdit} key={gym.uuid} />
              ))}
            </Box>
          </Fade>
        ) : (
          <GymsTable
            gyms={sortedGyms}
            onEdit={handleEdit}
            onView={handleView}
            onDelete={handleDelete}
            isLoading={isLoading}
          />
        )
      ) : (
        <EmptyState
          icon={<GymIcon />}
          title={
            searchTerm ? "No gyms match your search" : "No gym environments yet"
          }
          description={
            searchTerm
              ? "No gyms found matching"
              : "Get started by creating your first gym environment. Gyms are the foundation for organizing your AI automation tasks and testing scenarios."
          }
          isSearchState={!!searchTerm}
          searchTerm={searchTerm}
          onClearSearch={() => setSearchTerm("")}
          primaryAction={{
            label: searchTerm ? "Create New Gym" : "Create Your First Gym",
            icon: <AddIcon />,
            onClick: () => setFormOpen(true),
          }}
        />
      )}

      {/* Gym Form Dialog */}
      <GymForm
        open={formOpen}
        onClose={handleCloseForm}
        gym={editingGym}
        onSuccess={() => {
          const message = editingGym
            ? getCrudMessage("update", "success", "gym")
            : getCrudMessage("create", "success", "gym");
          showSuccess(message);
        }}
        onError={(error) => {
          const message = editingGym
            ? getCrudMessage("update", "error", "gym")
            : getCrudMessage("create", "error", "gym");
          showError(message);
          console.error("Gym form error:", error);
        }}
      />

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        {...modalConfig.deleteConfirmation}
      >
        <DialogTitle>Delete Gym</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete "{gymToDelete?.name}"? This action
            cannot be undone and may affect related tasks and executions.
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
            disabled={deleteGymMutation.isPending}
          >
            {deleteGymMutation.isPending ? "Deleting..." : "Delete"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Gym Detail Modal */}
      <DetailModal
        open={viewDialogOpen}
        onClose={() => setViewDialogOpen(false)}
        onEdit={
          gymToView
            ? () => {
                setViewDialogOpen(false);
                handleEdit(gymToView);
              }
            : undefined
        }
        title="Gym Details"
        icon={<GymIcon />}
        editButtonText="Edit Gym"
        canEdit={!!gymToView}
      >
        {gymToView && (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <Box>
              <Typography variant="h5" gutterBottom>
                {gymToView.name}
              </Typography>
              <Typography variant="body1" color="text.secondary" paragraph>
                {gymToView.description || "No description provided"}
              </Typography>
            </Box>

            <Divider />

            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
              <Box sx={{ flex: { xs: "1 1 100%", sm: "1 1 45%" } }}>
                <Typography
                  variant="subtitle2"
                  color="text.secondary"
                  gutterBottom
                >
                  Gym ID
                </Typography>
                <Typography
                  variant="body1"
                  sx={{ fontFamily: "monospace", fontWeight: 500 }}
                >
                  {gymToView.uuid}
                </Typography>
              </Box>

              <Box sx={{ flex: { xs: "1 1 100%", sm: "1 1 45%" } }}>
                <Typography
                  variant="subtitle2"
                  color="text.secondary"
                  gutterBottom
                >
                  Verification
                </Typography>
                <Chip
                  label={gymToView.verification_strategy.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  color="success"
                  icon={<CheckCircleIcon />}
                />
              </Box>
            </Box>

            <Box>
              <Typography
                variant="subtitle2"
                color="text.secondary"
                gutterBottom
              >
                Base URL
              </Typography>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography variant="body1" sx={{ fontFamily: "monospace" }}>
                  {gymToView.base_url}
                </Typography>
                <Button
                  size="small"
                  startIcon={<LaunchIcon />}
                  onClick={() => window.open(gymToView.base_url, "_blank")}
                >
                  Open
                </Button>
              </Box>
            </Box>

            <Box>
              <Typography
                variant="subtitle2"
                color="text.secondary"
                gutterBottom
              >
                Verification Strategy
              </Typography>
              <Typography variant="body1" sx={{ fontFamily: "monospace" }}>
                {gymToView.verification_strategy.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
              </Typography>
            </Box>

            <Divider />

            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
              <Box sx={{ flex: { xs: "1 1 100%", sm: "1 1 45%" } }}>
                <Typography
                  variant="subtitle2"
                  color="text.secondary"
                  gutterBottom
                >
                  Created
                </Typography>
                <Typography variant="body1">
                  {gymToView.created_at
                    ? `${new Date(gymToView.created_at).toLocaleDateString()} at ${new Date(gymToView.created_at).toLocaleTimeString()}`
                    : "Unknown"}
                </Typography>
              </Box>

              <Box sx={{ flex: { xs: "1 1 100%", sm: "1 1 45%" } }}>
                <Typography
                  variant="subtitle2"
                  color="text.secondary"
                  gutterBottom
                >
                  Last Updated
                </Typography>
                <Typography variant="body1">
                  {gymToView.updated_at
                    ? `${new Date(gymToView.updated_at).toLocaleDateString()} at ${new Date(gymToView.updated_at).toLocaleTimeString()}`
                    : "Unknown"}
                </Typography>
              </Box>
            </Box>
          </Box>
        )}
      </DetailModal>

      {/* Notification Snackbar */}
      <NotificationSnackbar snackbar={snackbar} onClose={hideSnackbar} />
    </Box>
  );
}
