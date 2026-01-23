import React, { useMemo, useState, useEffect, useCallback } from "react";
import {
  Box,
  Toolbar,
  TextField,
  IconButton,
  ToggleButtonGroup,
  ToggleButton,
  Chip,
  Typography,
  Card,
  CardContent,
  CardMedia,
  Breadcrumbs,
  Link,
  
} from "@mui/material";
import {
  Search as SearchIcon,
  GridView as GridIcon,
  ViewList as ListIcon,
  Folder as FolderIcon,
  PlayArrow as PlayIcon,
} from "@mui/icons-material";
import type { ExecutionFile, ExecutionFilesResponse, DriveFolder } from "../types";
import { useFiltering, type FilterCategory } from "../hooks/useFiltering";
import { useSorting, type SortOption } from "../hooks/useSorting";
import SortMenu from "../components/SortMenu";
import FilterMenu from "../components/FilterMenu";
import { useDriveStructure } from "../hooks/useExecutionFiles";
import { useFileUtils } from "../hooks/useExecutionFiles";
import { fileApi } from "../services/api";
import type { ScreenshotActionMatch } from "../utils/screenshotUtils";

// Video thumbnail component with static icon
const VideoThumbnail: React.FC<{
  height?: number;
  getFileIcon: (type: string, size?: number) => React.ReactNode;
}> = ({ height = 120, getFileIcon }) => {
  return (
    <Box
      sx={{
        position: "relative",
        height,
        backgroundColor: "grey.100",
        overflow: "hidden",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 1,
        }}
      >
        {getFileIcon("video", 48)}
        <PlayIcon
          sx={{
            fontSize: 40,
            color: "text.secondary",
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.3))",
          }}
        />
      </Box>
    </Box>
  );
};

// Helper function to check if a file is a video
const isVideoFile = (file: ExecutionFile): boolean => {
  const name = file.name.toLowerCase();
  return (
    name.endsWith(".webm") ||
    name.endsWith(".mp4") ||
    name.endsWith(".mov") ||
    name.endsWith(".avi") ||
    name.endsWith(".mkv") ||
    name.endsWith(".flv")
  );
};

interface IterationFileBrowserProps {
  executionId: string;
  iterKey: string; // e.g. "iteration_3"
  filesData?: ExecutionFilesResponse | undefined; // backward compat (unused when per-iteration fetch is enabled)
  onPreviewFile: (file: ExecutionFile, context?: { files: ExecutionFile[] }) => void;
  onDownloadFile: (file: ExecutionFile) => void;
  getFileIcon: (type: string, size?: number) => React.ReactNode;
  getActionContext?: (file: ExecutionFile) => ScreenshotActionMatch | null;
}

export const IterationFileBrowser: React.FC<IterationFileBrowserProps> = ({
  executionId,
  iterKey,
  filesData,
  onPreviewFile,
  onDownloadFile,
  getFileIcon,
  getActionContext,
}) => {
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"grid" | "list">("grid");
  // Use the files data directly since it's already filtered by iteration
  const scopedFromGlobal: ExecutionFilesResponse | undefined = useMemo(() => {
    if (!filesData) return undefined;
    
    // If this is iteration-specific data, use it directly
    // The backend already filtered the files for this iteration
    return filesData;
  }, [filesData]);

  // Drive structure uses the globally-fetched dataset scoped to this iteration
  const dataForDrive = scopedFromGlobal;
  const { driveState, getCurrentItems, navigateToFolder, navigateToRoot } = useDriveStructure(dataForDrive);
  const { formatDate, formatFileSize } = useFileUtils();

  const { folders: displayFolders, files: allFiles } = getCurrentItems;

  // Start at root since files are already filtered by iteration
  useEffect(() => {
    if (driveState.currentPath.length === 0) {
      navigateToRoot();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Build filter categories (reuse same pattern as main)
  const { filterCategories, filteredFiles } = useMemo(() => {
    const types = [...new Set(allFiles.map((file) => file.type))];
    const categories: FilterCategory<ExecutionFile>[] = [
      { key: "type", label: "File Type", options: types },
    ];
    // Apply local search term before filter/sort
    const term = search.trim().toLowerCase();
    const prefiltered = term
      ? allFiles.filter(
          (f) =>
            f.name.toLowerCase().includes(term) ||
            f.type.toLowerCase().includes(term),
        )
      : allFiles;
    return { filterCategories: categories, filteredFiles: prefiltered };
  }, [allFiles, search]);

  const { filteredItems, activeFilters, toggleFilter, clearFilters } =
    useFiltering(filteredFiles, filterCategories);

  const sortOptions: SortOption<ExecutionFile>[] = [
    { value: "name", label: "Sort by Name" },
    { value: "created_at", label: "Sort by Date" },
    { value: "size", label: "Sort by Size" },
    { value: "type", label: "Sort by Type" },
  ];

  const {
    sortedItems: displayFiles,
    requestSort,
    sortConfig,
  } = useSorting(filteredItems, sortOptions, {
    key: "created_at",
    direction: "asc",
  });

  const handlePreviewFile = useCallback(
    (file: ExecutionFile) => {
      onPreviewFile(file, { files: displayFiles });
    },
    [displayFiles, onPreviewFile]
  );

  return (
    <Box>
      <Toolbar
        sx={{
          gap: 2,
          px: 0,
          borderBottom: 1,
          borderColor: "divider",
          mb: 1,
          position: "sticky",
          top: 0,
          zIndex: 1,
          backgroundColor: "background.paper",
        }}
      >
        <Breadcrumbs sx={{ flexGrow: 1 }}>
          {(() => {
            const items: React.ReactNode[] = [];
            // Root link
            items.push(
              <Link
                key="root"
                component="button"
                variant="body2"
                onClick={() => navigateToRoot()}
                underline="none"
                color="text.secondary"
              >
                📁 Root
              </Link>,
            );

            const path = driveState.currentPath;
            // Render all path segments since we're already in iteration context
            for (let i = 0; i < path.length; i++) {
              const crumbPath = path.slice(0, i + 1);
              items.push(
                <Link
                  key={`crumb-${i}`}
                  component="button"
                  variant="body2"
                  underline="none"
                  color="text.secondary"
                  onClick={() => navigateToFolder(crumbPath)}
                >
                  {path[i]}
                </Link>,
              );
            }
            return items;
          })()}
        </Breadcrumbs>
        <TextField
          size="small"
          placeholder={`Search ${iterKey} files...`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          InputProps={{ startAdornment: <SearchIcon sx={{ color: "text.secondary", mr: 1 }} /> }}
          sx={{ width: 220 }}
        />
        <Chip label={`${displayFiles.length} file${displayFiles.length === 1 ? "" : "s"}`} size="small" />

        <SortMenu options={sortOptions} onSortChange={requestSort} sortConfig={sortConfig} />
        <FilterMenu
          options={filterCategories}
          activeFilters={activeFilters}
          onFilterToggle={toggleFilter}
          onClearFilters={clearFilters}
        />
        <Box sx={{ flexGrow: 1 }} />
        <ToggleButtonGroup
          value={view}
          exclusive
          onChange={(_, v) => v && setView(v)}
          size="small"
        >
          <ToggleButton value="grid"><GridIcon fontSize="small" /></ToggleButton>
          <ToggleButton value="list"><ListIcon fontSize="small" /></ToggleButton>
        </ToggleButtonGroup>
      </Toolbar>

      {view === "grid" ? (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "1fr",
              sm: "repeat(auto-fill, minmax(280px, 1fr))",
              md: "repeat(auto-fill, minmax(300px, 1fr))",
              lg: "repeat(auto-fill, minmax(320px, 1fr))",
            },
            gap: 2,
          }}
        >
          {/* Folders */}
          {displayFolders.map((folder: DriveFolder) => (
            <Box key={folder.path}>
              <Card sx={{ cursor: "pointer", transition: "all 0.2s", "&:hover": { transform: "translateY(-4px)", boxShadow: 4 } }} onClick={() => navigateToFolder([...driveState.currentPath, folder.name])}>
                <CardContent sx={{ textAlign: "center", py: 3 }}>
                  <FolderIcon sx={{ fontSize: 64, color: "text.secondary", mb: 1 }} />
                  <Typography variant="subtitle1" noWrap>{folder.name}</Typography>
                  <Chip label={`${folder.fileCount} files`} size="small" variant="outlined" sx={{ mt: 1 }} />
                </CardContent>
              </Card>
            </Box>
          ))}

          {/* Files */}
          {displayFiles.map((file: ExecutionFile) => {
            const actionContext = getActionContext?.(file);
            return (
              <Card
                key={file.path}
                sx={{
                  cursor: "pointer",
                  transition: "all 0.2s",
                  "&:hover": { transform: "translateY(-2px)", boxShadow: 3 },
                }}
                onClick={() => handlePreviewFile(file)}
              >
              {file.type === "screenshot" ? (
                <CardMedia
                  component="img"
                  height={120}
                  image={fileApi.getThumbnailUrl(executionId, file.path)}
                  alt={file.name}
                  sx={{ objectFit: "cover" }}
                />
              ) : isVideoFile(file) ? (
                <VideoThumbnail height={120} getFileIcon={getFileIcon} />
              ) : (
                <Box sx={{ height: 120, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "grey.100" }}>
                  {getFileIcon(file.type, 64)}
                </Box>
              )}
              <CardContent sx={{ pt: 1 }}>
                <Typography variant="subtitle2" noWrap title={file.name}>{file.name}</Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1 }}>
                  <Chip label={file.type.toUpperCase()} size="small" variant="outlined" sx={{ fontSize: "0.7rem", height: 20 }} />
                  <Typography variant="caption" color="text.secondary">{formatFileSize(file.size)}</Typography>
                  <Typography variant="caption" color="text.secondary">{formatDate(file.created_at)}</Typography>
                </Box>
                {file.type === "screenshot" && actionContext?.action && (
                  <Box sx={{ mt: 1, display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
                    <Chip
                      label={actionContext.action.action_type.toUpperCase()}
                      size="small"
                      color="primary"
                      sx={{ fontSize: "0.65rem", height: 18 }}
                    />
                    {actionContext.action.action_name && (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        noWrap
                        title={actionContext.action.action_name}
                      >
                        {actionContext.action.action_name}
                      </Typography>
                    )}
                  </Box>
                )}
              </CardContent>
              </Card>
            );
          })}
        </Box>
      ) : (
        <Box>
          {/* Folders */}
          {displayFolders.map((folder: DriveFolder) => (
            <Box key={folder.path} sx={{ display: "flex", alignItems: "center", p: 2, borderBottom: 1, borderColor: "divider", cursor: "pointer", "&:hover": { backgroundColor: "action.hover" } }} onClick={() => navigateToFolder([...driveState.currentPath, folder.name])}>
              <FolderIcon sx={{ mr: 2, color: "text.secondary" }} />
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="subtitle1">{folder.name}</Typography>
                <Typography variant="caption" color="text.secondary">{folder.fileCount} files</Typography>
              </Box>
            </Box>
          ))}

          {/* Files */}
          {displayFiles.map((file: ExecutionFile) => {
            const actionContext = getActionContext?.(file);
            return (
              <Box
                key={file.path}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  p: 2,
                  borderBottom: 1,
                  borderColor: "divider",
                  cursor: "pointer",
                  "&:hover": { backgroundColor: "action.hover" },
                }}
                onClick={() => handlePreviewFile(file)}
              >
                <Box sx={{ mr: 2 }}>{getFileIcon(file.type, 32)}</Box>
                <Box sx={{ flexGrow: 1, ml: 2, minWidth: 0 }}>
                  <Typography variant="subtitle2" noWrap>
                    {file.name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {formatDate(file.created_at)}
                  </Typography>
                  {file.type === "screenshot" && actionContext?.action && (
                    <Box sx={{ mt: 0.5, display: "flex", gap: 1, alignItems: "center" }}>
                      <Chip
                        label={actionContext.action.action_type.toUpperCase()}
                        size="small"
                        color="primary"
                        sx={{ fontSize: "0.65rem", height: 18 }}
                      />
                      {actionContext.action.action_name && (
                        <Typography variant="caption" color="text.secondary" noWrap>
                          {actionContext.action.action_name}
                        </Typography>
                      )}
                    </Box>
                  )}
                </Box>
                <Box sx={{ mr: 2 }}>
                  <Chip label={file.type.toUpperCase()} size="small" variant="outlined" />
                </Box>
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    handlePreviewFile(file);
                  }}
                  title="Preview"
                >
                  👁️
                </IconButton>
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDownloadFile(file);
                  }}
                  title="Download"
                >
                  ⬇️
                </IconButton>
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
};

export default IterationFileBrowser;
