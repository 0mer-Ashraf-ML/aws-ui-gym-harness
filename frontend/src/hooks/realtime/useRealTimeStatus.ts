import { useEffect, useRef, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Execution } from "../../types";

interface RealTimeConfig {
  enabled?: boolean;
  pollingInterval?: number;
  websocketUrl?: string;
  maxReconnectAttempts?: number;
  reconnectDelay?: number;
  debug?: boolean;
}

interface ConnectionState {
  status: "disconnected" | "connecting" | "connected" | "reconnecting" | "error";
  lastUpdate?: Date;
  reconnectAttempts: number;
  error?: string;
}

interface RealTimeStatusReturn {
  connectionState: ConnectionState;
  isConnected: boolean;
  forceReconnect: () => void;
  disconnect: () => void;
}

export const useRealTimeStatus = (
  config: RealTimeConfig = {}
): RealTimeStatusReturn => {
  const {
    enabled = true,
    pollingInterval = 3000,
    websocketUrl,
    maxReconnectAttempts = 5,
    reconnectDelay = 3000,
    debug = false,
  } = config;

  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [connectionState, setConnectionState] = useState<ConnectionState>({
    status: "disconnected",
    reconnectAttempts: 0,
  });

  const log = useCallback(
    (message: string, data?: any) => {
      if (debug) {
        console.log(`[RealTimeStatus] ${message}`, data || "");
      }
    },
    [debug]
  );

  // Update run in cache
  const updateRunInCache = useCallback(
    (updatedRun: Execution) => {
      // Update specific run cache
      queryClient.setQueryData(["runs", updatedRun.uuid], updatedRun);

      // Update main runs list cache
      queryClient.setQueryData<Execution[]>(["runs", undefined], (oldData) => {
        if (!oldData) return oldData;
        return oldData.map((run) =>
          run.uuid === updatedRun.uuid ? updatedRun : run
        );
      });

      // Update any filtered runs queries
      queryClient.invalidateQueries({
        queryKey: ["runs"],
        type: "all",
      });

      log("Updated run in cache", { uuid: updatedRun.uuid, status: updatedRun.status });
    },
    [queryClient, log]
  );

  // Polling fallback
  const startPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }

    pollingIntervalRef.current = setInterval(async () => {
      try {
        log("Polling for status updates");

        // Fetch all runs to check for status changes
        const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
        const response = await fetch(`${apiUrl}/api/v1/executions`, {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
          },
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        const runs: Execution[] = data.executions || [];

        // Check current cache and update changed runs
        const currentRuns = queryClient.getQueryData<Execution[]>(["runs", undefined]);

        if (currentRuns) {
          const changedRuns = runs.filter((newRun) => {
            const currentRun = currentRuns.find((cr) => cr.uuid === newRun.uuid);
            return currentRun && currentRun.status !== newRun.status;
          });

          changedRuns.forEach(updateRunInCache);

          if (changedRuns.length > 0) {
            log(`Updated ${changedRuns.length} runs via polling`);
            setConnectionState((prev) => ({
              ...prev,
              lastUpdate: new Date(),
            }));
          }
        }
      } catch (error) {
        log("Polling error", error);
        setConnectionState((prev) => ({
          ...prev,
          error: error instanceof Error ? error.message : "Polling failed",
        }));
      }
    }, pollingInterval);

    log("Started polling", { interval: pollingInterval });
  }, [pollingInterval, queryClient, updateRunInCache, log]);

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
      log("Stopped polling");
    }
  }, [log]);

  // WebSocket connection
  const connectWebSocket = useCallback(() => {
    if (!websocketUrl || wsRef.current) return;

    setConnectionState((prev) => ({ ...prev, status: "connecting" }));
    log("Attempting WebSocket connection", websocketUrl);

    try {
      const ws = new WebSocket(websocketUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        log("WebSocket connected");
        setConnectionState({
          status: "connected",
          reconnectAttempts: 0,
          lastUpdate: new Date(),
        });
        stopPolling(); // Stop polling when WebSocket is connected
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          log("WebSocket message received", data);

          if (data.type === "run_status_update" && data.run) {
            updateRunInCache(data.run);
            setConnectionState((prev) => ({
              ...prev,
              lastUpdate: new Date(),
            }));
          }
        } catch (error) {
          log("WebSocket message parsing error", error);
        }
      };

      ws.onclose = (event) => {
        log("WebSocket closed", { code: event.code, reason: event.reason });
        wsRef.current = null;

        if (event.code !== 1000) {
          // Not a normal closure, attempt to reconnect
          setConnectionState((prev) => ({
            ...prev,
            status: prev.reconnectAttempts >= maxReconnectAttempts ? "error" : "reconnecting",
            reconnectAttempts: prev.reconnectAttempts + 1,
            error: `Connection closed: ${event.reason || "Unknown reason"}`,
          }));

          // Try to reconnect if under max attempts
          if (connectionState.reconnectAttempts < maxReconnectAttempts) {
            reconnectTimeoutRef.current = setTimeout(() => {
              connectWebSocket();
            }, reconnectDelay);
          } else {
            // Fall back to polling
            log("Max reconnect attempts reached, falling back to polling");
            startPolling();
          }
        } else {
          setConnectionState((prev) => ({ ...prev, status: "disconnected" }));
        }
      };

      ws.onerror = (error) => {
        log("WebSocket error", error);
        setConnectionState((prev) => ({
          ...prev,
          status: "error",
          error: "WebSocket connection error",
        }));
      };
    } catch (error) {
      log("WebSocket connection failed", error);
      setConnectionState((prev) => ({
        ...prev,
        status: "error",
        error: error instanceof Error ? error.message : "Connection failed",
      }));
      // Fall back to polling
      startPolling();
    }
  }, [
    websocketUrl,
    maxReconnectAttempts,
    reconnectDelay,
    connectionState.reconnectAttempts,
    updateRunInCache,
    startPolling,
    stopPolling,
    log,
  ]);

  const disconnect = useCallback(() => {
    log("Disconnecting");

    if (wsRef.current) {
      wsRef.current.close(1000, "Manual disconnect");
      wsRef.current = null;
    }

    stopPolling();

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    setConnectionState({
      status: "disconnected",
      reconnectAttempts: 0,
    });
  }, [stopPolling, log]);

  const forceReconnect = useCallback(() => {
    log("Force reconnecting");
    disconnect();

    setTimeout(() => {
      if (websocketUrl) {
        connectWebSocket();
      } else {
        startPolling();
      }
    }, 100);
  }, [disconnect, connectWebSocket, startPolling, websocketUrl, log]);

  // Initialize connection
  useEffect(() => {
    if (!enabled) return;

    log("Initializing real-time status tracking");

    if (websocketUrl) {
      connectWebSocket();
    } else {
      startPolling();
      setConnectionState((prev) => ({ ...prev, status: "connected" }));
    }

    return () => {
      disconnect();
    };
  }, [enabled, websocketUrl, connectWebSocket, startPolling, disconnect, log]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close(1000, "Component unmounting");
      }
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  return {
    connectionState,
    isConnected: connectionState.status === "connected",
    forceReconnect,
    disconnect,
  };
};

// Helper hook for status indicator
export const useStatusIndicator = (realTimeStatus: RealTimeStatusReturn) => {
  const { connectionState } = realTimeStatus;

  const getStatusColor = () => {
    switch (connectionState.status) {
      case "connected":
        return "success";
      case "connecting":
      case "reconnecting":
        return "warning";
      case "error":
        return "error";
      default:
        return "default";
    }
  };

  const getStatusLabel = () => {
    switch (connectionState.status) {
      case "connected":
        return "Live";
      case "connecting":
        return "Connecting...";
      case "reconnecting":
        return `Reconnecting... (${connectionState.reconnectAttempts}/${5})`;
      case "error":
        return "Connection Error";
      default:
        return "Offline";
    }
  };

  return {
    color: getStatusColor(),
    label: getStatusLabel(),
    lastUpdate: connectionState.lastUpdate,
    error: connectionState.error,
  };
};
