import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./contexts/AuthContext";
import { DownloadQueueProvider } from "./contexts/DownloadQueueContext";
import AuthRedirectHandler from "./components/AuthRedirectHandler";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import RoleBasedRedirect from "./components/RoleBasedRedirect";
import Login from "./pages/Login";
import Admin from "./pages/Admin";
import Gyms from "./pages/Gyms";
import Tasks from "./pages/Tasks";
import GymTasks from "./pages/GymTasks";
import Models from "./pages/Models";
import Runs from "./pages/Runs";
import Run from "./pages/Run";
import Batches from "./pages/Batches";
import BatchRuns from "./pages/BatchRuns";
import BatchReportPreview from "./pages/BatchReportPreview";
import ExecutionMonitor from "./pages/ExecutionMonitor";
import IterationDetail from "./pages/IterationDetail";
import TokenMonitoring from "./pages/TokenMonitoring";
import Leaderboard from "./pages/Leaderboard";
import "./App.css";

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <DownloadQueueProvider>
          <BrowserRouter>
            <AuthRedirectHandler />
            <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Routes>
                      <Route path="/" element={<RoleBasedRedirect />} />
                      <Route
                        path="/gyms"
                        element={
                          <ProtectedRoute allowedRoles={["admin"]}>
                            <Gyms />
                          </ProtectedRoute>
                        }
                      />
                      <Route path="/tasks" element={<Tasks />} />
                      <Route path="/gyms/:gymId/tasks" element={<GymTasks />} />
                      <Route
                        path="/models"
                        element={
                          <ProtectedRoute allowedRoles={["admin"]}>
                            <Models />
                          </ProtectedRoute>
                        }
                      />
                      <Route
                        path="/runs"
                        element={
                          <ProtectedRoute allowedRoles={["admin"]}>
                            <Runs />
                          </ProtectedRoute>
                        }
                      />
                      <Route path="/batches" element={<Batches />} />
                      <Route path="/batches/:batchId/runs" element={<BatchRuns />} />
                      <Route path="/batches/:batchId/report-preview" element={<BatchReportPreview />} />
                      {/* Batch-aware execution and iteration routes */}
                      <Route path="/batches/:batchId/executions/:executionId/monitor" element={<ExecutionMonitor />} />
                      <Route path="/batches/:batchId/executions/:executionId/iterations/:iterationId" element={<IterationDetail />} />
                      <Route
                        path="/leaderboard"
                        element={
                          <ProtectedRoute allowedRoles={["admin"]}>
                            <Leaderboard />
                          </ProtectedRoute>
                        }
                      />
                      <Route
                        path="/run"
                        element={
                          <ProtectedRoute allowedRoles={["admin"]}>
                            <Run />
                          </ProtectedRoute>
                        }
                      />
                      <Route
                        path="/executions/:executionId/monitor"
                        element={<ExecutionMonitor />}
                      />
                      <Route
                        path="/executions/:executionId/iterations/:iterationId"
                        element={<IterationDetail />}
                      />
                      <Route
                        path="/admin"
                        element={
                          <ProtectedRoute requireAdmin>
                            <Admin />
                          </ProtectedRoute>
                        }
                      />
                      <Route path="/monitoring/tokens" element={<TokenMonitoring />} />
                      <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                  </Layout>
                </ProtectedRoute>
              }
            />
          </Routes>
        </BrowserRouter>
        </DownloadQueueProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
