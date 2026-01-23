import { useMemo, useState, useEffect } from "react";
import {
  Alert,
  Box,
  Pagination,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from "@mui/material";
import { LocalizationProvider, DatePicker } from "@mui/x-date-pickers";
import { AdapterDateFns } from "@mui/x-date-pickers/AdapterDateFns";
import {
  Assessment as AssessmentIcon,
  Download as DownloadIcon,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import DataTable, { type TableColumn } from "../components/DataTable";
import { useGyms } from "../hooks/useGyms";
import { executionApi } from "../services/api";
import type { TaskDetailPayload } from "../types";

type ReportSummaryRow = {
  id: string;
  prompt: string;
  difficulty: string | null;
  claude_sonnet_4_breaking: string | null;
  openai_computer_use_preview_breaking: string | null;
  source_total_time_seconds: number | null;
  source_total_time_formatted: string | null;
  wall_clock_seconds: number | null;
  wall_clock_formatted: string | null;
  average_iteration_minutes: number | null;
  iterations_total: number | null;
  passes_total: number | null;
  fails_total: number | null;
  task_start_time: string | null;
  task_end_time: string | null;
  gym_id?: string;
  task_id?: string;
};

const formatDuration = (seconds: number): string => {
  if (!Number.isFinite(seconds)) return "";
  const totalSeconds = Math.max(0, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600)
    .toString()
    .padStart(2, "0");
  const minutes = Math.floor((totalSeconds % 3600) / 60)
    .toString()
    .padStart(2, "0");
  const secs = Math.floor(totalSeconds % 60)
    .toString()
    .padStart(2, "0");
  return `${hours}:${minutes}:${secs}`;
};

const formatDateParam = (date: Date | null): string | undefined => {
  if (!date) return undefined;
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

export default function Reports() {
  const navigate = useNavigate();
  const [fromDate, setFromDate] = useState<Date | null>(null);
  const [toDate, setToDate] = useState<Date | null>(null);
  const { data: gyms } = useGyms();
  const [selectedGym, setSelectedGym] = useState<string>("");
  const [page, setPage] = useState(1);
  const rowsPerPage = 20;

  const [rows, setRows] = useState<ReportSummaryRow[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  // Default to first gym if nothing selected
  useEffect(() => {
    if (!selectedGym && gyms && gyms.length > 0) {
      setSelectedGym(gyms[0].uuid);
    }
  }, [gyms, selectedGym]);

  // Fetch real data when filters change
  useEffect(() => {
    const fetchSummary = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const res = await executionApi.getAllTasksSummary({
          gym_id: selectedGym || undefined,
          start_date: formatDateParam(fromDate),
          end_date: formatDateParam(toDate),
          include_task_details: true,
        });
        const fallbackGymId = selectedGym || gyms?.[0]?.uuid || "";
        const rows = (res.summary || []).map((entry, idx) => {
          const taskKey = entry.task || String(idx + 1);
          const taskTotals: TaskDetailPayload["totals"] | undefined = entry.task
            ? res.tasks?.[entry.task]?.totals
            : undefined;

          const wallClock = entry.wall_clock_formatted
            || (entry.wall_clock_seconds != null
              ? formatDuration(entry.wall_clock_seconds)
              : null);
          const sourceDuration = entry.source_total_time_formatted
            || (entry.source_total_time_seconds != null
              ? formatDuration(entry.source_total_time_seconds)
              : null);

          return {
            id: taskKey,
            prompt: entry.prompt || "",
            difficulty: entry.difficulty || null,
            claude_sonnet_4_breaking:
              entry.claude_sonnet_4_breaking ?? "No data",
            openai_computer_use_preview_breaking:
              entry.openai_computer_use_preview_breaking ?? "No data",
            source_total_time_seconds:
              entry.source_total_time_seconds ?? null,
            source_total_time_formatted: sourceDuration,
            wall_clock_seconds: entry.wall_clock_seconds ?? null,
            wall_clock_formatted: wallClock,
            average_iteration_minutes:
              entry.average_iteration_minutes ?? null,
            iterations_total: taskTotals?.iterations ?? null,
            passes_total: taskTotals?.passes ?? null,
            fails_total: taskTotals?.fails ?? null,
            task_start_time: entry.task_start_time ?? null,
            task_end_time: entry.task_end_time ?? null,
            gym_id: fallbackGymId,
            task_id: entry.task || taskKey,
          };
        });
        setRows(rows);
      } catch (e: unknown) {
        const message =
          typeof e === "object" && e && "message" in e
            ? String((e as { message?: unknown }).message || "")
            : String(e ?? "");
        setError(message || "Failed to load reports");
        setRows([]);
      } finally {
        setIsLoading(false);
      }
    };

    if (gyms && gyms.length > 0) {
      fetchSummary();
    }
  }, [selectedGym, fromDate, toDate, gyms]);

  const filteredItems = useMemo(() => {
    let items = rows;
    if (selectedGym) {
      items = items.filter((r) => r.gym_id === selectedGym);
    }
    return items;
  }, [rows, selectedGym]);

  const paged = useMemo(() => {
    const start = (page - 1) * rowsPerPage;
    return filteredItems.slice(start, start + rowsPerPage);
  }, [filteredItems, page]);

  const columns: TableColumn<ReportSummaryRow>[] = [
    {
      id: "prompt",
      label: "Prompt",
      minWidth: 320,
      render: (value) =>
        String(value || "").length > 120
          ? `${String(value).slice(0, 120)}...`
          : String(value || ""),
    },
    {
      id: "claude_sonnet_4_breaking",
      label: "Claude Breaking",
      minWidth: 160,
    },
    {
      id: "openai_computer_use_preview_breaking",
      label: "OpenAI Preview Breaking",
      minWidth: 200,
    },
  ];

  return (
    <Box>
      <PageHeader
        icon={<AssessmentIcon sx={{ fontSize: 48 }} />}
        title="Reports"
        description="Analyze execution metrics and export reports"
        searchPlaceholder=""
        searchValue={""}
        onSearchChange={() => {}}
        primaryButton={{
          label: "Refresh",
          icon: <AssessmentIcon />,
          onClick: () => {},
        }}
        secondaryButton={{
          label: isExporting ? "Preparing report..." : "Download Report",
          icon: <DownloadIcon />,
          onClick: async () => {
            try {
              setIsExporting(true);
              await executionApi.downloadAllTasksSummaryReport({
                gym_id: selectedGym || undefined,
                start_date: formatDateParam(fromDate),
                end_date: formatDateParam(toDate),
                include_snapshot: false,
              });
            } catch (e) {
              console.error(e);
            } finally {
              setIsExporting(false);
            }
          },
          disabled: isExporting,
        }}
        customLeftControls={
          <LocalizationProvider dateAdapter={AdapterDateFns}>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <FormControl size="small" sx={{ minWidth: 220 }}>
                <InputLabel id="gym-filter-label">Gym</InputLabel>
                <Select
                  labelId="gym-filter-label"
                  label="Gym"
                  value={selectedGym}
                  onChange={(e) => {
                    setSelectedGym(String(e.target.value));
                    setPage(1);
                  }}
                >
                  {gyms?.map((g) => (
                    <MenuItem key={g.uuid} value={g.uuid}>
                      {g.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <DatePicker
                label="From"
                value={fromDate}
                onChange={(val) => {
                  setFromDate(val);
                  setPage(1);
                }}
                slotProps={{ textField: { size: "small" } }}
              />
              <DatePicker
                label="To"
                value={toDate}
                onChange={(val) => {
                  setToDate(val);
                  setPage(1);
                }}
                slotProps={{ textField: { size: "small" } }}
              />
            </Box>
          </LocalizationProvider>
        }
      />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <DataTable
        data={paged}
        columns={columns as unknown as TableColumn<Record<string, unknown>>[]}
        isLoading={isLoading}
        onRowClick={(row) => {
          const r = row as unknown as { task_id?: string } & ReportSummaryRow;
          const taskId =
            r.task_id || r.id?.replace?.("rep-", "") || "";
          if (taskId) {
            const params = new URLSearchParams();
            const gymForRow = r.gym_id || selectedGym;
            if (gymForRow) params.set("gymId", gymForRow);
            const startParam = formatDateParam(fromDate);
            const endParam = formatDateParam(toDate);
            if (startParam) params.set("start", startParam);
            if (endParam) params.set("end", endParam);
            const query = params.toString();
            navigate(`/reports/tasks/${taskId}${query ? `?${query}` : ""}`);
          }
        }}
        stickyHeader={true}
        maxHeight="60vh"
      />

      <Box sx={{ display: "flex", justifyContent: "flex-end", mt: 2 }}>
        <Pagination
          count={Math.max(1, Math.ceil(filteredItems.length / rowsPerPage))}
          page={page}
          onChange={(_, p) => setPage(p)}
          color="primary"
          size="small"
        />
      </Box>
    </Box>
  );
}
