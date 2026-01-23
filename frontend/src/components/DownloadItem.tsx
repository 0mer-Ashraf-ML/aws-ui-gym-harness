/**
 * Individual download item component
 * Shows progress, speed, ETA, and cancel button
 */

import React from 'react';
import {
  Box,
  LinearProgress,
  Typography,
  IconButton,
  Chip,
  Tooltip,
} from '@mui/material';
import {
  Cancel as CancelIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  CancelOutlined as CancelledIcon,
} from '@mui/icons-material';
import type { DownloadItem as DownloadItemType } from '../types/download';
import { formatSpeed, formatETA, formatBytes } from '../services/downloadService';

interface DownloadItemProps {
  download: DownloadItemType;
  onCancel: (id: string) => void;
  onRemove: (id: string) => void;
}

export const DownloadItem: React.FC<DownloadItemProps> = ({
  download,
  onCancel,
  onRemove,
}) => {
  const isActive = download.status === 'pending' || download.status === 'downloading';
  const isCompleted = download.status === 'completed';
  const isFailed = download.status === 'failed';
  const isCancelled = download.status === 'cancelled';

  const getStatusIcon = () => {
    if (isCompleted) {
      return <CheckCircleIcon sx={{ color: 'success.main', fontSize: 20 }} />;
    }
    if (isFailed) {
      return <ErrorIcon sx={{ color: 'error.main', fontSize: 20 }} />;
    }
    if (isCancelled) {
      return <CancelledIcon sx={{ color: 'text.secondary', fontSize: 20 }} />;
    }
    return null;
  };

  const getStatusColor = (): 'default' | 'primary' | 'success' | 'error' | 'warning' => {
    if (isCompleted) return 'success';
    if (isFailed) return 'error';
    if (isCancelled) return 'default';
    return 'primary';
  };

  return (
    <Box
      sx={{
        p: 1.5,
        borderBottom: '1px solid',
        borderColor: 'divider',
        '&:last-child': {
          borderBottom: 'none',
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
        {/* Status Icon */}
        {getStatusIcon() && (
          <Box sx={{ mt: 0.5 }}>{getStatusIcon()}</Box>
        )}

        {/* Content */}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {/* Filename */}
          <Tooltip title={download.filename}>
            <Typography
              variant="body2"
              sx={{
                fontWeight: 500,
                mb: 0.5,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {download.filename}
            </Typography>
          </Tooltip>

          {/* Progress Bar */}
          {isActive && (
            <Box sx={{ mb: 1 }}>
              <LinearProgress
                variant="determinate"
                value={download.progress}
                sx={{
                  height: 6,
                  borderRadius: 1,
                  backgroundColor: 'action.hover',
                  '& .MuiLinearProgress-bar': {
                    borderRadius: 1,
                  },
                }}
              />
            </Box>
          )}

          {/* Status Info */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            {/* Progress Percentage */}
            {isActive && (
              <Chip
                label={`${download.progress}%`}
                size="small"
                color={getStatusColor()}
                sx={{ height: 20, fontSize: '0.7rem' }}
              />
            )}

            {/* Download Speed */}
            {isActive && download.speed > 0 && (
              <Typography variant="caption" color="text.secondary">
                {formatSpeed(download.speed)}
              </Typography>
            )}

            {/* ETA */}
            {isActive && download.eta > 0 && (
              <Typography variant="caption" color="text.secondary">
                {formatETA(download.eta)}
              </Typography>
            )}

            {/* File Size */}
            {download.totalBytes && (
              <Typography variant="caption" color="text.secondary">
                {formatBytes(download.totalBytes)}
              </Typography>
            )}

            {/* Error Message */}
            {isFailed && download.error && (
              <Typography variant="caption" color="error.main">
                {download.error}
              </Typography>
            )}

            {/* Status Chip */}
            {!isActive && (
              <Chip
                label={download.status.charAt(0).toUpperCase() + download.status.slice(1)}
                size="small"
                color={getStatusColor()}
                sx={{ height: 20, fontSize: '0.7rem' }}
              />
            )}
          </Box>
        </Box>

        {/* Actions */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          {isActive && (
            <Tooltip title="Cancel download">
              <IconButton
                size="small"
                onClick={() => onCancel(download.id)}
                sx={{ color: 'text.secondary' }}
              >
                <CancelIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {!isActive && (
            <Tooltip title="Remove from list">
              <IconButton
                size="small"
                onClick={() => onRemove(download.id)}
                sx={{ color: 'text.secondary' }}
              >
                <CancelIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Box>
      </Box>
    </Box>
  );
};
