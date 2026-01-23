import type { ActionEntry } from "../types";

export type LogLevel =
  | "trace"
  | "debug"
  | "info"
  | "success"
  | "warning"
  | "error"
  | "critical"
  | "stdout"
  | "stderr"
  | "unknown";

export interface ParsedLogLine {
  id: string;
  raw: string;
  timestamp?: string;
  timestampLabel: string;
  level: LogLevel;
  message: string;
  logger?: string;
  module?: string;
  actionId?: number;
  metadata?: Record<string, unknown>;
}

type ChipColor =
  | "default"
  | "primary"
  | "secondary"
  | "error"
  | "info"
  | "success"
  | "warning";

interface LogLevelDefinition {
  label: string;
  color: ChipColor;
  priority: number;
  aliases: string[];
}

const LOG_LEVEL_DEFINITIONS: Record<LogLevel, LogLevelDefinition> = {
  trace: {
    label: "Trace",
    color: "default",
    priority: 0,
    aliases: ["trace", "trc"],
  },
  debug: {
    label: "Debug",
    color: "info",
    priority: 1,
    aliases: ["debug", "dbg"],
  },
  info: {
    label: "Info",
    color: "primary",
    priority: 2,
    aliases: ["info", "information", "notice"],
  },
  success: {
    label: "Success",
    color: "success",
    priority: 3,
    aliases: ["success", "ok", "passed", "pass"],
  },
  warning: {
    label: "Warning",
    color: "warning",
    priority: 4,
    aliases: ["warning", "warn", "alert"],
  },
  error: {
    label: "Error",
    color: "error",
    priority: 5,
    aliases: ["error", "err", "failure", "failed"],
  },
  critical: {
    label: "Critical",
    color: "error",
    priority: 6,
    aliases: ["critical", "fatal", "panic"],
  },
  stdout: {
    label: "STDOUT",
    color: "secondary",
    priority: 1,
    aliases: ["stdout", "out"],
  },
  stderr: {
    label: "STDERR",
    color: "secondary",
    priority: 4,
    aliases: ["stderr", "errout", "std-err"],
  },
  unknown: {
    label: "Log",
    color: "default",
    priority: 2,
    aliases: ["", "log", "message"],
  },
};

const LEVEL_ALIAS_LOOKUP: Record<string, LogLevel> = Object.entries(
  LOG_LEVEL_DEFINITIONS,
).reduce<Record<string, LogLevel>>((acc, [level, config]) => {
  config.aliases.forEach((alias) => {
    if (alias) {
      acc[alias.toLowerCase()] = level as LogLevel;
    }
  });
  return acc;
}, {});

const TIMESTAMP_REGEX =
  /^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?|\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?)/;

const ACTION_ID_REGEXES = [
  /action[_\s-]?id[:=]\s*(\d+)/i,
  /action(?:\s+|#)(\d+)/i,
  /step\s+(\d+)\b/i,
];

const FILTERABLE_LEVELS: LogLevel[] = Object.keys(LOG_LEVEL_DEFINITIONS)
  .filter((level) => level !== "unknown")
  .map((level) => level as LogLevel);

const MAX_TIMESTAMP_DIFF_MS = 30 * 1000; // 30 seconds tolerance

const sortLevelsByPriority = (levels: LogLevel[]) => {
  const fallbackPriority = LOG_LEVEL_DEFINITIONS.info.priority;
  return [...levels].sort((a, b) => {
    const aPriority =
      LOG_LEVEL_DEFINITIONS[a]?.priority ?? fallbackPriority;
    const bPriority =
      LOG_LEVEL_DEFINITIONS[b]?.priority ?? fallbackPriority;
    return aPriority - bPriority;
  });
};

const buildLineId = (seed: string, index: number) => {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    const charCode = seed.charCodeAt(i);
    hash = (hash << 5) - hash + charCode;
    hash |= 0; // Convert to 32-bit integer
  }
  return `${index}-${Math.abs(hash)}`;
};

const normalizeTimestamp = (value?: string | number | null): string | undefined => {
  if (value === null || value === undefined) {
    return undefined;
  }
  if (typeof value === "number") {
    return new Date(value).toISOString();
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  if (/^\d{10}$/.test(trimmed)) {
    return new Date(Number(trimmed) * 1000).toISOString();
  }
  if (/^\d{13}$/.test(trimmed)) {
    return new Date(Number(trimmed)).toISOString();
  }
  const normalized = trimmed.replace(" ", "T").replace(/,(\d{3})/, ".$1");
  return normalized;
};

const formatTimestampLabel = (value?: string | number): string => {
  if (value === undefined || value === null) {
    return "—";
  }
  const normalized = normalizeTimestamp(value);
  if (!normalized) {
    return typeof value === "string" ? value : String(value);
  }
  const parsed = Date.parse(normalized);
  if (Number.isNaN(parsed)) {
    return normalized;
  }
  return new Date(parsed).toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

export const getTimestampParts = (
  value?: string | number,
): { date: string; time: string } => {
  if (value === undefined || value === null) {
    return { date: "—", time: "—" };
  }
  const normalized = normalizeTimestamp(value);
  if (!normalized) {
    return { date: String(value), time: "" };
  }
  const parsed = Date.parse(normalized);
  if (Number.isNaN(parsed)) {
    return { date: normalized, time: "" };
  }
  const dateObj = new Date(parsed);
  return {
    date: dateObj.toLocaleDateString([], {
      year: "numeric",
      month: "short",
      day: "2-digit",
    }),
    time: dateObj.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }),
  };
};

const normalizeLogLevel = (input?: string | null): LogLevel => {
  if (!input) {
    return "info";
  }
  const normalized = input.toString().trim().toLowerCase();
  if (LEVEL_ALIAS_LOOKUP[normalized]) {
    return LEVEL_ALIAS_LOOKUP[normalized];
  }
  switch (normalized) {
    case "warn":
      return "warning";
    case "fatal":
      return "critical";
    default:
      return "info";
  }
};

const extractActionId = (text: string): number | undefined => {
  for (const regex of ACTION_ID_REGEXES) {
    const match = text.match(regex);
    if (match?.[1]) {
      const numeric = Number.parseInt(match[1], 10);
      if (!Number.isNaN(numeric)) {
        return numeric;
      }
    }
  }
  return undefined;
};

const tryParseJsonLine = (
  line: string,
  index: number,
): ParsedLogLine | null => {
  if (!line.trim().startsWith("{")) {
    return null;
  }
  try {
    const data = JSON.parse(line) as Record<string, unknown>;
    const timestamp =
      data.timestamp ??
      data.time ??
      data.ts ??
      data.created_at ??
      data.createdAt;
    const levelValue =
      (data.level as string | undefined) ??
      (data.severity as string | undefined) ??
      (data.log_level as string | undefined);
    const actionValue =
      data.action_id ??
      data.actionId ??
      data.action ??
      (typeof data.metadata === "object" && data.metadata !== null
        ? (data.metadata as Record<string, unknown>).action_id
        : undefined);
    const message =
      (data.message as string | undefined) ??
      (data.msg as string | undefined) ??
      (data.event as string | undefined) ??
      (data.description as string | undefined) ??
      line;

    return {
      id: buildLineId(line, index),
      raw: line,
      timestamp: normalizeTimestamp(timestamp as string | number | undefined),
      timestampLabel: formatTimestampLabel(timestamp as string | number | undefined),
      level: normalizeLogLevel(levelValue),
      message,
      logger: typeof data.logger === "string" ? data.logger : undefined,
      module: typeof data.module === "string" ? data.module : undefined,
      actionId: typeof actionValue === "number" ? actionValue : extractActionId(String(actionValue ?? "")),
      metadata: data,
    };
  } catch {
    return null;
  }
};

const parsePlainTextLine = (line: string, index: number): ParsedLogLine => {
  const timestampMatch = line.match(TIMESTAMP_REGEX);
  let timestamp: string | undefined;
  let remainder = line;
  if (timestampMatch) {
    timestamp = normalizeTimestamp(timestampMatch[0]);
    remainder = line.slice(timestampMatch[0].length).replace(/^(\s*-\s*)/, "");
  }

  const structuredMatch = remainder.match(
    /^(?<logger>[^-]+?)\s+-\s+(?<level>[A-Za-z]+)\s+-\s+(?<rest>.*)$/,
  );

  let logger: string | undefined;
  let moduleName: string | undefined;
  let message = remainder.trim();
  let level: LogLevel = "info";

  if (structuredMatch?.groups) {
    logger = structuredMatch.groups.logger.trim();
    level = normalizeLogLevel(structuredMatch.groups.level);
    const rest = structuredMatch.groups.rest;
    const restParts = rest.split(" - ");
    if (restParts.length > 1) {
      moduleName = restParts[0].trim();
      message = restParts.slice(1).join(" - ").trim();
    } else {
      message = rest.trim();
    }
  } else {
    const levelMatch = remainder.match(
      /\b(INFO|DEBUG|WARNING|WARN|ERROR|CRITICAL|TRACE|SUCCESS)\b/i,
    );
    if (levelMatch?.[0]) {
      level = normalizeLogLevel(levelMatch[0]);
    }
  }

  return {
    id: buildLineId(line, index),
    raw: line,
    timestamp,
    timestampLabel: formatTimestampLabel(timestamp),
    level,
    message: message || line,
    logger,
    module: moduleName,
    actionId: extractActionId(line),
  };
};

export const parseLogContent = (
  content: string | null | undefined,
): ParsedLogLine[] => {
  if (!content) {
    return [];
  }
  const lines = content.split(/\r?\n/);
  const parsed: ParsedLogLine[] = [];
  let lastTimestamp: string | undefined;
  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) {
      if (parsed.length > 0) {
        parsed[parsed.length - 1].message = `${parsed[parsed.length - 1].message}\n`;
        parsed[parsed.length - 1].raw = `${parsed[parsed.length - 1].raw}\n`;
      }
      return;
    }

    const jsonParsed = tryParseJsonLine(trimmed, index);
    const hasTimestamp = TIMESTAMP_REGEX.test(line);

    if (!jsonParsed && !hasTimestamp && parsed.length > 0) {
      parsed[parsed.length - 1].message = `${parsed[parsed.length - 1].message}\n${trimmed}`;
      parsed[parsed.length - 1].raw = `${parsed[parsed.length - 1].raw}\n${line}`;
      return;
    }

    const parsedLine = jsonParsed ?? parsePlainTextLine(line, index);

    if (parsedLine.timestamp) {
      lastTimestamp = parsedLine.timestamp;
    } else if (lastTimestamp) {
      // Only cascade timestamp if this looks like a continuation line
      // (not a new log entry - check if it starts with a log level or looks structured)
      const looksLikeNewEntry = /^\s*(INFO|DEBUG|WARNING|WARN|ERROR|CRITICAL|TRACE|SUCCESS|STDOUT|STDERR)\b/i.test(trimmed) ||
        /^\d{4}-\d{2}-\d{2}/.test(trimmed) ||
        /^\{/.test(trimmed); // JSON object start
      
      if (!looksLikeNewEntry) {
        parsedLine.timestamp = lastTimestamp;
        parsedLine.timestampLabel = formatTimestampLabel(lastTimestamp);
      }
    }

    parsed.push(parsedLine);
  });
  return parsed;
};

export type LogSearchMode = "exact" | "fuzzy";

export const filterLogLines = (
  lines: ParsedLogLine[],
  searchTerm: string,
  selectedLevel: LogLevel | null,
  searchMode: LogSearchMode = "fuzzy",
): ParsedLogLine[] => {
  const normalizedTerm = searchTerm.trim().toLowerCase();

  return lines.filter((line) => {
    if (selectedLevel && line.level !== selectedLevel) {
      return false;
    }

    if (!normalizedTerm) {
      return true;
    }

    const haystack = `${line.message} ${line.raw} ${line.logger ?? ""}`.toLowerCase();
    if (searchMode === "exact") {
      return haystack.includes(normalizedTerm);
    }

    const tokens = normalizedTerm.split(/\s+/).filter(Boolean);
    return tokens.every((token) => haystack.includes(token));
  });
};

export const getLogLevelBadgeColor = (level: LogLevel) => {
  const config =
    LOG_LEVEL_DEFINITIONS[level] ?? LOG_LEVEL_DEFINITIONS.unknown;
  return {
    label: config.label,
    color: config.color,
  };
};

export const getLogLevelOptions = () =>
  FILTERABLE_LEVELS.map((level) => ({
    label: LOG_LEVEL_DEFINITIONS[level].label,
    value: level,
  }));

export const getLogLevelOptionsForLines = (
  lines: ParsedLogLine[],
): { label: string; value: LogLevel }[] => {
  if (!lines?.length) {
    return [];
  }

  const seenLevels = new Set<LogLevel>();
  lines.forEach((line) => {
    seenLevels.add(line.level);
  });

  return sortLevelsByPriority(Array.from(seenLevels)).map((level) => ({
    label: LOG_LEVEL_DEFINITIONS[level]?.label ?? level.toUpperCase(),
    value: level,
  }));
};

export const matchActionForLogLine = (
  row: ParsedLogLine | null | undefined,
  timelineActions: ActionEntry[],
): ActionEntry | null => {
  if (!row || !timelineActions?.length) {
    return null;
  }

  if (typeof row.actionId === "number") {
    const numericMatch = timelineActions.find(
      (action) =>
        action.sequence_index === row.actionId ||
        Number.parseInt(action.id, 10) === row.actionId,
    );
    if (numericMatch) {
      return numericMatch;
    }
  }

  if (row.timestamp) {
    const rowTime = Date.parse(row.timestamp);
    if (!Number.isNaN(rowTime)) {
      let bestMatchAction: ActionEntry | null = null;
      let bestMatchDiff = Number.POSITIVE_INFINITY;
      timelineActions.forEach((action) => {
        const actionTime = Date.parse(action.timestamp);
        if (Number.isNaN(actionTime)) {
          return;
        }
        const diff = Math.abs(actionTime - rowTime);
        if (diff < bestMatchDiff) {
          bestMatchAction = action;
          bestMatchDiff = diff;
        }
      });
      if (bestMatchAction && bestMatchDiff <= MAX_TIMESTAMP_DIFF_MS) {
        return bestMatchAction;
      }
    }
  }

  const messageLower = row.message.toLowerCase();
  const fallback = timelineActions.find((action) => {
    const nameMatch = action.action_name
      ? messageLower.includes(action.action_name.toLowerCase())
      : false;
    const typeMatch = action.action_type
      ? messageLower.includes(action.action_type.replace(/_/g, " ").toLowerCase())
      : false;
    return nameMatch || typeMatch;
  });

  return fallback ?? null;
};

