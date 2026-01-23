import React, { useState, useEffect } from "react";
import {
  Box,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  CircularProgress,
  Alert,
  useTheme,
  alpha,
} from "@mui/material";
import {
  ExpandMore as ExpandMoreIcon,
  Block as BlockIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  AccessTime as TimeoutIcon,
  HelpOutline as UnknownIcon,
} from "@mui/icons-material";
import { batchApi } from "../services/api";

interface FailureDiagnosticsPanelProps {
  batchId: string;
  failedCount: number;
}

interface FailedIteration {
  iteration_number: number;
  iteration_id: string;
  execution_id: string;
  task_id: string;
  model: string;
  category: string;
  reason_text: string;
  completion_reason?: string;
  execution_time_seconds?: number;
  iteration_url: string;
}

interface CategoryGroup {
  count: number;
  category_label: string;
  iterations: FailedIteration[];
}

interface FailureDiagnostics {
  batch_id: string;
  batch_name: string;
  total_failed: number;
  by_category: Record<string, CategoryGroup>;
}

const getCategoryIcon = (category: string) => {
  switch (category) {
    case "model_blocked":
      return <BlockIcon />;
    case "verification_failed":
      return <ErrorIcon />;
    case "verification_error":
      return <WarningIcon />;
    case "timeout":
      return <TimeoutIcon />;
    case "crashed":
      return <ErrorIcon />;
    default:
      return <UnknownIcon />;
  }
};

const getCategoryColor = (category: string) => {
  switch (category) {
    case "model_blocked":
      return "#ff9800"; // Orange
    case "verification_failed":
      return "#f44336"; // Red
    case "verification_error":
      return "#fbc02d"; // Amber/Yellow - technical issue
    case "timeout":
      return "#ff5722"; // Deep orange
    case "crashed":
      return "#d32f2f"; // Dark red
    default:
      return "#9e9e9e"; // Grey
  }
};

export default function FailureDiagnosticsPanel({
  batchId,
}: FailureDiagnosticsPanelProps) {
  const theme = useTheme();
  const [diagnostics, setDiagnostics] = useState<FailureDiagnostics | null>(
    null
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedCategory, setExpandedCategory] = useState<string | false>(
    false
  );

  useEffect(() => {
    const fetchDiagnostics = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await batchApi.getFailureDiagnostics(batchId);
        setDiagnostics(data);
        
        // Auto-expand first category if there's only one
        const categories = Object.keys(data.by_category);
        if (categories.length === 1) {
          setExpandedCategory(categories[0]);
        }
      } catch (err) {
        console.error("Failed to fetch failure diagnostics:", err);
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load failure diagnostics"
        );
      } finally {
        setLoading(false);
      }
    };

    fetchDiagnostics();
  }, [batchId]);

  const handleCategoryChange =
    (category: string) => (_event: React.SyntheticEvent, isExpanded: boolean) => {
      setExpandedCategory(isExpanded ? category : false);
    };

  if (loading) {
    return (
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 2,
          p: 3,
          border: `1px solid ${theme.palette.divider}`,
          borderRadius: 2,
          bgcolor: alpha(theme.palette.error.main, 0.05),
        }}
      >
        <CircularProgress size={24} />
        <Typography variant="body2" color="text.secondary">
          Analyzing failures...
        </Typography>
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        {error}
      </Alert>
    );
  }

  if (!diagnostics || diagnostics.total_failed === 0) {
    return null;
  }

  return (
    <Box
      sx={{
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 2,
        bgcolor: alpha(theme.palette.error.main, 0.03),
        overflow: "hidden",
      }}
    >
      <Box
        sx={{
          p: 2,
          bgcolor: alpha(theme.palette.error.main, 0.08),
          borderBottom: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Typography variant="subtitle1" fontWeight={600}>
          Failure Diagnostics
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {diagnostics.total_failed} failed iteration
          {diagnostics.total_failed !== 1 ? "s" : ""} across{" "}
          {Object.keys(diagnostics.by_category).length} categor
          {Object.keys(diagnostics.by_category).length !== 1 ? "ies" : "y"}
        </Typography>
      </Box>

      <Box sx={{ p: 1 }}>
        {Object.entries(diagnostics.by_category).map(([category, group]) => (
          <Accordion
            key={category}
            expanded={expandedCategory === category}
            onChange={handleCategoryChange(category)}
            sx={{
              "&:before": { display: "none" },
              boxShadow: "none",
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: "8px !important",
              mb: 1,
              "&:last-child": { mb: 0 },
            }}
          >
            <AccordionSummary
              expandIcon={<ExpandMoreIcon />}
              sx={{
                bgcolor: alpha(getCategoryColor(category), 0.08),
                borderRadius: 1,
                "&:hover": {
                  bgcolor: alpha(getCategoryColor(category), 0.12),
                },
              }}
            >
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1.5,
                  width: "100%",
                }}
              >
                <Box
                  sx={{
                    color: getCategoryColor(category),
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  {getCategoryIcon(category)}
                </Box>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="body1" fontWeight={600}>
                    {group.category_label}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {group.count} iteration{group.count !== 1 ? "s" : ""}
                  </Typography>
                </Box>
                <Chip
                  label={group.count}
                  size="small"
                  sx={{
                    bgcolor: alpha(getCategoryColor(category), 0.15),
                    color: getCategoryColor(category),
                    fontWeight: 600,
                  }}
                />
              </Box>
            </AccordionSummary>

            <AccordionDetails sx={{ p: 2, pt: 1 }}>
              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {group.iterations.map((iteration) => (
                  <Box
                    key={iteration.iteration_id}
                    sx={{
                      p: 2,
                      border: `1px solid ${theme.palette.divider}`,
                      borderRadius: 1,
                      bgcolor: theme.palette.background.paper,
                      "&:hover": {
                        bgcolor: alpha(theme.palette.primary.main, 0.02),
                      },
                    }}
                  >
                    <Box
                      sx={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        mb: 1,
                      }}
                    >
                      <Box>
                        <Typography variant="body2" fontWeight={600}>
                          Iteration {iteration.iteration_number}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Task: {iteration.task_id} • Model: {iteration.model}
                        </Typography>
                      </Box>
                      {iteration.execution_time_seconds && (
                        <Chip
                          label={`${Math.round(iteration.execution_time_seconds / 60)}m`}
                          size="small"
                          variant="outlined"
                        />
                      )}
                    </Box>

                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        mb: 1.5,
                        fontStyle: "italic",
                      }}
                    >
                      {iteration.reason_text}
                    </Typography>

                    {iteration.completion_reason && (
                      <Accordion
                        sx={{
                          boxShadow: "none",
                          border: `1px solid ${theme.palette.divider}`,
                          borderRadius: "4px !important",
                          "&:before": { display: "none" },
                          mb: 1,
                        }}
                      >
                        <AccordionSummary
                          expandIcon={<ExpandMoreIcon sx={{ fontSize: 18 }} />}
                          sx={{ minHeight: 36, "& .MuiAccordionSummary-content": { my: 0.5 } }}
                        >
                          <Typography variant="caption" color="text.secondary">
                            View full model response
                          </Typography>
                        </AccordionSummary>
                        <AccordionDetails sx={{ pt: 0, pb: 1 }}>
                          <Typography
                            variant="caption"
                            sx={{
                              display: "block",
                              whiteSpace: "pre-wrap",
                              fontFamily: "monospace",
                              color: theme.palette.text.secondary,
                              bgcolor: alpha(theme.palette.common.black, 0.03),
                              p: 1,
                              borderRadius: 0.5,
                            }}
                          >
                            {iteration.completion_reason}
                          </Typography>
                        </AccordionDetails>
                      </Accordion>
                    )}
                  </Box>
                ))}
              </Box>
            </AccordionDetails>
          </Accordion>
        ))}
      </Box>
    </Box>
  );
}

