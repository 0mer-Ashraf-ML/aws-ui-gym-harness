import { useState } from "react";

export type ViewMode = "card" | "table";

export interface ViewToggleState {
  view: ViewMode;
  setView: (view: ViewMode) => void;
  toggleView: () => void;
  isCardView: boolean;
  isTableView: boolean;
}

// Convenience hook for managing view state
export const useViewToggle = (initialView: ViewMode = "card"): ViewToggleState => {
  const [view, setView] = useState<ViewMode>(initialView);

  const toggleView = () => {
    setView(prev => prev === "card" ? "table" : "card");
  };

  return {
    view,
    setView,
    toggleView,
    isCardView: view === "card",
    isTableView: view === "table",
  };
};

export default useViewToggle;
