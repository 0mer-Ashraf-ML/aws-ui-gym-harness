import { useState, useMemo } from "react";
import {
  Typography,
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip,
  Divider,
} from "@mui/material";
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  ModelTraining as ModelTrainingIcon,
  Key as KeyIcon,
} from "@mui/icons-material";
import type { Model } from "../types";
import { useModels, useDeleteModel } from "../hooks/useModels";
import { useViewToggle } from "../hooks/useViewToggle";
import { useSorting } from "../hooks/useSorting";
import { useFiltering, type FilterCategory } from "../hooks/useFiltering";
import { useSnackbar, getCrudMessage } from "../hooks/useSnackbar";
import SortMenu from "../components/SortMenu";
import FilterMenu from "../components/FilterMenu";
import NotificationSnackbar from "../components/NotificationSnackbar";
import ModelCard from "../components/ModelCard";
import ModelForm from "../components/ModelForm";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import PageSkeleton from "../components/PageSkeleton";
import { ModelsTable } from "../components";
import { modalConfig } from "../utils/modalConfig";
import { DetailModal } from "../components/shared";

export default function Models() {
  const { data: models = [], isLoading } = useModels();

  // Snackbar for notifications
  const { snackbar, showSuccess, showError, hideSnackbar } = useSnackbar();

  const deleteModelMutation = useDeleteModel({
    onSuccess: () => {
      showSuccess(getCrudMessage("delete", "success", "model"));
    },
    onError: (error) => {
      showError(getCrudMessage("delete", "error", "model"));
      console.error("Delete model error:", error);
    },
  });
  const { view, setView, isCardView } = useViewToggle("card");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedModel, setSelectedModel] = useState<Model | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [modelToDelete, setModelToDelete] = useState<Model | null>(null);
  const [viewDialogOpen, setViewDialogOpen] = useState(false);
  const [modelToView, setModelToView] = useState<Model | null>(null);

  // Data processing pipeline: search -> filter -> sort
  const { searchedModels, filterCategories } = useMemo(() => {
    const searchLower = searchTerm.toLowerCase();
    const searched = models.filter(
      (model) =>
        model.name.toLowerCase().includes(searchLower) ||
        model.description.toLowerCase().includes(searchLower) ||
        model.type.toLowerCase().includes(searchLower),
    );

    const types = [...new Set(models.map((model) => model.type))];

    const categories: FilterCategory<Model>[] = [
      { key: "type", label: "Model Type", options: types },
    ];

    return { searchedModels: searched, filterCategories: categories };
  }, [models, searchTerm]);

  const { filteredItems, activeFilters, toggleFilter, clearFilters } =
    useFiltering(searchedModels, filterCategories);

  const sortOptions = [
    { value: "created_at", label: "Sort by Date" },
    { value: "name", label: "Sort by Name" },
    { value: "type", label: "Sort by Type" },
  ];

  const {
    sortedItems: sortedModels,
    requestSort,
    sortConfig,
  } = useSorting(filteredItems || [], sortOptions, {
    key: "created_at",
    direction: "desc",
  });

  const handleAddModel = () => {
    setSelectedModel(null);
    setIsFormOpen(true);
  };

  const handleEdit = (model: Model) => {
    setSelectedModel(model);
    setIsFormOpen(true);
  };

  const handleDelete = (model: Model) => {
    setModelToDelete(model);
    setDeleteConfirmOpen(true);
  };

  const handleView = (model: Model) => {
    setModelToView(model);
    setViewDialogOpen(true);
  };

  const confirmDelete = () => {
    if (modelToDelete) {
      deleteModelMutation.mutate(modelToDelete.id, {
        onSuccess: () => {
          setDeleteConfirmOpen(false);
          setModelToDelete(null);
        },
      });
    }
  };

  const handleCloseForm = () => {
    setIsFormOpen(false);
    setSelectedModel(null);
  };

  return (
    <Box>
      <PageHeader
        icon={<ModelTrainingIcon sx={{ fontSize: 48 }} />}
        title="Models"
        description="Manage your AI models and configurations"
        searchPlaceholder="Search models..."
        searchValue={searchTerm}
        onSearchChange={setSearchTerm}
        viewToggle={{
          view,
          onChange: setView,
          disabled: sortedModels.length === 0,
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
        primaryButton={{
          label: "Add Model",
          icon: <AddIcon />,
          onClick: handleAddModel,
        }}
      />

      {isLoading ? (
        <PageSkeleton
          variant="model"
          cardCount={6}
          showCardActions={true}
          cardLines={2}
        />
      ) : sortedModels.length === 0 ? (
        <EmptyState
          icon={<ModelTrainingIcon />}
          title={searchTerm ? "No models found" : "No models yet"}
          description={
            searchTerm
              ? "Try adjusting your search terms"
              : "Get started by adding your first model"
          }
          isSearchState={!!searchTerm}
          searchTerm={searchTerm}
          onClearSearch={() => setSearchTerm("")}
          primaryAction={{
            label: searchTerm ? "Add Model" : "Add Your First Model",
            icon: <AddIcon />,
            onClick: handleAddModel,
          }}
        />
      ) : sortedModels && sortedModels.length > 0 ? (
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
            {sortedModels.map((model) => (
              <ModelCard
                key={model.id}
                model={model}
                onEdit={handleEdit}
                onDelete={handleDelete}
                onView={handleView}
              />
            ))}
          </Box>
        ) : (
          <ModelsTable
            models={sortedModels}
            onEdit={handleEdit}
            onView={handleView}
            onDelete={handleDelete}
            isLoading={isLoading}
          />
        )
      ) : (
        <EmptyState
          icon={<ModelTrainingIcon />}
          title={searchTerm ? "No models match your search" : "No models found"}
          description={
            searchTerm
              ? "Try adjusting your search terms"
              : "Get started by creating your first model"
          }
          isSearchState={!!searchTerm}
          searchTerm={searchTerm}
          onClearSearch={() => setSearchTerm("")}
          primaryAction={{
            label: searchTerm ? "Create Model" : "Create Your First Model",
            icon: <AddIcon />,
            onClick: () => setIsFormOpen(true),
          }}
        />
      )}

      <ModelForm
        open={isFormOpen}
        onClose={handleCloseForm}
        model={selectedModel}
        onSuccess={() => {
          const message = selectedModel
            ? getCrudMessage("update", "success", "model")
            : getCrudMessage("create", "success", "model");
          showSuccess(message);
        }}
        onError={(error) => {
          const message = selectedModel
            ? getCrudMessage("update", "error", "model")
            : getCrudMessage("create", "error", "model");
          showError(message);
          console.error("Model form error:", error);
        }}
      />

      <Dialog
        open={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        {...modalConfig.deleteConfirmation}
      >
        <DialogTitle>Delete Model</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete "{modelToDelete?.name}"? This action
            cannot be undone.
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
            disabled={deleteModelMutation.isPending}
          >
            {deleteModelMutation.isPending ? "Deleting..." : "Delete"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Model Detail Modal */}
      <DetailModal
        open={viewDialogOpen}
        onClose={() => setViewDialogOpen(false)}
        onEdit={
          modelToView
            ? () => {
                setViewDialogOpen(false);
                handleEdit(modelToView);
              }
            : undefined
        }
        title="Model Details"
        icon={<ModelTrainingIcon />}
        editButtonText="Edit Model"
        canEdit={!!modelToView}
      >
        {modelToView && (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <Box>
              <Typography variant="h5" gutterBottom>
                {modelToView.name}
              </Typography>
              <Typography variant="body1" color="text.secondary" paragraph>
                {modelToView.description || "No description provided"}
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
                  Model ID
                </Typography>
                <Typography
                  variant="body1"
                  sx={{ fontFamily: "monospace", fontWeight: 500 }}
                >
                  {modelToView.id}
                </Typography>
              </Box>

              <Box sx={{ flex: { xs: "1 1 100%", sm: "1 1 45%" } }}>
                <Typography
                  variant="subtitle2"
                  color="text.secondary"
                  gutterBottom
                >
                  Type
                </Typography>
                <Chip
                  label={modelToView.type}
                  color={
                    modelToView.type?.toLowerCase() === "openai"
                      ? "success"
                      : modelToView.type?.toLowerCase() === "anthropic"
                        ? "info"
                        : "default"
                  }
                  sx={{ textTransform: "capitalize" }}
                />
              </Box>
            </Box>

            <Box>
              <Typography
                variant="subtitle2"
                color="text.secondary"
                gutterBottom
              >
                API Key
              </Typography>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <KeyIcon sx={{ fontSize: 16, color: "success.main" }} />
                <Typography variant="body1" sx={{ fontFamily: "monospace" }}>
                  {modelToView.api_key
                    ? `${modelToView.api_key.slice(0, 8)}${"*".repeat(Math.max(0, modelToView.api_key.length - 12))}${modelToView.api_key.slice(-4)}`
                    : "Not configured"}
                </Typography>
              </Box>
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
                  {modelToView.created_at
                    ? `${new Date(modelToView.created_at).toLocaleDateString()} at ${new Date(modelToView.created_at).toLocaleTimeString()}`
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
                  {modelToView.updated_at
                    ? `${new Date(modelToView.updated_at).toLocaleDateString()} at ${new Date(modelToView.updated_at).toLocaleTimeString()}`
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
