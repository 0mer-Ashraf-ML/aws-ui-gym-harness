/**
 * Download Manager Component
 * Persistent download queue UI similar to Google Drive
 * Shows active and completed downloads with progress tracking
 */

import React, { useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  IconButton,
  Collapse,
  Divider,
  Button,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Close as CloseIcon,
  Download as DownloadIcon,
} from '@mui/icons-material';
import { DownloadItem } from './DownloadItem';
import { useDownloadQueue } from '../hooks/useDownloadQueue';

export const DownloadManager: React.FC = () => {
  const {
    downloads,
    activeDownloads,
    completedDownloads,
    cancelDownload,
    removeDownload,
    clearCompleted,
  } = useDownloadQueue();

  const [expanded, setExpanded] = useState(true);
  const [minimized, setMinimized] = useState(false);

  // Don't show if no downloads
  if (downloads.length === 0) {
    return null;
  }

  const hasActiveDownloads = activeDownloads.length > 0;
  const hasCompletedDownloads = completedDownloads.length > 0;

  return (
    <Paper
      elevation={8}
      sx={{
        position: 'fixed',
        bottom: minimized ? 16 : 16,
        right: 16,
        width: minimized ? 56 : 400,
        maxWidth: 'calc(100vw - 32px)',
        maxHeight: minimized ? 56 : '70vh',
        zIndex: 1300, // Above modals
        transition: 'all 0.3s ease-in-out',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          p: 1.5,
          bgcolor: 'primary.main',
          color: 'primary.contrastText',
          cursor: minimized ? 'pointer' : 'default',
          minHeight: 56,
        }}
        onClick={() => minimized && setMinimized(false)}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <DownloadIcon />
          {!minimized && (
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Downloads
              {hasActiveDownloads && (
                <Typography
                  component="span"
                  sx={{ ml: 1, opacity: 0.9, fontSize: '0.85rem' }}
                >
                  ({activeDownloads.length} active)
                </Typography>
              )}
            </Typography>
          )}
        </Box>

        {!minimized && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            {hasCompletedDownloads && (
              <Button
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  clearCompleted();
                }}
                sx={{
                  color: 'primary.contrastText',
                  minWidth: 'auto',
                  px: 1,
                  fontSize: '0.75rem',
                }}
              >
                Clear
              </Button>
            )}
            {downloads.length > 1 && (
              <IconButton
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  setExpanded(!expanded);
                }}
                sx={{ color: 'primary.contrastText' }}
              >
                {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              </IconButton>
            )}
            {hasActiveDownloads && (
              <IconButton
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  setMinimized(true);
                }}
                sx={{ color: 'primary.contrastText' }}
              >
                <CloseIcon />
              </IconButton>
            )}
          </Box>
        )}
      </Box>

      {/* Content */}
      {!minimized && (
        <Box
          sx={{
            flex: 1,
            overflow: 'auto',
            bgcolor: 'background.paper',
            maxHeight: expanded ? 'calc(70vh - 56px)' : 200,
            transition: 'max-height 0.3s ease-in-out',
          }}
        >
          {/* Active Downloads */}
          {hasActiveDownloads && (
            <>
              {activeDownloads.map((download) => (
                <DownloadItem
                  key={download.id}
                  download={download}
                  onCancel={cancelDownload}
                  onRemove={removeDownload}
                />
              ))}
              {hasCompletedDownloads && <Divider />}
            </>
          )}

          {/* Completed Downloads */}
          {hasCompletedDownloads && (
            <Collapse in={expanded || !hasActiveDownloads}>
              {completedDownloads.map((download) => (
                <DownloadItem
                  key={download.id}
                  download={download}
                  onCancel={cancelDownload}
                  onRemove={removeDownload}
                />
              ))}
            </Collapse>
          )}

          {/* Empty State (shouldn't show, but just in case) */}
          {downloads.length === 0 && (
            <Box sx={{ p: 3, textAlign: 'center' }}>
              <Typography variant="body2" color="text.secondary">
                No downloads
              </Typography>
            </Box>
          )}
        </Box>
      )}

      {/* Minimized Badge */}
      {minimized && hasActiveDownloads && (
        <Box
          sx={{
            position: 'absolute',
            top: -8,
            right: -8,
            bgcolor: 'error.main',
            color: 'error.contrastText',
            borderRadius: '50%',
            width: 24,
            height: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '0.75rem',
            fontWeight: 600,
            border: '2px solid',
            borderColor: 'background.paper',
          }}
        >
          {activeDownloads.length}
        </Box>
      )}
    </Paper>
  );
};
