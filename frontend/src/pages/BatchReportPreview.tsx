import { useState, useEffect } from "react";
import {
  Box,
  Container,
  Typography,
  Alert,
  CircularProgress,
  Button,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  useTheme,
} from "@mui/material";
import {
  Download as DownloadIcon,
  ArrowBack as ArrowBackIcon,
} from "@mui/icons-material";
import { useParams, useNavigate } from "react-router-dom";
import { batchApi, executionApi } from "../services/api";
import { green, amber, red, grey } from "@mui/material/colors";

// Deterministic color scheme per label (no hardcoding of vendor names)
const colorSchemes = [
  { bg: "#7B1FA2", text: "#FFFFFF", section: "#F3E5F5" }, // purple
  { bg: "#1976D2", text: "#FFFFFF", section: "#E3F2FD" }, // blue
  { bg: "#5D4037", text: "#FFFFFF", section: "#EFEBE9" }, // brown
  { bg: "#00796B", text: "#FFFFFF", section: "#E0F2F1" }, // teal
  { bg: "#E64A19", text: "#FFFFFF", section: "#FBE9E7" }, // deep orange
  { bg: "#455A64", text: "#FFFFFF", section: "#ECEFF1" }, // blue grey
];
const hashString = (s: string) => {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
};
const modelHeaderStyles = (label: string) => {
  const idx = hashString(label) % colorSchemes.length;
  return colorSchemes[idx];
};

// Removed unused TabPanel/a11yProps helpers

// Helper: map difficulty label to Material Design colors (classic palette)
const difficultyColor = (diff?: string) => {
  const d = (diff || "").toLowerCase();
  if (d === "easy") return green[600];   // success
  if (d === "medium") return amber[700]; // warning
  if (d === "hard") return red[700];     // error
  return grey[600];                        // neutral
};

// Removed deriveDifficulty since summary Difficulty column was removed

export default function BatchReportPreview() {
  const { batchId } = useParams<{ batchId: string }>();
  const navigate = useNavigate();
  const theme = useTheme();
  const [reportData, setReportData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [isDownloading, setIsDownloading] = useState(false);

  // Generate tab list: Summary + Insights + each task
  const getTabs = () => {
    const tabs = ["Summary", "Insights"];
    if (reportData?.task_rows && Object.keys(reportData.task_rows).length > 0) {
      tabs.push(...Object.keys(reportData.task_rows));
    }
    return tabs;
  };

  useEffect(() => {
    const fetchReportData = async () => {
      if (!batchId) return;

      try {
        setLoading(true);
        setError(null);
        const data = await batchApi.getReportData(batchId);
        setReportData(data);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load report preview"
        );
        console.error("Error loading report preview:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchReportData();
  }, [batchId]);

  const handleDownloadReport = async () => {
    if (!batchId) return;

    setIsDownloading(true);
    setError(null);

    try {
      const report = await batchApi.generateReport(batchId);
      await executionApi.downloadExport(report.download_url);
    } catch (err) {
      setError("Failed to download report");
      console.error("Error downloading report:", err);
    } finally {
      setIsDownloading(false);
    }
  };

  if (loading) {
    return (
      <Container maxWidth="xl">
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight="400px"
        >
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="xl">
        <Box sx={{ py: 4 }}>
          <Alert severity="error">{error}</Alert>
          <Button
            variant="outlined"
            startIcon={<ArrowBackIcon />}
            onClick={() => navigate(-1)}
            sx={{ mt: 2 }}
          >
            Go Back
          </Button>
        </Box>
      </Container>
    );
  }

  if (!reportData) {
    return (
      <Container maxWidth="xl">
        <Box sx={{ py: 4 }}>
          <Alert severity="warning">No report data available</Alert>
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth={false} sx={{ py: 4 }}>
      <Box
        sx={{
          width: "100%",
          px: 3,
          display: "flex",
          flexDirection: "column",
          height: "100vh",
          boxSizing: "border-box",
        }}
      >
        {/* Header */}
        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="flex-start"
          mb={3}
        >
          <Box>
            <Typography variant="h4" component="h1" gutterBottom>
              Batch Report Preview: {reportData.batch_name}
            </Typography>
            <Typography variant="subtitle1" color="text.secondary">
              Executions: {reportData.executions_count} • Total Iterations:{" "}
              {reportData.total_iterations}
            </Typography>
          </Box>
          <Box display="flex" gap={2}>
            <Button
              variant="contained"
              startIcon={
                isDownloading ? (
                  <CircularProgress size={16} />
                ) : (
                  <DownloadIcon />
                )
              }
              onClick={handleDownloadReport}
              disabled={isDownloading}
              title="Download batch report as Excel file"
            >
              {isDownloading ? "Downloading..." : "Download Report"}
            </Button>
          </Box>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* Tabs - Vertical Layout */}
        <Box
          sx={{
            display: "flex",
            gap: 0,
            mb: 3,
            flex: 1,
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          {/* Vertical Tabs */}
          <Paper
            sx={{
              display: "flex",
              flexDirection: "column",
              width: 350,
              backgroundColor: theme.palette.mode === "light" ? "#F8F8F7" : "#161616",
              borderRight: `1px solid ${theme.palette.divider}`,
              height: "100%",
              overflow: "hidden",
              borderRadius: 0,
            }}
          >
            {getTabs().map((tabLabel, index) => (
              <Box
                key={index}
                onClick={() => setActiveTab(index)}
                sx={{
                  padding: "12px 16px",
                  cursor: "pointer",
                  backgroundColor:
                    activeTab === index
                      ? theme.palette.background.paper
                      : theme.palette.mode === "light"
                        ? "#F8F8F7"
                        : "#161616",
                  borderLeft:
                    activeTab === index
                      ? `4px solid ${theme.palette.primary.main}`
                      : "4px solid transparent",
                  borderBottom: `1px solid ${theme.palette.divider}`,
                  fontWeight: activeTab === index ? "bold" : "normal",
                  color:
                    activeTab === index
                      ? theme.palette.primary.main
                      : theme.palette.text.primary,
                  transition: "all 0.2s ease",
                  "&:hover": {
                    backgroundColor: theme.palette.background.paper,
                  },
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {tabLabel}
              </Box>
            ))}
          </Paper>

          {/* Tab Content */}
          <Box sx={{ flex: 1, pl: 3, overflowY: "auto", minHeight: 0 }}>
            {activeTab === 0 && (
              <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
                {reportData.summary_rows && reportData.summary_rows.length > 0 ? (
                  <>
                    {/* Summary Table */}
                    <Box>
                      <Typography variant="h6" sx={{ fontWeight: "bold", mb: 2 }}>
                        Task Summary
                      </Typography>
                      <TableContainer sx={{ border: `1px solid ${theme.palette.divider}` }}>
                        <Table sx={{ borderCollapse: "collapse" }}>
                          <TableHead>
                            <TableRow
                              sx={{
                                backgroundColor:
                                  theme.palette.mode === "light"
                                    ? theme.palette.primary.main
                                    : "#0c4a6e",
                              }}
                            >
                              <TableCell
                                sx={{
                                  fontWeight: "bold",
                                  color: "white",
                                  border: `1px solid ${theme.palette.divider}`,
                                  padding: "12px",
                                }}
                              >
                                Prompt ID
                              </TableCell>
                              
                              <TableCell
                                sx={{
                                  fontWeight: "bold",
                                  color: "white",
                                  border: `1px solid ${theme.palette.divider}`,
                                  padding: "12px",
                                }}
                              >
                                Prompt
                              </TableCell>
                              <TableCell
                                sx={{
                                  fontWeight: "bold",
                                  color: "white",
                                  border: `1px solid ${theme.palette.divider}`,
                                  padding: "12px",
                                }}
                              >
                                {/* Removed Difficulty and Avg Iteration columns */}
                              </TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {reportData.summary_rows.map((row: any, index: number) => (
                              <TableRow
                                key={index}
                                sx={{
                                  borderBottom: `1px solid ${theme.palette.divider}`,
                                  "&:last-child": { borderBottom: "none" },
                                }}
                              >
                                <TableCell
                                  sx={{
                                    border: `1px solid ${theme.palette.divider}`,
                                    padding: "12px",
                                    color: theme.palette.text.primary,
                                    fontWeight: "bold",
                                  }}
                                >
                                  {row["Prompt ID"] || "N/A"}
                                </TableCell>
                                <TableCell
                                  sx={{
                                    border: `1px solid ${theme.palette.divider}`,
                                    padding: "12px",
                                    color: theme.palette.text.primary,
                                    maxWidth: "500px",
                                    wordBreak: "break-word",
                                    whiteSpace: "normal",
                                  }}
                                >
                                  {row.Prompt || "N/A"}
                                </TableCell>
                                {/* Removed Difficulty and Avg Iteration cells */}
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Box>

                    {/* Model Breaking Section */}
                    <Box>
                      <Typography variant="h6" sx={{ fontWeight: "bold", mb: 2 }}>
                        Model Performance
                      </Typography>
                      <TableContainer sx={{ border: `1px solid ${theme.palette.divider}` }}>
                        <Table sx={{ borderCollapse: "collapse" }}>
                          <TableHead>
                            <TableRow
                              sx={{
                                backgroundColor:
                                  theme.palette.mode === "light"
                                    ? theme.palette.primary.main
                                    : "#0c4a6e",
                              }}
                            >
                              <TableCell
                                sx={{
                                  fontWeight: "bold",
                                  color: "white",
                                  border: `1px solid ${theme.palette.divider}`,
                                  padding: "12px",
                                }}
                              >
                                Task
                              </TableCell>
                              {/* Dynamically render model columns */}
                              {reportData.summary_rows.length > 0 &&
                                Object.keys(reportData.summary_rows[0])
                                  .filter((key) => key.includes("Breaking"))
                                  .map((modelKey) => (
                                    <TableCell
                                      key={modelKey}
                                      sx={{
                                        fontWeight: "bold",
                                        color: "white",
                                        border: `1px solid ${theme.palette.divider}`,
                                        padding: "12px",
                                      }}
                                    >
                                      {modelKey.replace(" Breaking", "")}
                                    </TableCell>
                                  ))}
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {reportData.summary_rows.map((row: any, index: number) => (
                              <TableRow
                                key={index}
                                sx={{
                                  borderBottom: `1px solid ${theme.palette.divider}`,
                                  "&:last-child": { borderBottom: "none" },
                                }}
                              >
                                <TableCell
                                  sx={{
                                    border: `1px solid ${theme.palette.divider}`,
                                    padding: "12px",
                                    color: theme.palette.text.primary,
                                    fontWeight: "bold",
                                  }}
                                >
                                  {row.Task || "N/A"}
                                </TableCell>
                                {Object.keys(row)
                                  .filter((key) => key.includes("Breaking"))
                                  .map((modelKey) => (
                                    <TableCell
                                      key={modelKey}
                                      sx={{
                                        border: `1px solid ${theme.palette.divider}`,
                                        padding: "12px",
                                        textAlign: "center",
                                        color: "white",
                                        backgroundColor: (() => {
                                          const modelLabel = modelKey.replace(" Breaking", "");
                                          const modelDiff = (row[`${modelLabel} Difficulty`] || "unknown").toString();
                                          return difficultyColor(modelDiff);
                                        })(),
                                        fontWeight: "bold",
                                      }}
                                    >
                                      {row[modelKey] || "N/A"}
                                    </TableCell>
                                  ))}
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Box>

                    {/* Difficulty Legend */}
                    <Box>
                      <Typography variant="h6" sx={{ fontWeight: "bold", mb: 2 }}>
                        Difficulty Definitions
                      </Typography>
                      <TableContainer sx={{ border: `1px solid ${theme.palette.divider}` }}>
                        <Table sx={{ borderCollapse: "collapse" }}>
                          <TableHead>
                            <TableRow
                              sx={{
                                backgroundColor:
                                  theme.palette.mode === "light"
                                    ? theme.palette.primary.main
                                    : "#0c4a6e",
                              }}
                            >
                              <TableCell
                                sx={{
                                  fontWeight: "bold",
                                  color: "white",
                                  border: `1px solid ${theme.palette.divider}`,
                                  padding: "12px",
                                  width: "20%",
                                }}
                              >
                                Difficulty
                              </TableCell>
                              <TableCell
                                sx={{
                                  fontWeight: "bold",
                                  color: "white",
                                  border: `1px solid ${theme.palette.divider}`,
                                  padding: "12px",
                                  width: "40%",
                                }}
                              >
                                Criteria
                              </TableCell>
                              <TableCell
                                sx={{
                                  fontWeight: "bold",
                                  color: "white",
                                  border: `1px solid ${theme.palette.divider}`,
                                  padding: "12px",
                                  width: "40%",
                                }}
                              >
                                Description
                              </TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {[
                              {
                                difficulty: "Easy",
                                criteria: "Pass@3 = 100%",
                                description: "Prompt should fail 0 times\nPrompt should pass 3 times",
                                color: "#4caf50",
                              },
                              {
                                difficulty: "Medium",
                                criteria: "40% < Pass@3 < 100%",
                                description: "Prompt should fail between 1 - 1 out of 3 times\nPrompt should pass between 2 - 2 out of 3 times",
                                color: "#ff9800",
                              },
                              {
                                difficulty: "Hard",
                                criteria: "Pass@3 < 40%",
                                description: "Prompt should fail between 2-3 out of 3 times\nPrompt should pass between 0-1 out of 3 times",
                                color: "#f44336",
                              },
                            ].map((item, index) => (
                              <TableRow
                                key={index}
                                sx={{
                                  borderBottom: `1px solid ${theme.palette.divider}`,
                                  "&:last-child": { borderBottom: "none" },
                                }}
                              >
                                <TableCell
                                  sx={{
                                    border: `1px solid ${theme.palette.divider}`,
                                    padding: "12px",
                                    backgroundColor: item.color,
                                    color: "white",
                                    fontWeight: "bold",
                                    textAlign: "center",
                                  }}
                                >
                                  {item.difficulty}
                                </TableCell>
                                <TableCell
                                  sx={{
                                    border: `1px solid ${theme.palette.divider}`,
                                    padding: "12px",
                                    color: theme.palette.text.primary,
                                    whiteSpace: "pre-line",
                                  }}
                                >
                                  {item.criteria}
                                </TableCell>
                                <TableCell
                                  sx={{
                                    border: `1px solid ${theme.palette.divider}`,
                                    padding: "12px",
                                    color: theme.palette.text.primary,
                                    whiteSpace: "pre-line",
                                  }}
                                >
                                  {item.description}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Box>
                  </>
                ) : (
                  <Typography color="text.secondary">
                    No summary data available
                  </Typography>
                )}
              </Box>
            )}

            {/* Insights Tab */}
            {activeTab === 1 && (
              <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: "bold", mb: 2 }}>
                  Model Insights
                </Typography>
                
                {reportData?.batch_insights && Object.keys(reportData.batch_insights).length > 0 ? (
                  <TableContainer sx={{ border: `1px solid ${theme.palette.divider}` }}>
                    <Table sx={{ borderCollapse: "collapse" }}>
                      <TableHead>
                        <TableRow
                          sx={{
                            backgroundColor:
                              theme.palette.mode === "light"
                                ? theme.palette.primary.main
                                : "#0c4a6e",
                          }}
                        >
                          <TableCell
                            sx={{
                              fontWeight: "bold",
                              color: "white",
                              border: `1px solid ${theme.palette.divider}`,
                              padding: "12px",
                            }}
                          >
                            Task Identifier
                          </TableCell>
                          {Object.keys(reportData.batch_insights).map((model) => (
                            <TableCell
                              key={model}
                              sx={{
                                fontWeight: "bold",
                                color: "white",
                                border: `1px solid ${theme.palette.divider}`,
                                padding: "12px",
                                textAlign: "center",
                              }}
                            >
                              {model === "openai" ? "OpenAI Computer Use Preview" :
                               model === "anthropic" ? "Claude Sonnet 4" :
                               model === "gemini" ? "Google Gemini Computer Use" :
                               model}
                            </TableCell>
                          ))}
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {/* Overview row with batch-level insights */}
                        <TableRow>
                          <TableCell
                            sx={{
                              fontWeight: "bold",
                              border: `1px solid ${theme.palette.divider}`,
                              padding: "12px",
                            }}
                          >
                            Overview
                          </TableCell>
                          {Object.entries(reportData.batch_insights).map(([model, insights]) => (
                            <TableCell
                              key={model}
                              sx={{
                                border: `1px solid ${theme.palette.divider}`,
                                padding: "12px",
                                maxWidth: 400,
                                whiteSpace: "normal",
                                wordBreak: "break-word",
                                verticalAlign: "top",
                              }}
                            >
                              {String(insights) || "No batch insights available"}
                            </TableCell>
                          ))}
                        </TableRow>
                        
                        {/* Execution-level insights for each task */}
                        {reportData?.task_rows && Object.keys(reportData.task_rows).map((taskId) => {
                          const taskData = reportData.task_rows[taskId];
                          return (
                            <TableRow key={taskId}>
                              <TableCell
                                sx={{
                                  fontWeight: "bold",
                                  border: `1px solid ${theme.palette.divider}`,
                                  padding: "12px",
                                }}
                              >
                                {taskId}
                              </TableCell>
                              {Object.keys(reportData.batch_insights).map((model) => {
                                const modelData = taskData?.[model];
                                const insights = modelData?.[0]?.eval_insights;
                                return (
                                  <TableCell
                                    key={model}
                                    sx={{
                                      border: `1px solid ${theme.palette.divider}`,
                                      padding: "12px",
                                      maxWidth: 400,
                                      whiteSpace: "normal",
                                      wordBreak: "break-word",
                                      verticalAlign: "top",
                                    }}
                                  >
                                    {String(insights) || "No insights available"}
                                  </TableCell>
                                );
                              })}
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Typography color="text.secondary">
                    No insights data available
                  </Typography>
                )}
              </Box>
            )}

            {/* Dynamic Task Tabs */}
            {getTabs().map((tabLabel, tabIndex) => {
              if (tabIndex === 0 || tabIndex === 1) return null; // Skip Summary and Insights, already handled above

              const taskId = tabLabel;
              const taskData = reportData?.task_rows?.[taskId];
              // Find the summary row for this task to mirror sheet top block
              const summaryRow = (reportData?.summary_rows || []).find((r: any) => r["Prompt ID"] === taskId);

              return activeTab === tabIndex ? (
                <Box key={tabIndex} sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  {taskData ? (
                    <>
                      {/* Task Header */}
                      <Box sx={{ mb: 3 }}>
                        <Typography variant="h5" sx={{ fontWeight: "bold" }}>
                          {taskId}
                        </Typography>
                      </Box>

                      {/* Compact Task Summary (matches Summary sheet columns) */}
                      {summaryRow && (
                        <Box sx={{ mb: 2 }}>
                          <Typography variant="subtitle1" sx={{ fontWeight: "bold", mb: 1 }}>
                            Task Summary
                          </Typography>
                          <TableContainer sx={{ border: `1px solid ${theme.palette.divider}` }}>
                            <Table size="small" sx={{ borderCollapse: "collapse" }}>
                              <TableHead>
                                <TableRow sx={{ backgroundColor: theme.palette.mode === "light" ? theme.palette.primary.main : "#0c4a6e" }}>
                                  <TableCell sx={{ fontWeight: "bold", color: "white", border: `1px solid ${theme.palette.divider}`, padding: "8px" }}>Prompt ID</TableCell>
                                  <TableCell sx={{ fontWeight: "bold", color: "white", border: `1px solid ${theme.palette.divider}`, padding: "8px" }}>Prompt</TableCell>
                                {/* Removed Difficulty and Avg Iteration columns */}
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                <TableRow>
                                  <TableCell sx={{ border: `1px solid ${theme.palette.divider}`, padding: "8px", fontWeight: "bold" }}>{summaryRow["Prompt ID"]}</TableCell>
                                  <TableCell sx={{ border: `1px solid ${theme.palette.divider}`, padding: "8px", maxWidth: 600, whiteSpace: "normal", wordBreak: "break-word" }}>{summaryRow["Prompt"]}</TableCell>
                                {/* Removed Difficulty and Avg Iteration cells */}
                                </TableRow>
                              </TableBody>
                            </Table>
                          </TableContainer>
                        </Box>
                      )}

                      {/* Per-Model sections (frontend-only, dynamic, no backend changes) */}
                      {summaryRow && (
                        (() => {
                          // 1) Model labels from summary (for display only)
                          const modelLabels: string[] = Object.keys(summaryRow)
                            .filter((k) => k.endsWith(" Breaking"))
                            .map((k) => k.replace(" Breaking", ""));

                          // 2) Group task iterations by runner
                          const groups: Record<string, any[]> = {};
                          (reportData.iteration_records || [])
                            .filter((rec: any) => rec.task_id === taskId)
                            .forEach((rec: any) => {
                              const key = String(rec.runner || "unknown");
                              if (!groups[key]) groups[key] = [];
                              groups[key].push(rec);
                            });

                          const normalize = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
                          const score = (a: string, b: string) => {
                            const at = new Set(normalize(a).split(" ").filter(Boolean));
                            const bt = new Set(normalize(b).split(" ").filter(Boolean));
                            let c = 0; at.forEach((t) => { if (bt.has(t)) c++; });
                            return c;
                          };

                          // 3) Render a section per runner group; pick best display label from modelLabels
                          return Object.entries(groups).map(([runner, records]) => {
                            let displayLabel = runner;
                            let best = -1;
                            for (const label of modelLabels) {
                              const sc = score(label, runner);
                              if (sc > best) { best = sc; displayLabel = label; }
                            }

                            // Compute per-runner difficulty from records (sheet-like: success rate thresholds)
                            const total = records.length;
                            const passCount = records.filter((r: any) => String(r.status || "").toLowerCase().startsWith("pass")).length;
                            const successRate = total ? (passCount / total) * 100 : 0;
                            const runnerDifficulty = successRate >= 100 ? "easy" : successRate >= 40 ? "medium" : "hard";
                            const header = modelHeaderStyles(displayLabel);

                            return (
                              <Box key={runner} sx={{ border: `1px solid ${theme.palette.divider}`, borderRadius: 1, overflow: "hidden", mb: 2, backgroundColor: theme.palette.background.paper }}>
                                <Box sx={{ backgroundColor: header.bg, color: header.text, px: 2, py: 1, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                  <Typography sx={{ fontWeight: "bold" }}>{displayLabel}</Typography>
                                  <Typography sx={{ fontWeight: "bold" }}>{String(runnerDifficulty).toUpperCase()}</Typography>
                                </Box>
                                <TableContainer>
                                  <Table size="small" sx={{ borderCollapse: "collapse" }}>
                                    <TableHead>
                                      <TableRow>
                                        <TableCell sx={{ fontWeight: "bold", border: `1px solid ${theme.palette.divider}`, padding: "8px" }}>Model Response</TableCell>
                                        <TableCell sx={{ fontWeight: "bold", border: `1px solid ${theme.palette.divider}`, padding: "8px" }}>Pass/Fail</TableCell>
                                        <TableCell sx={{ fontWeight: "bold", border: `1px solid ${theme.palette.divider}`, padding: "8px" }}>Time Taken</TableCell>
                                        <TableCell sx={{ fontWeight: "bold", border: `1px solid ${theme.palette.divider}`, padding: "8px" }}>Iteration Link</TableCell>
                                        <TableCell sx={{ fontWeight: "bold", border: `1px solid ${theme.palette.divider}`, padding: "8px" }}>Comments</TableCell>
                                        <TableCell sx={{ fontWeight: "bold", border: `1px solid ${theme.palette.divider}`, padding: "8px" }}>Insights</TableCell>
                                      </TableRow>
                                    </TableHead>
                                    <TableBody>
                                      {records.map((record: any, i: number) => {
                                        const pass = String(record.status || "").toLowerCase().startsWith("pass");
                                        const minutes = record.duration_seconds != null ? `${(record.duration_seconds / 60).toFixed(1)}m` : "-";
                                        const linkText = record.iteration_uuid ? `View iteration ${String(record.iteration_uuid || "").slice(0, 7)}` : "-";
                                        return (
                                          <TableRow key={i}>
                                            <TableCell sx={{ border: `1px solid ${theme.palette.divider}`, padding: "8px", whiteSpace: "pre-wrap" }}>{record.completion_reason || "-"}</TableCell>
                                            <TableCell sx={{ border: `1px solid ${theme.palette.divider}`, padding: "8px" }}>
                                              <Box component="span" sx={{ px: 1.2, py: 0.3, borderRadius: 999, fontWeight: 700, color: pass ? theme.palette.success.contrastText : theme.palette.error.contrastText, backgroundColor: pass ? theme.palette.success.main : theme.palette.error.main }}>{pass ? "PASSED" : "FAILED"}</Box>
                                            </TableCell>
                                            <TableCell sx={{ border: `1px solid ${theme.palette.divider}`, padding: "8px" }}>{minutes}</TableCell>
                                            <TableCell sx={{ border: `1px solid ${theme.palette.divider}`, padding: "8px" }}>
                                              {record.iteration_url ? (<a href={record.iteration_url} target="_blank" rel="noreferrer">{linkText}</a>) : "-"}
                                            </TableCell>
                                            <TableCell sx={{ border: `1px solid ${theme.palette.divider}`, padding: "8px", whiteSpace: "pre-wrap" }}>{record.verification_comments || ""}</TableCell>
                                            <TableCell sx={{ border: `1px solid ${theme.palette.divider}`, padding: "8px", whiteSpace: "pre-wrap", maxWidth: 300, wordBreak: "break-word" }}>{String(record.eval_insights) || "-"}</TableCell>
                                          </TableRow>
                                        );
                                      })}
                                    </TableBody>
                                  </Table>
                                </TableContainer>
                              </Box>
                            );
                          });
                        })()
                      )}

                      {/* Removed extra bottom Iterations table to avoid duplication; model sections above cover details */}
                    </>
                  ) : (
                    <Typography color="text.secondary">No data available</Typography>
                  )}
                </Box>
              ) : null;
            })}
          </Box>
        </Box>
      </Box>
    </Container>
  );
}
