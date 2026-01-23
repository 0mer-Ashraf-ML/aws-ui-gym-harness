/**
 * Download service for handling archive downloads with progress tracking
 * Similar to Google Drive's download experience
 */

import type { DownloadProgressUpdate } from '../types/download';

export interface DownloadOptions {
  url: string;
  filename: string;
  onProgress?: (update: DownloadProgressUpdate) => void;
  abortController?: AbortController;
  token?: string;
}

export interface DownloadResult {
  blob: Blob;
  filename: string;
}

/**
 * Download a file with progress tracking
 * Uses fetch API with ReadableStream for real-time progress updates
 */
export async function downloadWithProgress(
  options: DownloadOptions
): Promise<DownloadResult> {
  const { url, filename, onProgress, abortController, token } = options;

  const headers: HeadersInit = {
    'Cache-Control': 'no-store',
    'Pragma': 'no-cache',
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    method: 'GET',
    credentials: 'include',
    cache: 'no-store',
    headers,
    signal: abortController?.signal,
  });

  if (!response.ok) {
    throw new Error(`Download failed: ${response.status} ${response.statusText}`);
  }

  const contentLength = response.headers.get('content-length');
  const totalBytes = contentLength ? parseInt(contentLength, 10) : undefined;

  if (!response.body) {
    throw new Error('Response body is null');
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let downloadedBytes = 0;
  let lastUpdateTime = Date.now();
  let lastDownloadedBytes = 0;

  // Send initial progress update (0% or small progress to show download started)
  if (onProgress) {
    onProgress({
      id: '',
      progress: 0,
      downloadedBytes: 0,
      speed: 0,
      eta: 0,
    });
  }

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) break;

      chunks.push(value);
      downloadedBytes += value.length;

      // Calculate speed and ETA
      const now = Date.now();
      const timeDelta = (now - lastUpdateTime) / 1000; // seconds

      // Update progress more frequently (every 200ms) for better UX
      if (timeDelta >= 0.2 && onProgress) {
        const bytesDelta = downloadedBytes - lastDownloadedBytes;
        const speed = bytesDelta / timeDelta; // bytes per second

        let progress = 0;
        let eta = 0;
        
        if (totalBytes) {
          // Calculate progress percentage
          progress = Math.min(100, Math.round((downloadedBytes / totalBytes) * 100));
          
          // Calculate ETA
          if (speed > 0) {
            const remainingBytes = totalBytes - downloadedBytes;
            eta = remainingBytes / speed;
          }
        } else {
          // If no content-length, show progress based on downloaded bytes
          // Use a logarithmic scale to show progress that increases but caps at 99%
          // This gives users feedback that download is progressing
          // Formula: progress = min(99, log10(downloadedBytes / 1024 + 1) * 20)
          // This means: 1KB = ~6%, 10KB = ~20%, 100KB = ~40%, 1MB = ~60%, 10MB = ~80%, 100MB+ = ~99%
          if (downloadedBytes > 0) {
            const kbDownloaded = downloadedBytes / 1024;
            progress = Math.min(99, Math.round(Math.log10(kbDownloaded + 1) * 20));
          } else {
            progress = 0;
          }
        }

        onProgress({
          id: '', // ID is managed by the context, not needed here
          progress,
          downloadedBytes,
          speed,
          eta,
        });

        lastUpdateTime = now;
        lastDownloadedBytes = downloadedBytes;
      }
    }

    // Final progress update - always set to 100% when complete
    if (onProgress) {
      onProgress({
        id: '', // ID is managed by the context
        progress: 100,
        downloadedBytes,
        speed: 0,
        eta: 0,
      });
    }

    const blob = new Blob(chunks as BlobPart[], { type: response.headers.get('content-type') || 'application/zip' });

    // Extract filename from Content-Disposition header if available
    const contentDisposition = response.headers.get('Content-Disposition');
    let finalFilename = filename;
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
      if (filenameMatch && filenameMatch[1]) {
        finalFilename = filenameMatch[1].replace(/['"]/g, '');
      }
    }

    return {
      blob,
      filename: finalFilename,
    };
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('Download cancelled');
    }
    throw error;
  } finally {
    reader.releaseLock();
  }
}

/**
 * Format bytes to human-readable string
 */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 Bytes';

  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

/**
 * Format speed to human-readable string
 */
export function formatSpeed(bytesPerSecond: number): string {
  return formatBytes(bytesPerSecond) + '/s';
}

/**
 * Format ETA to human-readable string
 */
export function formatETA(seconds: number): string {
  if (seconds <= 0 || !isFinite(seconds)) return 'Calculating...';

  if (seconds < 60) {
    return `${Math.round(seconds)}s remaining`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);

  if (minutes < 60) {
    return remainingSeconds > 0
      ? `${minutes}m ${remainingSeconds}s remaining`
      : `${minutes}m remaining`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  return remainingMinutes > 0
    ? `${hours}h ${remainingMinutes}m remaining`
    : `${hours}h remaining`;
}
