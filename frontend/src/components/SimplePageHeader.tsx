import type { ReactNode } from "react";
import { Box, Typography } from "@mui/material";

interface SimplePageHeaderProps {
  icon: ReactNode;
  title: string;
  description: string;
}

export default function SimplePageHeader({
  icon,
  title,
  description,
}: SimplePageHeaderProps) {
  return (
    <Box sx={{ mb: 6 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
        {icon}
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            {title}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            {description}
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}
