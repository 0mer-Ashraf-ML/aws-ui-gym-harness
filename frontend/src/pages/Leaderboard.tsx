/**
 * Leaderboard Page
 * 
 * Displays fail percentage statistics with filters for batches, date range, and gyms
 */

import { useState, useMemo } from "react";
import {
  Box,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  TextField,
  MenuItem,
  Alert,
  Stack,
  Chip,
  FormControl,
  InputLabel,
  Select,
  Autocomplete,
} from "@mui/material";
import type { SelectChangeEvent } from "@mui/material";
import {
  LocalizationProvider,
  DatePicker,
} from "@mui/x-date-pickers";
import { AdapterDateFns } from "@mui/x-date-pickers/AdapterDateFns";
import ReactECharts from "echarts-for-react";
import { useLeaderboard, type LeaderboardFilters } from "../hooks/useLeaderboard";
import { useBatchMetadata } from "../hooks/useBatches";
import { useGyms } from "../hooks/useGyms";
import { format } from "date-fns";
import type { BatchMetadata } from "../types";

// Model colors matching the examples
const MODEL_COLORS: Record<string, string> = {
  gemini: "#ff9800", // Orange/light brown for Gemini
  anthropic: "#9c27b0", // Purple/blue for Sonnet 4
  openai: "#00bcd4", // Teal/green for OpenAI
  unified: "#607d8b", // Gray for unified
};

// Helper function to get model display name
const getModelDisplayName = (model: string): string => {
  const modelLower = model.toLowerCase();
  if (modelLower.includes("gemini")) return "Gemini 2.5";
  if (modelLower.includes("anthropic") || modelLower.includes("sonnet")) return "Sonnet 4";
  if (modelLower.includes("openai")) return "OpenAI Operator";
  return model.charAt(0).toUpperCase() + model.slice(1);
};

// Helper function to get model color
const getModelColor = (model: string): string => {
  const modelLower = model.toLowerCase();
  if (modelLower.includes("gemini")) return MODEL_COLORS.gemini;
  if (modelLower.includes("anthropic") || modelLower.includes("sonnet")) return MODEL_COLORS.anthropic;
  if (modelLower.includes("openai")) return MODEL_COLORS.openai;
  return MODEL_COLORS.unified;
};

export default function Leaderboard() {
  // Filter states
  const [batchFilterType, setBatchFilterType] = useState<"all" | "last5" | "last10" | "last20" | "last30" | "specific">("all");
  const [selectedBatchIds, setSelectedBatchIds] = useState<string[]>([]);
  const [startDate, setStartDate] = useState<Date | null>(null);
  const [endDate, setEndDate] = useState<Date | null>(null);
  const [selectedGymIds, setSelectedGymIds] = useState<string[]>([]);

  // Fetch data
  const { data: batches = [], isLoading: batchesLoading } = useBatchMetadata();
  const { data: gyms = [], isLoading: gymsLoading } = useGyms();

  // Get batches based on filter type
  const filteredBatches = useMemo(() => {
    if (batchFilterType === "all") {
      return [];
    } else if (batchFilterType === "specific") {
      return batches.filter((b: BatchMetadata) => selectedBatchIds.includes(b.uuid));
    } else {
      // last5, last10, last20, last30
      const count = parseInt(batchFilterType.replace("last", ""));
      const sortedBatches = [...batches].sort(
        (a: BatchMetadata, b: BatchMetadata) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      return sortedBatches.slice(0, count);
    }
  }, [batchFilterType, selectedBatchIds, batches]);

  // Build filters for API
  const filters = useMemo<LeaderboardFilters | undefined>(() => {
    const filter: LeaderboardFilters = {};

    // Batch filter
    if (batchFilterType !== "all") {
      if (batchFilterType === "specific" && selectedBatchIds.length > 0) {
        filter.batch_ids = selectedBatchIds;
      } else if (filteredBatches.length > 0) {
        filter.batch_ids = filteredBatches.map((b: BatchMetadata) => b.uuid);
      }
    }

    // Date range filter - use UTC to avoid timezone issues
    if (startDate) {
      // Set to start of day in UTC
      const utcStart = new Date(Date.UTC(
        startDate.getFullYear(),
        startDate.getMonth(),
        startDate.getDate(),
        0, 0, 0
      ));
      filter.start_date = utcStart.toISOString();
    }
    if (endDate) {
      // Set to end of day in UTC
      const utcEnd = new Date(Date.UTC(
        endDate.getFullYear(),
        endDate.getMonth(),
        endDate.getDate(),
        23, 59, 59
      ));
      filter.end_date = utcEnd.toISOString();
    }

    // Gym filter
    if (selectedGymIds.length > 0) {
      filter.gym_ids = selectedGymIds;
    }

    // Return undefined if no filters (show all data)
    const hasFilters = 
      filter.batch_ids?.length || 
      filter.start_date || 
      filter.end_date || 
      filter.gym_ids?.length;
    
    return hasFilters ? filter : undefined;
  }, [batchFilterType, selectedBatchIds, startDate, endDate, selectedGymIds, filteredBatches]);

  // Fetch leaderboard data
  const {
    data: leaderboardData,
    isLoading: leaderboardLoading,
    error: leaderboardError,
  } = useLeaderboard(filters);

  // Prepare chart data for Model Performance By Environment (Gym)
  const modelGymChartData = useMemo(() => {
    if (!leaderboardData || !leaderboardData.model_gym_stats.length) return [];
    
    // Group by gym, then by model
    const gymMap = new Map<string, Array<{ model: string; failPercentage: number; totalCount: number }>>();
    
    leaderboardData.model_gym_stats.forEach((stat) => {
      if (!gymMap.has(stat.gym_name)) {
        gymMap.set(stat.gym_name, []);
      }
      gymMap.get(stat.gym_name)!.push({
        model: stat.model,
        failPercentage: stat.fail_percentage,
        totalCount: stat.total_count,
      });
    });
    
    // Build data structure for horizontal bar chart
    // Each gym becomes a row, with bars for each model
    const chartData: Array<Record<string, string | number>> = [];
    const allModels = new Set<string>();
    
    leaderboardData.model_gym_stats.forEach((stat) => {
      allModels.add(stat.model);
    });
    
    const sortedModels = Array.from(allModels).sort();
    
    gymMap.forEach((models, gymName) => {
      const row: Record<string, string | number> = {
        environment: gymName,
      };
      
      models.forEach((modelData) => {
        row[getModelDisplayName(modelData.model)] = modelData.failPercentage;
      });
      
      // Fill in missing models with 0
      sortedModels.forEach((model) => {
        const displayName = getModelDisplayName(model);
        if (!(displayName in row)) {
          row[displayName] = 0;
        }
      });
      
      chartData.push(row);
    });
    
    return chartData;
  }, [leaderboardData]);

  // Prepare chart data for Overall Model Performance (first chart - 3 bars, one per model)
  const modelChartData = useMemo(() => {
    if (!leaderboardData || !leaderboardData.model_stats.length) return [];
    
    // Sort by model name for consistent ordering
    return leaderboardData.model_stats
      .map((stat) => ({
        model: getModelDisplayName(stat.model),
        "Agent Failing Percentage": stat.fail_percentage,
        totalCount: stat.total_count,
        originalModel: stat.model, // Keep original for color lookup
      }))
      .sort((a, b) => a.model.localeCompare(b.model));
  }, [leaderboardData]);

  const isLoading = batchesLoading || gymsLoading || leaderboardLoading;

  return (
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Box sx={{ p: 3 }}>
        <Typography variant="h4" gutterBottom>
          Leaderboard
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          View fail percentage statistics for iterations across batches and gyms
        </Typography>

        {/* Filters Section */}
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Filters
            </Typography>
            <Stack spacing={3} sx={{ mt: 2 }}>
              {/* Batch Filter Section */}
              <Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Batch Selection
                </Typography>
                <Stack spacing={2} direction={{ xs: "column", sm: "row" }}>
                  <FormControl sx={{ minWidth: { xs: "100%", sm: 200 } }}>
                    <InputLabel>Filter Type</InputLabel>
                    <Select
                      value={batchFilterType}
                      label="Filter Type"
                      onChange={(e: SelectChangeEvent) => {
                        setBatchFilterType(e.target.value as "all" | "last5" | "last10" | "last20" | "last30" | "specific");
                        if (e.target.value !== "specific") {
                          setSelectedBatchIds([]);
                        }
                      }}
                    >
                      <MenuItem value="all">All Batches</MenuItem>
                      <MenuItem value="last5">Last 5 Batches</MenuItem>
                      <MenuItem value="last10">Last 10 Batches</MenuItem>
                      <MenuItem value="last20">Last 20 Batches</MenuItem>
                      <MenuItem value="last30">Last 30 Batches</MenuItem>
                      <MenuItem value="specific">Specific Batches</MenuItem>
                    </Select>
                  </FormControl>

                  {batchFilterType === "specific" && (
                    <Autocomplete
                      multiple
                      options={batches}
                      getOptionLabel={(option: BatchMetadata) => `${option.name} (${new Date(option.created_at).toLocaleDateString()})`}
                      value={batches.filter((b: BatchMetadata) => selectedBatchIds.includes(b.uuid))}
                      onChange={(_, newValue) => {
                        setSelectedBatchIds(newValue.map((b) => b.uuid));
                      }}
                      renderInput={(params) => (
                        <TextField {...params} label="Select Batches" placeholder="Choose batches" />
                      )}
                      sx={{ flex: 1, minWidth: { xs: "100%", sm: 300 } }}
                    />
                  )}
                </Stack>

                {/* Show selected batches when using last N batches */}
                {batchFilterType !== "all" && batchFilterType !== "specific" && filteredBatches.length > 0 && (
                  <Box sx={{ mt: 2 }}>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Selected Batches ({filteredBatches.length}):
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                      {filteredBatches.map((batch: BatchMetadata) => (
                        <Chip
                          key={batch.uuid}
                          label={`${batch.name} (${new Date(batch.created_at).toLocaleDateString()})`}
                          size="small"
                          sx={{ fontSize: "0.75rem" }}
                        />
                      ))}
                    </Stack>
                  </Box>
                )}

                {/* Show selected batches when using specific batches */}
                {batchFilterType === "specific" && selectedBatchIds.length > 0 && (
                  <Box sx={{ mt: 2 }}>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Selected Batches ({selectedBatchIds.length}):
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                      {batches
                        .filter((b: BatchMetadata) => selectedBatchIds.includes(b.uuid))
                        .map((batch: BatchMetadata) => (
                          <Chip
                            key={batch.uuid}
                            label={`${batch.name} (${new Date(batch.created_at).toLocaleDateString()})`}
                            size="small"
                            onDelete={() => {
                              setSelectedBatchIds(selectedBatchIds.filter((id) => id !== batch.uuid));
                            }}
                            sx={{ fontSize: "0.75rem" }}
                          />
                        ))}
                    </Stack>
                  </Box>
                )}
              </Box>

              {/* Date Range Section */}
              <Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Date Range
                </Typography>
                <Stack spacing={2} direction={{ xs: "column", sm: "row" }}>
                  <DatePicker
                    label="Start Date"
                    value={startDate}
                    onChange={(newValue) => setStartDate(newValue)}
                    maxDate={new Date()}
                    slotProps={{ textField: { fullWidth: true } }}
                    sx={{ flex: 1 }}
                  />
                  <DatePicker
                    label="End Date"
                    value={endDate}
                    onChange={(newValue) => setEndDate(newValue)}
                    maxDate={new Date()}
                    slotProps={{ textField: { fullWidth: true } }}
                    sx={{ flex: 1 }}
                  />
                </Stack>
              </Box>

              {/* Gym Filter Section */}
              <Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Gym Selection
                </Typography>
                <Autocomplete
                  multiple
                  options={gyms}
                  getOptionLabel={(option) => option.name}
                  value={gyms.filter((g) => selectedGymIds.includes(g.uuid))}
                  onChange={(_, newValue) => {
                    setSelectedGymIds(newValue.map((g) => g.uuid));
                  }}
                  renderInput={(params) => (
                    <TextField {...params} label="Select Gyms" placeholder="All gyms if empty" />
                  )}
                  fullWidth
                />
              </Box>
            </Stack>

            {/* Active Filters Display */}
            {(batchFilterType !== "all" ||
              startDate ||
              endDate ||
              selectedGymIds.length > 0) && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Active Filters:
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" gap={1}>
                  {batchFilterType !== "all" && batchFilterType !== "specific" && (
                    <Chip
                      label={`${batchFilterType.replace("last", "").toUpperCase()} Batches`}
                      size="small"
                      onDelete={() => {
                        setBatchFilterType("all");
                      }}
                    />
                  )}
                  {batchFilterType === "specific" && selectedBatchIds.length > 0 && (
                    <Chip
                      label={`${selectedBatchIds.length} Batch(es)`}
                      size="small"
                      onDelete={() => {
                        setBatchFilterType("all");
                        setSelectedBatchIds([]);
                      }}
                    />
                  )}
                  {startDate && (
                    <Chip
                      label={`From: ${format(startDate, "MMM dd, yyyy")}`}
                      size="small"
                      onDelete={() => setStartDate(null)}
                    />
                  )}
                  {endDate && (
                    <Chip
                      label={`To: ${format(endDate, "MMM dd, yyyy")}`}
                      size="small"
                      onDelete={() => setEndDate(null)}
                    />
                  )}
                  {selectedGymIds.length > 0 && (
                    <Chip
                      label={`${selectedGymIds.length} Gym(s)`}
                      size="small"
                      onDelete={() => setSelectedGymIds([])}
                    />
                  )}
                </Stack>
              </Box>
            )}
          </CardContent>
        </Card>

        {/* Error Display */}
        {leaderboardError && (
          <Alert severity="error" sx={{ mb: 3 }}>
            Failed to load leaderboard data: {leaderboardError.message}
          </Alert>
        )}

        {/* Loading State */}
        {isLoading && (
          <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
            <CircularProgress />
          </Box>
        )}

        {/* Charts */}
        {!isLoading && leaderboardData && (
          <Stack spacing={3}>
            {/* Overall Model Performance - First Chart */}
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Model Performance
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Overall fail percentage for each model with applied filters
                </Typography>
                {modelChartData.length > 0 ? (
                  <ReactECharts
                    option={{
                      tooltip: {
                        trigger: "axis",
                        axisPointer: {
                          type: "shadow",
                        },
                        formatter: (params: any) => {
                          const param = Array.isArray(params) ? params[0] : params;
                          return `${param.name}<br/>${param.seriesName}: ${param.value.toFixed(2)}%`;
                        },
                      },
                      grid: {
                        left: 140,
                        right: 80,
                        bottom: 60,
                        top: 40,
                        containLabel: false,
                      },
                      xAxis: {
                        type: "value",
                        name: "Agent Failing Percentage",
                        nameLocation: "middle",
                        nameGap: 30,
                        min: 0,
                        max: 100,
                        axisLabel: {
                          formatter: "{value}%",
                        },
                        splitLine: {
                          show: false,
                        },
                      },
                      yAxis: {
                        type: "category",
                        data: modelChartData.map((d) => d.model),
                        axisLabel: {
                          interval: 0,
                          width: 120,
                          overflow: "truncate",
                        },
                        splitLine: {
                          show: false,
                        },
                      },
                      series: [
                        {
                          name: "Agent Failing Percentage",
                          type: "bar",
                          data: modelChartData.map((entry) => ({
                            value: entry["Agent Failing Percentage"],
                            itemStyle: {
                              color: getModelColor((entry as any).originalModel || ""),
                              borderRadius: [0, 8, 8, 0],
                            },
                          })),
                          barWidth: "60%",
                          label: {
                            show: false,
                          },
                          emphasis: {
                            itemStyle: {
                              shadowBlur: 10,
                              shadowOffsetX: 0,
                              shadowColor: "rgba(0, 0, 0, 0.5)",
                            },
                          },
                        },
                      ],
                    }}
                    style={{ height: Math.max(300, modelChartData.length * 100), width: "100%" }}
                    opts={{ renderer: "svg" }}
                  />
                ) : (
                  <Alert severity="info">No model data available for the selected filters</Alert>
                )}
              </CardContent>
            </Card>

            {/* Model Performance By Environment (Gym) - Second Chart - Vertical Bars */}
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Model Performance By Environment
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Fail percentage for each model across different environments (gyms)
                </Typography>
                {modelGymChartData.length > 0 ? (
                  <ReactECharts
                    option={{
                      tooltip: {
                        trigger: "axis",
                        axisPointer: {
                          type: "shadow",
                        },
                        formatter: (params: any) => {
                          if (Array.isArray(params)) {
                            let result = `${params[0].axisValue}<br/>`;
                            params.forEach((param) => {
                              result += `${param.marker}${param.seriesName}: ${param.value.toFixed(2)}%<br/>`;
                            });
                            return result;
                          }
                          return `${params.name}<br/>${params.seriesName}: ${params.value.toFixed(2)}%`;
                        },
                      },
                      legend: {
                        data: Array.from(
                          new Set(leaderboardData.model_gym_stats.map((s) => s.model))
                        )
                          .sort()
                          .map((model) => getModelDisplayName(model)),
                        top: "5%",
                        textStyle: {
                          color: "#6e7079",
                          fontSize: 14,
                          fontWeight: "500",
                        },
                      },
                      grid: {
                        left: "10%",
                        right: "10%",
                        bottom: "15%",
                        top: "15%",
                        containLabel: true,
                      },
                      xAxis: {
                        type: "category",
                        data: modelGymChartData.map((d) => d.environment),
                        axisLabel: {
                          rotate: -45,
                          interval: 0,
                        },
                        splitLine: {
                          show: false,
                        },
                      },
                      yAxis: {
                        type: "value",
                        name: "Agent Failing Percentage",
                        nameLocation: "middle",
                        nameGap: 50,
                        min: 0,
                        max: 100,
                        axisLabel: {
                          formatter: "{value}%",
                        },
                        splitLine: {
                          show: false,
                        },
                      },
                      series: Array.from(
                        new Set(leaderboardData.model_gym_stats.map((s) => s.model))
                      )
                        .sort()
                        .map((model) => {
                          const displayName = getModelDisplayName(model);
                          const modelColor = getModelColor(model);
                          return {
                            name: displayName,
                            type: "bar",
                            itemStyle: {
                              color: modelColor,
                            },
                            data: modelGymChartData.map((entry) => {
                              const value = (entry as any)[displayName] || 0;
                              return {
                                value,
                                itemStyle: {
                                  color: modelColor,
                                  borderRadius: [4, 4, 0, 0],
                                },
                              };
                            }),
                            emphasis: {
                              itemStyle: {
                                shadowBlur: 10,
                                shadowOffsetY: 0,
                                shadowColor: "rgba(0, 0, 0, 0.5)",
                              },
                            },
                          };
                        }),
                    }}
                    style={{ height: Math.max(400, modelGymChartData.length * 80), width: "100%" }}
                    opts={{ renderer: "svg" }}
                  />
                ) : (
                  <Alert severity="info">No model-gym data available for the selected filters</Alert>
                )}
              </CardContent>
            </Card>
          </Stack>
        )}

        {/* Empty State */}
        {!isLoading && !leaderboardData && !leaderboardError && (
          <Alert severity="info">No data available. Try adjusting your filters.</Alert>
        )}
      </Box>
    </LocalizationProvider>
  );
}

