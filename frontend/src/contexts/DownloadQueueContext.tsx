/**
 * Download Queue Context Provider
 * Shares download queue state across all components
 */

import React, { createContext, useContext, useState, useCallback, useRef, useEffect, type ReactNode } from 'react';
import type { DownloadItem, DownloadStatus, DownloadType, DownloadProgressUpdate } from '../types/download';
import { downloadWithProgress } from '../services/downloadService';

interface DownloadQueueContextValue {
  downloads: DownloadItem[];
  activeDownloads: DownloadItem[];
  completedDownloads: DownloadItem[];
  addDownload: (
    type: DownloadType,
    url: string,
    filename: string,
    token?: string
  ) => Promise<string>; // Returns download ID
  cancelDownload: (id: string) => void;
  removeDownload: (id: string) => void;
  clearCompleted: () => void;
}

const DownloadQueueContext = createContext<DownloadQueueContextValue | undefined>(undefined);

interface DownloadQueueProviderProps {
  children: ReactNode;
}

const AUTO_REMOVE_DELAY = 5000; // Remove completed downloads after 5 seconds

export const DownloadQueueProvider: React.FC<DownloadQueueProviderProps> = ({ children }) => {
  const [downloads, setDownloads] = useState<DownloadItem[]>([]);
  const downloadRefs = useRef<Map<string, AbortController>>(new Map());
  const removeTimers = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const isProcessingRef = useRef<boolean>(false);
  const downloadsRef = useRef<DownloadItem[]>([]);
  
  // Keep ref in sync with state
  useEffect(() => {
    downloadsRef.current = downloads;
  }, [downloads]);

  // Filter active downloads (pending or downloading)
  const activeDownloads = downloads.filter(
    (d) => d.status === 'pending' || d.status === 'downloading'
  );

  // Filter completed downloads (completed, failed, or cancelled)
  const completedDownloads = downloads.filter(
    (d) => d.status === 'completed' || d.status === 'failed' || d.status === 'cancelled'
  );

  /**
   * Remove a download from the queue
   */
  const removeDownload = useCallback((id: string) => {
    // Cancel if active
    const controller = downloadRefs.current.get(id);
    if (controller) {
      controller.abort();
      downloadRefs.current.delete(id);
    }

    // Clear auto-remove timer
    const timer = removeTimers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      removeTimers.current.delete(id);
    }

    setDownloads((prev) => prev.filter((d) => d.id !== id));
  }, []);

  /**
   * Update download progress
   */
  const updateProgress = useCallback((id: string, update: DownloadProgressUpdate) => {
    setDownloads((prev) =>
      prev.map((download) =>
        download.id === id
          ? {
              ...download,
              progress: update.progress,
              downloadedBytes: update.downloadedBytes,
              speed: update.speed,
              eta: update.eta,
              status: 'downloading' as DownloadStatus,
            }
          : download
      )
    );
  }, []);

  /**
   * Update download status
   */
  const updateStatus = useCallback(
    (id: string, status: DownloadStatus, error?: string) => {
      setDownloads((prev) =>
        prev.map((download) =>
          download.id === id
            ? {
                ...download,
                status,
                error,
                ...(status === 'completed' ? { progress: 100, eta: 0, speed: 0 } : {}),
              }
            : download
        )
      );

      // Clean up abort controller
      if (status === 'completed' || status === 'failed' || status === 'cancelled') {
        const controller = downloadRefs.current.get(id);
        if (controller) {
          controller.abort();
          downloadRefs.current.delete(id);
        }

        // Auto-remove completed downloads after delay
        if (status === 'completed') {
          const timer = setTimeout(() => {
            removeDownload(id);
          }, AUTO_REMOVE_DELAY);
          removeTimers.current.set(id, timer);
        }
      }
    },
    [removeDownload]
  );

  /**
   * Process the next pending download in the queue
   * Only processes one download at a time (sequential)
   */
  const processNextDownload = useCallback(async () => {
    // Prevent concurrent processing
    if (isProcessingRef.current) {
      return;
    }

    // Get current downloads from ref (always up-to-date)
    const currentDownloads = downloadsRef.current;
    
    // Find next pending download
    const nextDownload = currentDownloads.find(
      (d) => d.status === 'pending'
    );

    if (!nextDownload) {
      return; // No pending downloads
    }

    // Start processing
    isProcessingRef.current = true;
    const { id, url, filename, abortController } = nextDownload;

    // Get token from the download item (stored during addDownload)
    const token = (nextDownload as any).token as string | undefined;

    try {
      // Update status to downloading
      updateStatus(id, 'downloading');

      const result = await downloadWithProgress({
        url,
        filename,
        token,
        abortController,
        onProgress: (update) => {
          updateProgress(id, update);
        },
      });

      // Download complete - trigger browser download
      const blobUrl = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = result.filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      // Clean up blob URL after a delay
      setTimeout(() => {
        URL.revokeObjectURL(blobUrl);
      }, 100);

      // Update status to completed
      updateStatus(id, 'completed');
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Download failed';
      
      if (errorMessage === 'Download cancelled') {
        updateStatus(id, 'cancelled');
      } else {
        updateStatus(id, 'failed', errorMessage);
      }
    } finally {
      isProcessingRef.current = false;
      // Process next download in queue after a short delay
      setTimeout(() => {
        processNextDownload();
      }, 100);
    }
  }, [updateProgress, updateStatus]);

  /**
   * Add a new download to the queue
   * Downloads are processed sequentially (one at a time)
   */
  const addDownload = useCallback(
    async (
      type: DownloadType,
      url: string,
      filename: string,
      token?: string
    ): Promise<string> => {
      const id = `download-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      const abortController = new AbortController();
      downloadRefs.current.set(id, abortController);

      const downloadItem: DownloadItem & { token?: string } = {
        id,
        type,
        filename,
        url,
        progress: 0,
        speed: 0,
        eta: 0,
        status: 'pending',
        startTime: Date.now(),
        downloadedBytes: 0,
        abortController,
        token, // Store token for later use
      };

      // Add to queue
      setDownloads((prev) => [...prev, downloadItem]);
      
      // Trigger processing if not already processing
      if (!isProcessingRef.current) {
        setTimeout(() => processNextDownload(), 0);
      }

      return id;
    },
    [processNextDownload]
  );

  /**
   * Cancel an active download
   */
  const cancelDownload = useCallback(
    (id: string) => {
      const controller = downloadRefs.current.get(id);
      if (controller) {
        controller.abort();
        downloadRefs.current.delete(id);
        updateStatus(id, 'cancelled');
      }
    },
    [updateStatus]
  );

  /**
   * Clear all completed downloads
   */
  const clearCompleted = useCallback(() => {
    completedDownloads.forEach((download) => {
      removeDownload(download.id);
    });
  }, [completedDownloads, removeDownload]);

  // Process next download when downloads change and there's a pending one
  useEffect(() => {
    if (!isProcessingRef.current) {
      const hasPending = downloads.some((d) => d.status === 'pending');
      if (hasPending) {
        processNextDownload();
      }
    }
  }, [downloads, processNextDownload]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      // Cancel all active downloads
      downloadRefs.current.forEach((controller) => {
        controller.abort();
      });
      downloadRefs.current.clear();

      // Clear all timers
      removeTimers.current.forEach((timer) => {
        clearTimeout(timer);
      });
      removeTimers.current.clear();
      
      isProcessingRef.current = false;
    };
  }, []);

  const contextValue: DownloadQueueContextValue = {
    downloads,
    activeDownloads,
    completedDownloads,
    addDownload,
    cancelDownload,
    removeDownload,
    clearCompleted,
  };

  return (
    <DownloadQueueContext.Provider value={contextValue}>
      {children}
    </DownloadQueueContext.Provider>
  );
};

/**
 * Hook to access download queue context
 */
export const useDownloadQueueContext = (): DownloadQueueContextValue => {
  const context = useContext(DownloadQueueContext);
  if (context === undefined) {
    throw new Error('useDownloadQueueContext must be used within a DownloadQueueProvider');
  }
  return context;
};

