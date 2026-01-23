import { useQuery } from "@tanstack/react-query";
import { useState, useEffect, useMemo } from "react";
import { fileApi } from "../services/api";
import type {
  ExecutionFilesResponse,
  DriveFolder,
  DriveViewState,
  ExecutionFile,
} from "../types";

/**
 * Hook for execution files with skeleton loading during sync
 */
export const useExecutionFilesRealtime = (
  executionId: string | undefined,
  format: "hierarchical" | "flat" = "hierarchical",
  executionStatus?: string,
  options = {},
) => {
  const opts = options as any;
  const globallyDisabled = opts?.enabled === false;
  const [lastFileCount, setLastFileCount] = useState(0);
  const [syncingFiles, setSyncingFiles] = useState(false);
  const [previousExecutionStatus, setPreviousExecutionStatus] = useState<
    string | undefined
  >(executionStatus);
  const [retryCount, setRetryCount] = useState(0);
  const [lastError, setLastError] = useState<Error | null>(null);

  // Determine if we should show skeleton loading (during pending/executing)
  const isExecutionActive =
    executionStatus === "pending" || executionStatus === "executing";

  // Debug logging
  if (!globallyDisabled) {
    console.log(
      `🔍 Execution ${executionId?.slice(0, 8)}: status="${executionStatus}", isActive=${isExecutionActive}, isSyncing=${syncingFiles}`,
    );
  }

  const query = useQuery({
    queryKey: ["execution-files-realtime", executionId, format],
    queryFn: async () => {
      if (globallyDisabled) {
        // Do not fetch when globally disabled
        return Promise.reject(new Error("execution-files realtime disabled"));
      }
      try {
        const result = await fileApi.getExecutionFiles(executionId!, format);
        // Reset retry count on successful fetch
        if (retryCount > 0) {
          console.log(`✅ File fetch recovered after ${retryCount} retries`);
          setRetryCount(0);
        }
        setLastError(null);
        return result;
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : "Unknown error";
        console.error(`❌ File fetch failed: ${errorMsg}`);
        setLastError(error instanceof Error ? error : new Error(errorMsg));
        throw error;
      }
    },
    enabled: !!executionId && !globallyDisabled,
    // Poll every 3s during active execution
    refetchInterval: globallyDisabled ? false : (isExecutionActive ? 3000 : false),
    // Keep polling if the tab loses focus so folders appear as soon as they are created
    refetchIntervalInBackground: true,
    staleTime: globallyDisabled ? Infinity : (isExecutionActive ? 1000 : 30000),
    gcTime: 30000, // Keep in cache for 30 seconds after unmount
    retry: (failureCount) => {
      // Retry up to 3 times for active executions, 1 time for inactive
      const maxRetries = isExecutionActive ? 3 : 1;

      if (failureCount < maxRetries) {
        const delay = Math.min(1000 * Math.pow(2, failureCount), 10000); // Exponential backoff, max 10s
        console.log(
          `🔄 Retrying file fetch in ${delay}ms (attempt ${failureCount + 1}/${maxRetries})`,
        );
        setRetryCount(failureCount + 1);
        return true;
      }

      console.error(
        `💀 File fetch failed permanently after ${maxRetries} attempts`,
      );
      return false;
    },
    retryDelay: (attemptIndex) =>
      Math.min(1000 * Math.pow(2, attemptIndex), 10000),
    ...options,
  });

  // Handle execution status changes and force refetch
  useEffect(() => {
    if (globallyDisabled) return;
    if (executionStatus !== previousExecutionStatus) {
      console.log(
        `🔄 Status changed from "${previousExecutionStatus}" to "${executionStatus}" - forcing refetch`,
      );
      setPreviousExecutionStatus(executionStatus);

      // Reset retry count when status changes
      setRetryCount(0);
      setLastError(null);

      // Force refetch when status changes with error handling
      if (executionId) {
        query.refetch().catch((error) => {
          console.error(`❌ Status change refetch failed:`, error);
        });
      }
    }
  }, [executionStatus, previousExecutionStatus, executionId, query]);

  // Simplified syncing state management
  useEffect(() => {
    if (globallyDisabled) return;
    if (query.data?.total_files !== undefined) {
      const currentFileCount = query.data.total_files;

      // If execution is active, we're syncing files
      if (isExecutionActive) {
        if (!syncingFiles) {
          console.log(
            `📁 Starting file sync for execution ${executionId?.slice(0, 8)}`,
          );
          setSyncingFiles(true);
        }

        // Track file count changes
        if (lastFileCount > 0 && currentFileCount > lastFileCount) {
          console.log(
            `📁 Files synced: ${currentFileCount - lastFileCount} new files detected (total: ${currentFileCount})`,
          );
        }
        setLastFileCount(currentFileCount);
      } else if (syncingFiles && !isExecutionActive) {
        // Execution finished - continue syncing for a bit longer to catch final files
        console.log(
          `⏰ Execution completed, continuing sync for 8 more seconds...`,
        );
        const finalSyncTimer = setTimeout(() => {
          setSyncingFiles(false);
          console.log(
            `📁 File sync completed. Final count: ${currentFileCount} files`,
          );
        }, 8000); // 8 second delay to ensure all files are synced

        return () => {
          console.log(`🚫 Clearing final sync timer`);
          clearTimeout(finalSyncTimer);
        };
      }
    }
  }, [
    query.data?.total_files,
    isExecutionActive,
    lastFileCount,
    syncingFiles,
    executionId,
  ]);

  // Continue polling for a short time even after execution ends
  const shouldPoll = isExecutionActive || (syncingFiles && !isExecutionActive);

  // Override the refetch interval if we need to keep polling
  useEffect(() => {
    if (globallyDisabled) return;
    let interval: NodeJS.Timeout | null = null;

    if (shouldPoll && !isExecutionActive) {
      // Poll every 1 second for 5 seconds after execution ends to catch late files
      console.log(`🔄 Starting post-execution polling (burst)`);
      interval = setInterval(() => {
        console.log(`🔄 Post-execution refetch`);
        query.refetch().catch((error) => {
          console.warn(`⚠️ Post-execution refetch failed:`, error);
        });
      }, 1000);

      // Stop after 5 seconds
      setTimeout(() => {
        if (interval) {
          console.log(`⏹️ Stopping post-execution polling`);
          clearInterval(interval);
        }
      }, 5000);
    }

    return () => {
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [shouldPoll, isExecutionActive, query]);

  const isShowingSkeleton = isExecutionActive || syncingFiles;

  return {
    ...query,
    isShowingSkeleton,
    isSyncing: syncingFiles,
    retryCount,
    lastError,
    hasError: !!query.error || !!lastError,
    totalFiles: query.data?.total_files || 0,
  };
};

/**
 * Hook for execution summary data
 */
export const useExecutionSummary = (
  executionId: string | undefined,
  options = {},
) => {
  return useQuery({
    queryKey: ["execution-summary", executionId],
    queryFn: () => fileApi.getExecutionSummary(executionId!),
    enabled: !!executionId,
    staleTime: 60000, // Summary changes less frequently
    gcTime: 60000,
    ...options,
  });
};

/**
 * Transform hierarchical data to drive-like folder structure
 */
export const useDriveStructure = (data: ExecutionFilesResponse | undefined) => {
  const [driveState, setDriveState] = useState<
    Omit<DriveViewState, "sortBy" | "sortOrder">
  >({
    currentPath: [],
    searchTerm: "",
    viewMode: "grid",
  });

  // Detect if structure has category-based folders (logs, screenshots, etc.)
  // vs complex nested structure (task/iteration/model)
  const hasCategoryFolders = useMemo(() => {
    if (!data?.structure) return false;

    const keys = Object.keys(data.structure);
    
    // Only consider it category-based if ALL non-root_files keys are categories
    const nonRootKeys = keys.filter((key) => key !== "root_files");
    
    // If there are no non-root keys, it's not category-based
    if (nonRootKeys.length === 0) return false;
    
    // Check if all non-root keys are direct category folders
    // (meaning the structure is flat: { logs: [...], screenshots: [...], files: [...] })
    const allAreCategories = nonRootKeys.every((key) => {
      const value = data.structure![key];
      // Category folders should contain arrays of files directly
      return Array.isArray(value);
    });
    
    return allAreCategories;
  }, [data?.structure]);

  // Structure is simplified only if it ONLY contains root_files
  const isSimplifiedStructure = useMemo(() => {
    if (!data?.structure) return false;
    const keys = Object.keys(data.structure);
    return keys.length === 1 && keys[0] === "root_files";
  }, [data?.structure]);

  // Create folders array - for category folders or complex nested structure
  const folders = useMemo((): DriveFolder[] => {
    if (!data?.structure) return [];

    if (hasCategoryFolders) {
      // Category-based structure: create folders for everything except root_files and files
      const folderEntries = Object.entries(data.structure)
        .filter(([folderName]) => folderName !== "root_files" && folderName !== "files");
      
      return folderEntries.map(([folderName, content]) => {
        const files = Array.isArray(content) ? content : [];

        return {
          name: folderName,
          path: folderName,
          fileCount: files.length,
          subfolders: [],
          files: files,
        };
      });
    } else {
      // Complex nested structure (like iterations)
      const result = Object.entries(data.structure)
        .filter(([folderName]) => folderName !== "root_files")
        .map(([folderName, content]) => {
          let allFiles: ExecutionFile[] = [];
          let subfolders: DriveFolder[] = [];


          if (
            content &&
            typeof content === "object" &&
            !Array.isArray(content)
          ) {
            // This is a nested structure - check if it's iterations or categories
            const contentKeys = Object.keys(content);
            const firstValue = content[contentKeys[0]];
            
            // If the first value is also an object (not array), we have another level of nesting
            // This means we have: task -> iteration -> category -> files
            if (firstValue && typeof firstValue === "object" && !Array.isArray(firstValue)) {
              // Check if we have a 4-level structure (task -> iteration -> model -> category -> files)
              // or 3-level structure (task -> iteration -> category -> files)
              const firstIterationValue = firstValue[Object.keys(firstValue)[0]];
              const hasModelLevel = firstIterationValue && typeof firstIterationValue === "object" && !Array.isArray(firstIterationValue);

              if (hasModelLevel) {
                // 4-level structure: task -> iteration -> model -> category -> files
                subfolders = Object.entries(content).map(([iterationName, iterationContent]) => {
                  let iterationFiles: ExecutionFile[] = [];
                  let iterationSubfolders: DriveFolder[] = [];

                  if (iterationContent && typeof iterationContent === "object" && !Array.isArray(iterationContent)) {
                    // Create model subfolders within the iteration
                    iterationSubfolders = Object.entries(iterationContent).map(([modelName, modelContent]) => {
                      let modelFiles: ExecutionFile[] = [];
                      let modelSubfolders: DriveFolder[] = [];

                      if (modelContent && typeof modelContent === "object" && !Array.isArray(modelContent)) {
                        // Create category subfolders within the model
                        modelSubfolders = Object.entries(modelContent).map(([categoryName, categoryFiles]) => {
                          const files = Array.isArray(categoryFiles) ? categoryFiles : [];
                          modelFiles = [...modelFiles, ...files];

                          return {
                            name: categoryName,
                            path: `${folderName}/${iterationName}/${modelName}/${categoryName}`,
                            fileCount: files.length,
                            subfolders: [],
                            files: files,
                          };
                        });
                      }

                      iterationFiles = [...iterationFiles, ...modelFiles];

                      return {
                        name: modelName,
                        path: `${folderName}/${iterationName}/${modelName}`,
                        fileCount: modelFiles.length,
                        subfolders: modelSubfolders,
                        files: modelFiles,
                      };
                    });
                  }

                  allFiles = [...allFiles, ...iterationFiles];

                  return {
                    name: iterationName,
                    path: `${folderName}/${iterationName}`,
                    fileCount: iterationFiles.length,
                    subfolders: iterationSubfolders,
                    files: iterationFiles,
                  };
                });
              } else {
                // 3-level structure: task -> iteration -> category -> files
                subfolders = Object.entries(content).map(([iterationName, iterationContent]) => {
                  let iterationFiles: ExecutionFile[] = [];
                  let iterationSubfolders: DriveFolder[] = [];

                  if (iterationContent && typeof iterationContent === "object" && !Array.isArray(iterationContent)) {
                    // Create category subfolders within the iteration
                    iterationSubfolders = Object.entries(iterationContent).map(([categoryName, categoryFiles]) => {
                      const files = Array.isArray(categoryFiles) ? categoryFiles : [];
                      iterationFiles = [...iterationFiles, ...files];

                      return {
                        name: categoryName,
                        path: `${folderName}/${iterationName}/${categoryName}`,
                        fileCount: files.length,
                        subfolders: [],
                        files: files,
                      };
                    });
                  }

                  allFiles = [...allFiles, ...iterationFiles];

                  return {
                    name: iterationName,
                    path: `${folderName}/${iterationName}`,
                    fileCount: iterationFiles.length,
                    subfolders: iterationSubfolders,
                    files: iterationFiles,
                  };
                });
              }
            } else {
              // Direct category structure: task -> category -> files
              subfolders = Object.entries(content).map(
                ([categoryName, categoryFiles]) => {
                  const files = Array.isArray(categoryFiles) ? categoryFiles : [];
                  allFiles = [...allFiles, ...files];


                  return {
                    name: categoryName,
                    path: `${folderName}/${categoryName}`,
                    fileCount: files.length,
                    subfolders: [],
                    files: files,
                  };
                },
              );
            }
          } else if (Array.isArray(content)) {
            // Direct array of files
            allFiles = content;
          }

          const folder = {
            name: folderName,
            path: folderName,
            fileCount: allFiles.length,
            subfolders: subfolders,
            files: allFiles,
          };


          return folder;
        });

      return result;
    }
  }, [data?.structure, hasCategoryFolders]);

  const updateDriveState = (updates: Partial<DriveViewState>) => {
    setDriveState((prev) => ({ ...prev, ...updates }));
  };

  const navigateToFolder = (folderPath: string[]) => {
    setDriveState((prev) => ({ ...prev, currentPath: folderPath }));
  };

  const navigateBack = () => {
    setDriveState((prev) => ({
      ...prev,
      currentPath: prev.currentPath.slice(0, -1),
    }));
  };

  const navigateToRoot = () => {
    setDriveState((prev) => ({ ...prev, currentPath: [] }));
  };

  // Get current folder based on path
  const currentFolder = useMemo(() => {
    if (driveState.currentPath.length === 0) return null;

    // Navigate through nested folder structure
    let currentFolderObj: DriveFolder | null = null;

    for (let i = 0; i < driveState.currentPath.length; i++) {
      const pathSegment = driveState.currentPath[i];

      if (i === 0) {
        // First level - look in main folders
        currentFolderObj = folders.find((f) => f.name === pathSegment) || null;
      } else {
        // Nested level - look in current folder's subfolders
        if (currentFolderObj && currentFolderObj.subfolders) {
          currentFolderObj =
            currentFolderObj.subfolders.find((f) => f.name === pathSegment) ||
            null;
        } else {
          currentFolderObj = null;
        }
      }

      if (!currentFolderObj) break;
    }

    return currentFolderObj;
  }, [folders, driveState.currentPath]);

  // Get filtered and sorted files for current view
  const getCurrentItems = useMemo(() => {
    let currentFiles: ExecutionFile[] = [];
    let currentFolders: DriveFolder[] = [];

    if (!currentFolder) {
      // Root level
      if (hasCategoryFolders && data?.structure) {
        // Category-based structure - show category folders + root files directly
        currentFolders = folders;

        // Add root_files to the current files if they exist
        if (
          data.structure.root_files &&
          Array.isArray(data.structure.root_files)
        ) {
          currentFiles = [...data.structure.root_files];
        }

        // Add files from the "files" category directly to root level
        if (
          data.structure.files &&
          Array.isArray(data.structure.files)
        ) {
          currentFiles = [...currentFiles, ...data.structure.files];
        }
      } else if (isSimplifiedStructure && data?.structure) {
        // Only root_files - show them directly
        currentFiles = [];
        Object.values(data.structure).forEach((value) => {
          if (Array.isArray(value)) {
            currentFiles.push(...value);
          }
        });
      } else {
        // Complex nested structure - show folders + root_files at root
        currentFolders = folders;

        // Add root_files to the current files if they exist
        if (
          data?.structure?.root_files &&
          Array.isArray(data.structure.root_files)
        ) {
          currentFiles = [...data.structure.root_files];
        }
      }
    } else {
      // Inside a folder
      
      // Check if we're in a category folder (logs, screenshots, etc.)
      const isCategoryFolder = ['logs', 'screenshots', 'files', 'conversation_history', 'task_responses'].includes(
        driveState.currentPath[driveState.currentPath.length - 1]
      );

      if (currentFolder.subfolders.length > 0 && !isCategoryFolder) {
        // Show subfolders (like categories within iterations) only if not in a category folder
        currentFolders = currentFolder.subfolders;
      } else {
        // Show files directly (especially for category folders like logs, screenshots)
        currentFiles = currentFolder.files;
      }
    }

    // Apply search filter to files
    if (driveState.searchTerm && currentFiles.length > 0) {
      currentFiles = currentFiles.filter(
        (file) =>
          file.name
            .toLowerCase()
            .includes(driveState.searchTerm.toLowerCase()) ||
          file.type.toLowerCase().includes(driveState.searchTerm.toLowerCase()),
      );
    }

    return {
      folders: currentFolders,
      files: currentFiles,
    };
  }, [
    folders,
    currentFolder,
    driveState.searchTerm,
    isSimplifiedStructure,
    hasCategoryFolders,
    data?.structure,
  ]);

  return {
    folders,
    driveState,
    currentFolder,
    getCurrentItems,
    updateDriveState,
    navigateToFolder,
    navigateBack,
    navigateToRoot,
    isSimplifiedStructure,
    hasCategoryFolders,
  };
};

/**
 * Hook for managing file selections in the drive
 */
export const useFileSelection = () => {
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());

  const selectFile = (filePath: string) => {
    setSelectedFiles((prev) => new Set([...prev, filePath]));
  };

  const deselectFile = (filePath: string) => {
    setSelectedFiles((prev) => {
      const newSet = new Set(prev);
      newSet.delete(filePath);
      return newSet;
    });
  };

  const toggleFileSelection = (filePath: string) => {
    setSelectedFiles((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(filePath)) {
        newSet.delete(filePath);
      } else {
        newSet.add(filePath);
      }
      return newSet;
    });
  };

  const selectAll = (files: ExecutionFile[]) => {
    setSelectedFiles(new Set(files.map((f) => f.path)));
  };

  const clearSelection = () => {
    setSelectedFiles(new Set());
  };

  const isFileSelected = (filePath: string) => {
    return selectedFiles.has(filePath);
  };

  return {
    selectedFiles,
    selectFile,
    deselectFile,
    toggleFileSelection,
    selectAll,
    clearSelection,
    isFileSelected,
    selectedCount: selectedFiles.size,
  };
};

/**
 * Hook for file download operations with progress tracking
 */
export const useFileDownload = () => {
  const [downloadProgress, setDownloadProgress] = useState<
    Record<string, number>
  >({});
  const [isDownloading, setIsDownloading] = useState<Set<string>>(new Set());

  const downloadFile = async (executionId: string, file: ExecutionFile) => {
    const fileKey = `${executionId}-${file.path}`;

    try {
      setIsDownloading((prev) => new Set([...prev, fileKey]));
      setDownloadProgress((prev) => ({ ...prev, [fileKey]: 0 }));

      const blob = await fileApi.downloadFile(
        executionId,
        file.path,
        (progress) => {
          setDownloadProgress((prev) => ({ ...prev, [fileKey]: progress }));
        },
      );

      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();

      // Cleanup
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      console.log(`✅ Downloaded: ${file.name}`);
    } catch (error) {
      console.error(`❌ Download failed for ${file.name}:`, error);
      throw error;
    } finally {
      setIsDownloading((prev) => {
        const newSet = new Set(prev);
        newSet.delete(fileKey);
        return newSet;
      });

      // Clear progress after a delay
      setTimeout(() => {
        setDownloadProgress((prev) => {
          const { [fileKey]: _removed, ...rest } = prev;
          void _removed; // Acknowledge the unused variable
          return rest;
        });
      }, 2000);
    }
  };

  const downloadMultipleFiles = async (
    executionId: string,
    files: ExecutionFile[],
  ) => {
    console.log(`📦 Starting bulk download of ${files.length} files`);

    const downloadPromises = files.map((file) =>
      downloadFile(executionId, file),
    );

    try {
      await Promise.all(downloadPromises);
      console.log("✅ Bulk download completed");
    } catch (error) {
      console.error("❌ Bulk download failed:", error);
      throw error;
    }
  };

  return {
    downloadFile,
    downloadMultipleFiles,
    downloadProgress,
    isDownloading,
    getFileProgress: (executionId: string, filePath: string) =>
      downloadProgress[`${executionId}-${filePath}`] || 0,
    isFileDownloading: (executionId: string, filePath: string) =>
      isDownloading.has(`${executionId}-${filePath}`),
  };
};

/**
 * Utility hook for file operations
 */
export const useFileUtils = () => {
  const formatFileSize = (bytes: number): string => {
    const units = ["B", "KB", "MB", "GB"];
    let size = bytes;
    let unitIndex = 0;

    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }

    return `${size.toFixed(1)} ${units[unitIndex]}`;
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    const now = new Date();
    const diffInMinutes = (now.getTime() - date.getTime()) / (1000 * 60);

    if (diffInMinutes < 1) return "Just now";
    if (diffInMinutes < 60) return `${Math.floor(diffInMinutes)}m ago`;
    if (diffInMinutes < 1440) return `${Math.floor(diffInMinutes / 60)}h ago`;
    return date.toLocaleDateString();
  };

  const getFileTypeColor = (type: string): string => {
    switch (type) {
      case "screenshot":
        return "#4caf50"; // green
      case "log":
        return "#ff9800"; // orange
      case "json":
        return "#2196f3"; // blue
      case "csv":
        return "#9c27b0"; // purple
      default:
        return "#757575"; // grey
    }
  };

  const canPreviewFile = (type: string): boolean => {
    return ["screenshot", "json", "log"].includes(type);
  };

  return {
    formatFileSize,
    formatDate,
    getFileTypeColor,
    canPreviewFile,
  };
};
