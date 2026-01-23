/**
 * Hook for managing download queue with progress tracking
 * Similar to Google Drive's download management
 * 
 * This hook now uses the DownloadQueueContext to share state across components
 */

import type { DownloadItem, DownloadType } from '../types/download';
import { useDownloadQueueContext } from '../contexts/DownloadQueueContext';

interface UseDownloadQueueReturn {
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

/**
 * Hook to access download queue functionality
 * Uses shared context state so all components see the same downloads
 */
export function useDownloadQueue(): UseDownloadQueueReturn {
  return useDownloadQueueContext();
}
