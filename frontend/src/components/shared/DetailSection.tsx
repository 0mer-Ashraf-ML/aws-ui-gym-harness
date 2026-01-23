import React from "react";
import { Box, Typography, Divider } from "@mui/material";
import type { BoxProps } from "@mui/material";

interface DetailSectionProps {
  title?: string;
  children: React.ReactNode;
  showDivider?: boolean;
  sx?: BoxProps["sx"];
}

interface DetailFieldProps {
  label: string;
  value: React.ReactNode;
  fullWidth?: boolean;
  sx?: BoxProps["sx"];
}

interface DetailFieldsProps {
  children: React.ReactNode;
  columns?: 1 | 2;
  sx?: BoxProps["sx"];
}

// Main section component
export function DetailSection({
  title,
  children,
  showDivider = true,
  sx,
}: DetailSectionProps) {
  return (
    <Box sx={sx}>
      {title && (
        <Typography
          variant="subtitle1"
          gutterBottom
          sx={{ fontWeight: 600, mb: showDivider ? 1 : 2 }}
        >
          {title}
        </Typography>
      )}
      {showDivider && title && <Divider sx={{ mb: 2 }} />}
      {children}
    </Box>
  );
}

// Container for multiple fields with responsive layout
export function DetailFields({ children, columns = 2, sx }: DetailFieldsProps) {
  return (
    <Box
      sx={{
        display: "flex",
        flexWrap: "wrap",
        gap: 2,
        ...sx,
      }}
    >
      {React.Children.map(children, (child) => {
        if (React.isValidElement(child) && child.type === DetailField) {
          return React.cloneElement(
            child as React.ReactElement<DetailFieldProps>,
            {
              fullWidth:
                columns === 1 || (child.props as DetailFieldProps).fullWidth,
            },
          );
        }
        return child;
      })}
    </Box>
  );
}

// Individual field component
export function DetailField({
  label,
  value,
  fullWidth = false,
  sx,
}: DetailFieldProps) {
  return (
    <Box
      sx={{
        flex: fullWidth ? "1 1 100%" : { xs: "1 1 100%", sm: "1 1 45%" },
        ...sx,
      }}
    >
      <Typography variant="subtitle2" color="text.secondary" gutterBottom>
        {label}
      </Typography>
      <Box>
        {typeof value === "string" ? (
          <Typography variant="body1">{value}</Typography>
        ) : (
          value
        )}
      </Box>
    </Box>
  );
}

// Container for the entire detail modal content
export function DetailContent({ children }: { children: React.ReactNode }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      {children}
    </Box>
  );
}

// Header section with title and description
export function DetailHeader({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <>
      <Box>
        <Typography variant="h5" gutterBottom>
          {title}
        </Typography>
        {description && (
          <Typography variant="body1" color="text.secondary" paragraph>
            {description}
          </Typography>
        )}
      </Box>
      <Divider />
    </>
  );
}

// Timestamps section (common pattern)
export function DetailTimestamps({
  createdAt,
  updatedAt,
}: {
  createdAt?: string;
  updatedAt?: string;
}) {
  const formatDate = (dateString?: string) => {
    if (!dateString) return "Unknown";
    const date = new Date(dateString);
    return `${date.toLocaleDateString()} at ${date.toLocaleTimeString()}`;
  };

  return (
    <DetailSection>
      <DetailFields>
        <DetailField label="Created" value={formatDate(createdAt)} />
        <DetailField label="Last Updated" value={formatDate(updatedAt)} />
      </DetailFields>
    </DetailSection>
  );
}

export default DetailSection;
