import { useState, useMemo } from "react";

export type SortDirection = "asc" | "desc";

export interface SortOption<T> {
  value: string;
  label: string;
  getValue?: (item: T) => string | number;
}

export interface SortConfig {
  key: string;
  direction: SortDirection;
}

// Helper to get a nested property value
const get = (obj: any, path: string) => {
  return path.split(".").reduce((acc, part) => acc && acc[part], obj);
};

export const useSorting = <T extends object>(
  items: T[],
  options: SortOption<T>[],
  initialConfig: SortConfig,
) => {
  const [sortConfig, setSortConfig] = useState<SortConfig>(initialConfig);

  const sortedItems = useMemo(() => {
    if (!items) {
      return [];
    }
    const sortableItems = [...items];
    const sortOption = options.find((o) => o.value === sortConfig.key);

    if (sortOption) {
      sortableItems.sort((a, b) => {
        const aValue = sortOption.getValue
          ? sortOption.getValue(a)
          : get(a, sortConfig.key);
        const bValue = sortOption.getValue
          ? sortOption.getValue(b)
          : get(b, sortConfig.key);

        if (aValue < bValue) {
          return sortConfig.direction === "asc" ? -1 : 1;
        }
        if (aValue > bValue) {
          return sortConfig.direction === "asc" ? 1 : -1;
        }
        return 0;
      });
    }
    return sortableItems;
  }, [items, sortConfig, options]);

  const requestSort = (key: string) => {
    let direction: SortDirection = "asc";
    if (sortConfig.key === key && sortConfig.direction === "asc") {
      direction = "desc";
    }
    setSortConfig({ key, direction });
  };

  return { sortedItems, requestSort, sortConfig };
};
