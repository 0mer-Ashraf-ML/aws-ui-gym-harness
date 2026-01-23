import { useState, useEffect } from "react";
import {
  Box,
  Card,
  CardContent,
  Chip,
  Typography,
  Alert,
  CircularProgress,
} from "@mui/material";
import api from "../services/api";
import BatchInsightsTabs from "./BatchInsightsTabs";
import type { Batch } from "../types";

interface BatchDetailProps {
  batchId: string;
}

export default function BatchDetail({ batchId }: BatchDetailProps) {
  const [batch, setBatch] = useState<Batch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadBatch();
  }, [batchId]);

  const loadBatch = async () => {
    try {
      setLoading(true);
      const response = await api.batchApi.getById(batchId);
      setBatch(response);
    } catch (err) {
      setError("Failed to load batch details");
      console.error("Error loading batch:", err);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed":
        return "success";
      case "executing":
        return "warning";
      case "failed":
        return "error";
      case "crashed":
        return "error";
      case "pending":
        return "info";
      default:
        return "default";
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="200px">
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!batch) {
    return <Alert severity="warning">Batch not found</Alert>;
  }

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Typography variant="h6" component="h2" gutterBottom>
            {batch.name}
          </Typography>
          
          <Box>
            <Typography variant="subtitle2" color="text.secondary">
              Batch ID
            </Typography>
            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
              {batch.uuid}
            </Typography>
          </Box>
          
          <Box>
            <Typography variant="subtitle2" color="text.secondary">
              Gym ID
            </Typography>
            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
              {batch.gym_id}
            </Typography>
          </Box>
          
          <Box>
            <Typography variant="subtitle2" color="text.secondary">
              Iterations
            </Typography>
            <Typography variant="body2">{batch.number_of_iterations}</Typography>
          </Box>
          
          <Box>
            <Typography variant="subtitle2" color="text.secondary">
              Status
            </Typography>
            <Chip
              label={batch.status}
              color={getStatusColor(batch.status) as any}
              size="small"
            />
          </Box>
          
          <Box>
            <Typography variant="subtitle2" color="text.secondary">
              Created
            </Typography>
            <Typography variant="body2">
              {new Date(batch.created_at).toLocaleString()}
            </Typography>
          </Box>
          
          <Box>
            <Typography variant="subtitle2" color="text.secondary">
              Updated
            </Typography>
            <Typography variant="body2">
              {new Date(batch.updated_at).toLocaleString()}
            </Typography>
          </Box>
        </Box>
        
        <BatchInsightsTabs evalInsights={batch.eval_insights} />
      </CardContent>
    </Card>
  );
}
