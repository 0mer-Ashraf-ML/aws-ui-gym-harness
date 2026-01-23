/**
 * Download utilities for exporting files
 */

/**
 * Sanitize a filename by replacing invalid characters
 * @param filename - The filename to sanitize
 * @returns Sanitized filename safe for file systems
 */
export function sanitizeFilename(filename: string): string {
  return filename
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, "_") // Replace invalid characters
    .replace(/\s+/g, "_") // Replace spaces with underscores
    .replace(/_+/g, "_") // Replace multiple underscores with single
    .replace(/^_+|_+$/g, ""); // Remove leading/trailing underscores
}

/**
 * Trigger a download of JSON data as a file
 * @param data - The data to download as JSON
 * @param filename - The filename for the download (will be sanitized)
 */
export function downloadJSON(data: unknown, filename: string): void {
  // Sanitize filename and ensure .json extension
  const sanitized = sanitizeFilename(filename);
  const finalFilename = sanitized.endsWith(".json")
    ? sanitized
    : `${sanitized}.json`;

  // Create blob and download
  const jsonString = JSON.stringify(data, null, 2);
  const blob = new Blob([jsonString], { type: "application/json" });
  const url = URL.createObjectURL(blob);

  // Create temporary anchor element and trigger download
  const link = document.createElement("a");
  link.href = url;
  link.download = finalFilename;
  document.body.appendChild(link);
  link.click();

  // Cleanup
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
