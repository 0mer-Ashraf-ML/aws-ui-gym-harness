/**
 * Token Monitoring Page
 * 
 * Displays token usage statistics, costs, and trends
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Button,
  TextField,
  MenuItem,
  Alert,
  Chip,
  Divider,
  Paper,
  Stack,
} from '@mui/material';
import {
  Download as DownloadIcon,
  Refresh as RefreshIcon,
  TrendingUp as TrendingUpIcon,
  AttachMoney as MoneyIcon,
  Speed as SpeedIcon,
  Storage as StorageIcon,
} from '@mui/icons-material';
import {
  getUsageSummary,
  downloadUsageCSV,
  getAvailableModels,
  type TokenUsageSummary,
} from '../services/monitoring';
import { getUsageGyms, getUsageBatches, type UsageGym, type UsageBatch } from '../services/monitoring';

const TokenMonitoring: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<TokenUsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedModel, setSelectedModel] = useState<string>('all');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [dateRange, setDateRange] = useState<string>('7');
  const [selectedGym, setSelectedGym] = useState<string>('all');
  const [selectedBatch, setSelectedBatch] = useState<string>('all');
  
  // State for all available models (separate from filtered summary)
  const [allModels, setAllModels] = useState<string[]>([]);

  // Data for gyms and batches from token usage snapshots (includes deleted batches)
  const [usageGyms, setUsageGyms] = useState<UsageGym[]>([]);
  const [usageBatches, setUsageBatches] = useState<UsageBatch[]>([]);
  const [allUsageBatches, setAllUsageBatches] = useState<UsageBatch[]>([]);

  useEffect(() => {
    // Load gyms snapshot
    getUsageGyms()
      .then(setUsageGyms)
      .catch((e) => console.error('Failed to load usage gyms', e));
  }, []);

  useEffect(() => {
    // Load all batches snapshot on mount and cache
    getUsageBatches()
      .then((all) => {
        setAllUsageBatches(all);
        if (selectedGym === 'all') {
          setUsageBatches(all);
        }
      })
      .catch((e) => console.error('Failed to load usage batches (all)', e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // When gym changes, use cached all or fetch filtered by gym
    if (selectedGym === 'all') {
      setUsageBatches(allUsageBatches);
    } else {
      getUsageBatches({ gym_id: selectedGym })
        .then(setUsageBatches)
        .catch((e) => console.error('Failed to load usage batches (filtered)', e));
    }
  }, [selectedGym, allUsageBatches]);

  // Load all available models on component mount
  useEffect(() => {
    const loadModels = async () => {
      try {
        const models = await getAvailableModels();
        setAllModels(models);
      } catch (err) {
        console.error('Failed to load available models:', err);
      }
    };
    loadModels();
  }, []);

  useEffect(() => {
    // Only auto-calculate dates when dateRange is NOT 'custom'
    if (dateRange !== 'custom') {
      const today = new Date();
      if (dateRange === 'today') {
        const ymd = today.toISOString().split('T')[0];
        setStartDate(ymd);
        setEndDate(ymd);
      } else {
        const days = parseInt(dateRange, 10);
        if (!Number.isNaN(days)) {
          const start = new Date(today);
          start.setDate(today.getDate() - days);
          setStartDate(start.toISOString().split('T')[0]);
          setEndDate(today.toISOString().split('T')[0]);
        }
      }
    }
    // When switching to custom, don't overwrite existing dates
  }, [dateRange]);

  useEffect(() => {
    loadData();
  }, [selectedModel, startDate, endDate, selectedGym, selectedBatch]);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = {
        model_name: selectedModel === 'all' ? undefined : selectedModel,
        start_date: startDate ? `${startDate}T00:00:00Z` : undefined,
        end_date: endDate ? `${endDate}T23:59:59Z` : undefined,
        gym_id: selectedGym === 'all' ? undefined : selectedGym,
        batch_id: selectedBatch === 'all' ? undefined : selectedBatch,
      };

      const summaryData = await getUsageSummary(params);

      setSummary(summaryData);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load usage data');
    } finally {
      setLoading(false);
    }
  };

  const handleExportCSV = async () => {
    try {
      await downloadUsageCSV({
        model_name: selectedModel === 'all' ? undefined : selectedModel,
        start_date: startDate ? `${startDate}T00:00:00Z` : undefined,
        end_date: endDate ? `${endDate}T23:59:59Z` : undefined,
        gym_id: selectedGym === 'all' ? undefined : selectedGym,
        batch_id: selectedBatch === 'all' ? undefined : selectedBatch,
      });
    } catch (err) {
      setError('Failed to export CSV');
    }
  };

  if (loading && !summary) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  // Use allModels for dropdown, summary.by_model only for display
  const models = allModels;

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1">
          Token Usage Monitoring
        </Typography>
        <Stack direction="row" spacing={2}>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={loadData}
            disabled={loading}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<DownloadIcon />}
            onClick={handleExportCSV}
          >
            Export CSV
          </Button>
        </Stack>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Filters */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Filters
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              select
              fullWidth
              label="Model"
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="all">All Models</MenuItem>
              {models.map((model) => (
                <MenuItem key={model} value={model}>
                  {model}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              fullWidth
              label="Gym"
              value={selectedGym}
              onChange={(e) => {
                const nextGym = e.target.value;
                setSelectedGym(nextGym);
                // Reset batch when gym changes
                setSelectedBatch('all');
              }}
              sx={{ minWidth: 220 }}
            >
              <MenuItem value="all">All Gyms</MenuItem>
              {usageGyms.map((gym) => (
                <MenuItem key={gym.gym_id} value={gym.gym_id}>
                  {gym.gym_name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              fullWidth
              label="Batch"
              value={selectedBatch}
              onChange={(e) => setSelectedBatch(e.target.value)}
              sx={{ minWidth: 220 }}
            >
              <MenuItem value="all">All Batches</MenuItem>
              {usageBatches.map((batch) => (
                <MenuItem key={batch.batch_id} value={batch.batch_id}>
                  {batch.batch_name}{batch.batch_is_deleted ? ' (deleted)' : ''}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              fullWidth
              label="Date Range"
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="today">Today</MenuItem>
              <MenuItem value="7">Last 7 Days</MenuItem>
              <MenuItem value="30">Last 30 Days</MenuItem>
              <MenuItem value="90">Last 90 Days</MenuItem>
              <MenuItem value="custom">Custom Range</MenuItem>
            </TextField>
            {dateRange === 'custom' && (
              <>
                <TextField
                  fullWidth
                  type="date"
                  label="Start Date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  sx={{ minWidth: 180 }}
                />
                <TextField
                  fullWidth
                  type="date"
                  label="End Date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  sx={{ minWidth: 180 }}
                />
              </>
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* Summary Stats */}
      {summary && (
        <Box 
          sx={{ 
            display: 'grid', 
            gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: '1fr 1fr 1fr 1fr' },
            gap: 3,
            mb: 3 
          }}
        >
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <StorageIcon color="primary" sx={{ mr: 1 }} />
                <Typography variant="h6">Total Tokens</Typography>
              </Box>
              <Typography variant="h4" component="div">
                {summary.total_tokens.toLocaleString()}
              </Typography>
              <Typography variant="body2" color="text.secondary" mt={1}>
                Across {Object.keys(summary.by_model).length} models
              </Typography>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <TrendingUpIcon color="info" sx={{ mr: 1 }} />
                <Typography variant="h6">Total Iterations</Typography>
              </Box>
              <Typography variant="h4" component="div">
                {Object.values(summary.by_model).reduce((sum: number, model: any) => sum + (model.iteration_count || 0), 0).toLocaleString()}
              </Typography>
              <Typography variant="body2" color="text.secondary" mt={1}>
                Unique iterations tracked
              </Typography>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <SpeedIcon color="success" sx={{ mr: 1 }} />
                <Typography variant="h6">Total Executions</Typography>
              </Box>
              <Typography variant="h4" component="div">
                {Object.values(summary.by_model).reduce((sum: number, model: any) => sum + (model.execution_count || 0), 0).toLocaleString()}
              </Typography>
              <Typography variant="body2" color="text.secondary" mt={1}>
                Unique executions tracked
              </Typography>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <MoneyIcon color="warning" sx={{ mr: 1 }} />
                <Typography variant="h6">API Calls</Typography>
              </Box>
              <Typography variant="h4" component="div">
                {summary.total_api_calls.toLocaleString()}
              </Typography>
              <Typography variant="body2" color="text.secondary" mt={1}>
                Total requests made
              </Typography>
            </CardContent>
          </Card>
        </Box>
      )}

      {/* Model Breakdown */}
      {summary && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Usage by Model
            </Typography>
            <Box 
              sx={{ 
                display: 'grid', 
                gridTemplateColumns: { xs: '1fr', md: '1fr 1fr', lg: '1fr 1fr 1fr' },
                gap: 2 
              }}
            >
              {Object.entries(summary.by_model).map(([modelName, stats]) => (
                <Paper elevation={2} sx={{ p: 2 }} key={modelName}>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                    <Typography variant="h6">
                      {modelName.toUpperCase()}
                    </Typography>
                    <Stack direction="row" spacing={1}>
                      <Chip
                        label={`${stats.iteration_count} iterations`}
                        size="small"
                        color="primary"
                        variant="filled"
                      />
                      <Chip
                        label={`${stats.execution_count} executions`}
                        size="small"
                        color="secondary"
                        variant="outlined"
                      />
                    </Stack>
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, fontStyle: 'italic' }}>
                    Model: {stats.model_versions || 'Unknown'}
                  </Typography>
                  <Divider sx={{ mb: 2 }} />
                  <Stack spacing={1}>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="text.secondary">
                        Total Tokens:
                      </Typography>
                      <Typography variant="body2" fontWeight="bold" color="primary.main">
                        {stats.total_tokens.toLocaleString()}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="text.secondary">
                        Input Tokens:
                      </Typography>
                      <Typography variant="body2">
                        {stats.total_input_tokens.toLocaleString()}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="text.secondary">
                        Output Tokens:
                      </Typography>
                      <Typography variant="body2">
                        {stats.total_output_tokens.toLocaleString()}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="text.secondary">
                        Cached Tokens:
                      </Typography>
                      <Typography variant="body2">
                        {stats.total_cached_tokens.toLocaleString()}
                      </Typography>
                    </Box>
                    <Divider sx={{ my: 1 }} />
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="text.secondary">
                        API Calls:
                      </Typography>
                      <Typography variant="body2" fontWeight="medium">
                        {stats.total_api_calls.toLocaleString()}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="text.secondary">
                        Avg. Tokens/Iteration:
                      </Typography>
                      <Typography variant="body2" fontWeight="medium">
                        {Math.round(stats.average_tokens_per_iteration).toLocaleString()}
                      </Typography>
                    </Box>
                    <Divider sx={{ my: 1 }} />
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="text.secondary" fontWeight="bold">
                        Avg. Tokens/API Call:
                      </Typography>
                      <Typography variant="body2" fontWeight="bold" color="success.main">
                        {Math.round(stats.average_tokens_per_api_call || 0).toLocaleString()}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="text.secondary" sx={{ pl: 2, fontSize: '0.75rem' }}>
                        ↳ Input:
                      </Typography>
                      <Typography variant="body2" sx={{ fontSize: '0.75rem' }}>
                        {Math.round(stats.average_input_tokens_per_api_call || 0).toLocaleString()}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" color="text.secondary" sx={{ pl: 2, fontSize: '0.75rem' }}>
                        ↳ Output:
                      </Typography>
                      <Typography variant="body2" sx={{ fontSize: '0.75rem' }}>
                        {Math.round(stats.average_output_tokens_per_api_call || 0).toLocaleString()}
                      </Typography>
                    </Box>
                  </Stack>
                </Paper>
              ))}
            </Box>
          </CardContent>
        </Card>
      )}

    </Box>
  );
};

export default TokenMonitoring;

