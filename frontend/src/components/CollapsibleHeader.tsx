import { Box } from "@mui/material";
import type { ReactNode, RefObject } from "react";

interface CollapsibleHeaderProps {
  isScrolled: boolean;
  headerRef: RefObject<HTMLDivElement | null>;
  children: ReactNode;
}

export default function CollapsibleHeader({
  isScrolled,
  headerRef,
  children,
}: CollapsibleHeaderProps) {
  return (
    <Box
      ref={headerRef}
      sx={{
        transform: isScrolled ? "translateY(-100%)" : "translateY(0)",
        opacity: isScrolled ? 0 : 1,
        transition: "transform 0.2s ease-in-out, opacity 0.2s ease-in-out",
        height: isScrolled ? 0 : "auto",
        overflow: isScrolled ? "hidden" : "visible",
      }}
    >
      {children}
    </Box>
  );
}

