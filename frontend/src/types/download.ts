/**
 * Download-related types for archive download feature
 */

export type DownloadType = 'batch' | 'execution' | 'iteration';

export type DownloadStatus = 'pending' | 'downloading' | 'completed' | 'failed' | 'cancelled';

export interface DownloadItem {
  id: string;
  type: DownloadType;
  filename: string;
  url: string;
  progress: number; // 0-100
  speed: number; // bytes per second
  eta: number; // seconds remaining
  status: DownloadStatus;
  error?: string;
  startTime: number; // timestamp
  totalBytes?: number; // total file size in bytes
  downloadedBytes: number; // bytes downloaded so far
  abortController?: AbortController;
}

export interface DownloadProgressUpdate {
  id: string;
  progress: number;
  downloadedBytes: number;
  speed: number;
  eta: number;
}
