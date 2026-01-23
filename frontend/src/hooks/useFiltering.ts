import { useState, useMemo, useCallback } from "react";

export interface FilterCategory<T> {
  key: string;
  label: string;
  options: readonly (string | number)[];
  getValue?: (item: T) => string | number;
}

export type ActiveFilters = Map<string, Set<string | number>>;

const get = (obj: any, path: string) => {
  return path.split(".").reduce((acc, part) => acc && acc[part], obj);
};

export const useFiltering = <T extends object>(
  items: T[],
  filterCategories: FilterCategory<T>[] = [],
) => {
  const [activeFilters, setActiveFilters] = useState<ActiveFilters>(new Map());

  const toggleFilter = useCallback(
    (filterKey: string, value: string | number) => {
      setActiveFilters((prevFilters) => {
        const newFilters = new Map(prevFilters);
        const filterValues = new Set(newFilters.get(filterKey));

        if (filterValues.has(value)) {
          filterValues.delete(value);
        } else {
          filterValues.add(value);
        }

        if (filterValues.size === 0) {
          newFilters.delete(filterKey);
        } else {
          newFilters.set(filterKey, filterValues);
        }

        return newFilters;
      });
    },
    [],
  );

  const clearFilters = useCallback(() => {
    setActiveFilters(new Map());
  }, []);

  const filteredItems = useMemo(() => {
    if (activeFilters.size === 0) {
      return items;
    }

    return items.filter((item) => {
      for (const [key, selectedValues] of activeFilters.entries()) {
        if (selectedValues.size === 0) continue;

        const category = filterCategories.find((c) => c.key === key);
        const itemValue = category?.getValue
          ? category.getValue(item)
          : get(item, key);

        if (itemValue === undefined || !selectedValues.has(itemValue)) {
          return false;
        }
      }
      return true;
    });
  }, [items, activeFilters, filterCategories]);

  return { filteredItems, activeFilters, toggleFilter, clearFilters };
};
