import type {
  ExecutionFile,
  ExecutionFilesResponse,
  ActionEntry,
} from "../types";

/**
 * Parse screenshot filename to extract metadata (iteration, step, action type)
 */
export interface ScreenshotMetadata {
  iteration?: number;
  step?: number;
  actionType?: string;
  timestamp?: string;
}

export function parseScreenshotMetadata(filename: string): ScreenshotMetadata {
  const metadata: ScreenshotMetadata = {};
  
  // Common patterns:
  // - iteration_1_after_click_at_176418...
  // - after_type_text_at_176418...
  // - iteration_2_step_5_after_scroll...
  
  // Extract iteration number
  const iterationMatch = filename.match(/iteration[_\s](\d+)/i);
  if (iterationMatch) {
    metadata.iteration = parseInt(iterationMatch[1], 10);
  }
  
  // Extract step number
  const stepMatch = filename.match(/step[_\s](\d+)/i);
  if (stepMatch) {
    metadata.step = parseInt(stepMatch[1], 10);
  }
  
  // Extract action type (after_click, after_type, after_scroll, etc.)
  const actionMatch = filename.match(/after[_\s]([a-z_]+)/i);
  if (actionMatch) {
    metadata.actionType = actionMatch[1].replace(/_/g, " ");
  } else {
    // Try other patterns
    const altActionMatch = filename.match(/(click|type|scroll|navigate|select|upload|screenshot)/i);
    if (altActionMatch) {
      metadata.actionType = altActionMatch[1].toLowerCase();
    }
  }
  
  // Extract timestamp if present
  const timestampMatch = filename.match(/(\d{8}_\d{6})/);
  if (timestampMatch) {
    metadata.timestamp = timestampMatch[1];
  }
  
  return metadata;
}

/**
 * Extract all screenshot files from ExecutionFilesResponse
 */
export function getAllScreenshots(
  filesData: ExecutionFilesResponse | undefined
): ExecutionFile[] {
  if (!filesData?.structure) {
    return [];
  }
  
  const screenshots: ExecutionFile[] = [];
  
  function extractFromStructure(structure: any): void {
    if (Array.isArray(structure)) {
      // Direct array of files
      structure.forEach((file) => {
        if (file.type === "screenshot") {
          screenshots.push(file);
        }
      });
    } else if (typeof structure === "object" && structure !== null) {
      // Nested structure - recurse
      Object.values(structure).forEach((value) => {
        extractFromStructure(value);
      });
    }
  }
  
  extractFromStructure(filesData.structure);
  
  // Sort by created_at timestamp (chronological order)
  return screenshots.sort((a, b) => {
    const dateA = new Date(a.created_at).getTime();
    const dateB = new Date(b.created_at).getTime();
    return dateA - dateB;
  });
}

const normalizeScreenshotPath = (path?: string | null): string => {
  if (!path) {
    return "";
  }
  return path
    .replace(/\\/g, "/")
    .replace(/^\.\/+/, "")
    .replace(/^\/+/, "")
    .toLowerCase();
};

const extractScreenshotSegment = (path: string): string => {
  const segmentIndex = path.lastIndexOf("screenshots/");
  if (segmentIndex >= 0) {
    return path.substring(segmentIndex);
  }
  return path;
};

const extractFilename = (path: string): string => {
  const normalized = path.includes("/") ? path.substring(path.lastIndexOf("/") + 1) : path;
  return normalized;
};

type ScreenshotVariant = "before" | "after" | "legacy";

export interface ScreenshotActionIndexEntry {
  action: ActionEntry;
  variant: ScreenshotVariant;
  path: string;
}

export interface ScreenshotActionIndex {
  byPath: Record<string, ScreenshotActionIndexEntry>;
  byFilename: Record<string, ScreenshotActionIndexEntry[]>;
}

const addPathToIndex = (
  index: ScreenshotActionIndex,
  action: ActionEntry,
  rawPath: string | null | undefined,
  variant: ScreenshotVariant
) => {
  if (!rawPath) return;
  const normalized = normalizeScreenshotPath(rawPath);
  if (!normalized) return;

  const segment = extractScreenshotSegment(normalized);
  const entry: ScreenshotActionIndexEntry = {
    action,
    variant,
    path: segment || normalized,
  };

  index.byPath[normalized] = entry;
  if (segment && segment !== normalized) {
    index.byPath[segment] = entry;
  }

  const fileName = extractFilename(segment || normalized);
  if (fileName) {
    const bucket = index.byFilename[fileName] ?? [];
    bucket.push(entry);
    index.byFilename[fileName] = bucket;
  }
};

export const buildScreenshotActionIndex = (
  actions: ActionEntry[] | undefined
): ScreenshotActionIndex => {
  const index: ScreenshotActionIndex = {
    byPath: {},
    byFilename: {},
  };

  if (!actions?.length) {
    return index;
  }

  actions.forEach((action) => {
    addPathToIndex(index, action, action.screenshot_after, "after");
    addPathToIndex(index, action, action.screenshot_before, "before");
    addPathToIndex(index, action, action.screenshot_path, "legacy");
  });

  return index;
};

export interface ScreenshotActionMatch {
  action: ActionEntry;
  variant: ScreenshotVariant;
}

export const findActionForScreenshot = (
  file: ExecutionFile | null,
  index: ScreenshotActionIndex | null | undefined
): ScreenshotActionMatch | null => {
  if (!file || !index) {
    return null;
  }

  const normalizedPath = normalizeScreenshotPath(file.path || file.name);
  const candidates: (ScreenshotActionMatch | null)[] = [];

  const tryLookup = (key: string | undefined) => {
    if (!key) return null;
    const match = index.byPath[key];
    if (match) {
      return { action: match.action, variant: match.variant };
    }
    return null;
  };

  candidates.push(tryLookup(normalizedPath));
  candidates.push(tryLookup(extractScreenshotSegment(normalizedPath)));

  const filename = extractFilename(normalizedPath);
  if (filename) {
    const bucket = index.byFilename[filename];
    if (bucket?.length) {
      const match = bucket[0];
      candidates.push({ action: match.action, variant: match.variant });
    }
  }

  if (file.name) {
    const directFilename = file.name.toLowerCase();
    const bucket = index.byFilename[directFilename];
    if (bucket?.length) {
      const match = bucket[0];
      candidates.push({ action: match.action, variant: match.variant });
    }
  }

  return candidates.find((candidate): candidate is ScreenshotActionMatch => !!candidate) ?? null;
};

export const formatSecondsIntoExecution = (seconds: number): string => {
  if (seconds < 60) {
    return `${Math.round(seconds)}s into execution`;
  }
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const remaining = Math.round(seconds % 60);
    return remaining > 0
      ? `${minutes}m ${remaining}s into execution`
      : `${minutes}m into execution`;
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return minutes > 0
    ? `${hours}h ${minutes}m into execution`
    : `${hours}h into execution`;
};

export const getRelativeTimeLabel = (file?: ExecutionFile | null): string | null => {
  if (!file) return null;
  if (file.relative_created_at) {
    return file.relative_created_at;
  }
  if (typeof file.seconds_into_execution === "number") {
    return formatSecondsIntoExecution(file.seconds_into_execution);
  }
  if (file.created_at) {
    try {
      return new Date(file.created_at).toLocaleString();
    } catch {
      return file.created_at;
    }
  }
  return null;
};

export const ACTION_METADATA_LABELS: Record<string, string> = {
  element: "Element",
  selector: "Selector",
  coordinates: "Coordinates",
  target_coordinates: "Target Coordinates",
  coordinates_normalized: "Coordinates (normalized)",
  start_coordinates: "Start Coordinates",
  start_coordinates_normalized: "Start (normalized)",
  text: "Text",
  key: "Key",
  scroll_distance: "Scroll Distance",
  scroll_axis: "Scroll Axis",
  direction: "Direction",
  amount: "Amount",
  magnitude: "Magnitude",
  drag_path: "Drag Path",
};

export const formatMetadataValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "";
  }
  if (Array.isArray(value)) {
    return value
      .map((item) =>
        typeof item === "object" ? JSON.stringify(item) : String(item)
      )
      .join(", ");
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
};

/**
 * Get navigation context for a screenshot (previous/next)
 */
export function getScreenshotNavigation(
  currentFile: ExecutionFile,
  allScreenshots: ExecutionFile[]
): { previous: ExecutionFile | null; next: ExecutionFile | null; index: number; total: number } {
  const currentIndex = allScreenshots.findIndex(
    (file) => file.path === currentFile.path
  );
  
  if (currentIndex === -1) {
    return {
      previous: null,
      next: null,
      index: 0,
      total: allScreenshots.length,
    };
  }
  
  return {
    previous: currentIndex > 0 ? allScreenshots[currentIndex - 1] : null,
    next: currentIndex < allScreenshots.length - 1 ? allScreenshots[currentIndex + 1] : null,
    index: currentIndex + 1,
    total: allScreenshots.length,
  };
}

