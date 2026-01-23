import { useState, useEffect } from "react";
import {
  Box,
  Button,
  Chip,
  Container,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Alert,
  CircularProgress,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  InputAdornment,
} from "@mui/material";
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Search as SearchIcon,
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
} from "@mui/icons-material";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useBatches, useDeleteBatch, useDeleteAllBatches } from "../hooks/useBatches";
import { useGyms } from "../hooks/useGyms";
import type { Batch } from "../types";
import BatchForm from "../components/BatchForm";
import { useAuth } from "../contexts/AuthContext";

export default function Batches() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [formOpen, setFormOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedGymId, setSelectedGymId] = useState<string>("");

  // Read pagination params from URL
  const page = parseInt(searchParams.get("page") || "1", 10);
  const size = parseInt(searchParams.get("size") || "10", 10);

  // Update URL when pagination changes
  const updatePagination = (newPage: number, newSize: number) => {
    const params = new URLSearchParams(searchParams);
    params.set("page", newPage.toString());
    params.set("size", newSize.toString());
    if (selectedGymId) {
      params.set("gym_id", selectedGymId);
    } else {
      params.delete("gym_id");
    }
    setSearchParams(params);
  };

  // Sync selectedGymId with URL on mount
  useEffect(() => {
    const gymIdFromUrl = searchParams.get("gym_id");
    if (gymIdFromUrl) {
      setSelectedGymId(gymIdFromUrl);
    }
  }, []);

  // Update URL when gym filter changes
  const handleGymChange = (gymId: string) => {
    setSelectedGymId(gymId);
    const params = new URLSearchParams(searchParams);
    if (gymId) {
      params.set("gym_id", gymId);
    } else {
      params.delete("gym_id");
    }
    // Reset to page 1 when filter changes
    params.set("page", "1");
    setSearchParams(params);
  };

  const { data: gyms = [] } = useGyms();
  const { data: batchesResponse, isLoading, error: queryError } = useBatches(
    {
      page,
      size,
      ...(selectedGymId ? { gym_id: selectedGymId } : {}),
    }
  );

  const batches = batchesResponse?.batches || [];
  const total = batchesResponse?.total || 0;
  const totalPages = Math.ceil(total / size);
  const deleteBatchMutation = useDeleteBatch({
    onSuccess: () => {
      setError(null);
    },
    onError: (error) => {
      setError("Failed to delete batch");
      console.error("Error deleting batch:", error);
    },
  });

  const deleteAllBatchesMutation = useDeleteAllBatches({
    onSuccess: (result) => {
      setError(null);
      alert(result.message);
    },
    onError: (error) => {
      setError(error.message || "Failed to delete all batches");
      console.error("Error deleting all batches:", error);
    },
  });

  const handleCreateBatch = () => {
    setFormOpen(true);
  };

  const handleDeleteBatch = (batch: Batch) => {
    if (window.confirm(`Are you sure you want to delete the batch "${batch.name}"?`)) {
      deleteBatchMutation.mutate(batch.uuid);
    }
  };

  const handleDeleteAllBatches = () => {
    const hasExecuting = batches.some(batch => batch.status.toLowerCase() === "executing");
    
    if (hasExecuting) {
      setError("Cannot delete batches while some are executing. Please terminate or wait for executing batches to complete.");
      return;
    }

    const confirmation = window.confirm(
      `⚠️ WARNING: This will permanently delete ALL ${total} batch(es) in the system.\n\n` +
      `This action cannot be undone and will remove:\n` +
      `- All batch records\n` +
      `- All execution data\n` +
      `- All associated files\n\n` +
      `Are you absolutely sure you want to proceed?`
    );
    
    if (confirmation) {
      const doubleConfirmation = window.confirm(
        `Please confirm one more time:\n\n` +
        `Delete ALL ${total} batches?`
      );
      
      if (doubleConfirmation) {
        deleteAllBatchesMutation.mutate();
      }
    }
  };



  const handleBatchClick = (batch: Batch) => {
    navigate(`/batches/${batch.uuid}/runs`);
  };

  const handleFormSuccess = (batch: Batch) => {
    setFormOpen(false);
    setError(null);
    // Navigate to batch runs page to see the automatically started execution
    navigate(`/batches/${batch.uuid}/runs`);
  };

  const handleFormError = (error: Error) => {
    setError(error.message);
  };

  const getDisplayStatus = (batch: Batch): string => {
    if (!batch.rerun_enabled && batch.status === "crashed") {
      return "TERMINATED";
    }
    return batch.status;
  };

  const getStatusColor = (status: string): "success" | "warning" | "error" | "default" => {
    switch (status.toLowerCase()) {
      case "completed":
        return "success";
      case "executing":
        return "warning";
      case "failed":
      case "crashed":
        return "error";
      case "terminated":
        return "default"; // Will be overridden with custom color via sx prop
      case "pending":
        return "default";
      default:
        return "default";
    }
  };

  const getStatusChipProps = (status: string) => {
    if (status.toLowerCase() === "terminated") {
      return {
        color: "default" as const,
        sx: {
          backgroundColor: "#9c27b0", // Purple color
          color: "#ffffff",
          "&:hover": {
            backgroundColor: "#7b1fa2",
          },
        },
      };
    }
    return {
      color: getStatusColor(status) as "success" | "warning" | "error" | "default",
    };
  };

  // Filter batches based on search term
  const filteredBatches = batches.filter((batch) => {
    if (!searchTerm.trim()) return true;
    
    const term = searchTerm.toLowerCase().trim();
    return (
      batch.name.toLowerCase().includes(term) ||
      batch.gym_id.toLowerCase().includes(term) ||
      batch.status.toLowerCase().includes(term)
    );
  });

  const getGymName = (gymId: string) => {
    const gym = gyms.find(g => g.uuid === gymId);
    return gym ? gym.name : gymId;
  };

  const { isAdmin } = useAuth();

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Container maxWidth="xl">
      <Box sx={{ py: 4 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
          <Typography variant="h4" component="h1">
            Batches
        </Typography>
          <Box display="flex" gap={2}>
            {isAdmin && (
              <Button
                variant="outlined"
                color="error"
                startIcon={<DeleteIcon />}
                onClick={handleDeleteAllBatches}
                disabled={deleteAllBatchesMutation.isPending || total === 0}
              >
                Delete All Batches
              </Button>
            )}
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={handleCreateBatch}
            >
              Create Batch
            </Button>
          </Box>
        </Box>

        {/* Search and Filter Controls */}
        <Box display="flex" gap={2} mb={3} alignItems="center">
          <TextField
            placeholder="Search batches by name, gym, or status..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon />
                </InputAdornment>
              ),
            }}
            sx={{ minWidth: 300 }}
          />
          <FormControl sx={{ minWidth: 200 }}>
            <InputLabel>Filter by Gym</InputLabel>
            <Select
              value={selectedGymId}
              onChange={(e) => handleGymChange(e.target.value)}
              label="Filter by Gym"
            >
              <MenuItem value="">All Gyms</MenuItem>
              {gyms.map((gym) => (
                <MenuItem key={gym.uuid} value={gym.uuid}>
                  {gym.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        {(error || queryError) && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error || (queryError as Error)?.message || "An error occurred"}
        </Alert>
      )}

        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Gym</TableCell>
                <TableCell>Created By</TableCell>
                <TableCell>Iterations</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Created</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredBatches.map((batch) => (
                <TableRow 
                  key={batch.uuid}
                  hover
                  sx={{ cursor: 'pointer' }}
                  onClick={() => handleBatchClick(batch)}
                >
                  <TableCell>
                    <Typography variant="body2" fontWeight="medium">
                      {batch.name}
                    </Typography>
                  </TableCell>
                  <TableCell>{getGymName(batch.gym_id)}</TableCell>
                <TableCell>{batch.username || "-"}</TableCell>
                  <TableCell>{batch.number_of_iterations}</TableCell>
                  <TableCell>
                    <Chip
                      label={getDisplayStatus(batch)}
                      size="small"
                      {...getStatusChipProps(getDisplayStatus(batch))}
                    />
                  </TableCell>
                  <TableCell>
                    {new Date(batch.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    {isAdmin && (
                      <IconButton 
                        size="small" 
                        onClick={() => handleDeleteBatch(batch)} 
                        disabled={batch.status === "executing"}
                        title={batch.status === "executing" ? "Cannot delete batch while executing" : "Delete Batch"}
                      >
                        <DeleteIcon />
                      </IconButton>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        {/* Pagination Controls */}
        <Box display="flex" justifyContent="space-between" alignItems="center" mt={3} gap={2}>
          <Box display="flex" alignItems="center" gap={2}>
            <Typography variant="body2" color="text.secondary">
              {total > 0
                ? `Showing ${(page - 1) * size + 1}-${Math.min(page * size, total)} of ${total} batches`
                : "No batches found"}
            </Typography>
            <FormControl size="small" sx={{ minWidth: 100 }}>
              <InputLabel>Rows</InputLabel>
              <Select
                value={size}
                label="Rows"
                onChange={(e) => {
                  const newSize = Number(e.target.value);
                  updatePagination(1, newSize);
                }}
              >
                <MenuItem value={10}>10</MenuItem>
                <MenuItem value={20}>20</MenuItem>
                <MenuItem value={50}>50</MenuItem>
              </Select>
            </FormControl>
          </Box>
          <Box display="flex" alignItems="center" gap={1}>
            <Button
              variant="outlined"
              startIcon={<ChevronLeftIcon />}
              onClick={() => updatePagination(page - 1, size)}
              disabled={page <= 1}
            >
              Previous
            </Button>
            <Typography variant="body2" sx={{ minWidth: 100, textAlign: "center" }}>
              Page {page} of {totalPages || 1}
            </Typography>
            <Button
              variant="outlined"
              endIcon={<ChevronRightIcon />}
              onClick={() => updatePagination(page + 1, size)}
              disabled={page >= totalPages}
            >
              Next
            </Button>
          </Box>
        </Box>

      <BatchForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSuccess={handleFormSuccess}
        onError={handleFormError}
      />
    </Box>
    </Container>
  );
}
