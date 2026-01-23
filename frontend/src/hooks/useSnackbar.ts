import { useState, useCallback } from 'react';

export type SnackbarSeverity = 'success' | 'error' | 'warning' | 'info';

export interface SnackbarState {
  open: boolean;
  message: string;
  severity: SnackbarSeverity;
}

export interface UseSnackbarReturn {
  snackbar: SnackbarState;
  showSnackbar: (message: string, severity?: SnackbarSeverity) => void;
  showSuccess: (message: string) => void;
  showError: (message: string) => void;
  showWarning: (message: string) => void;
  showInfo: (message: string) => void;
  hideSnackbar: () => void;
}

const DEFAULT_SNACKBAR_STATE: SnackbarState = {
  open: false,
  message: '',
  severity: 'info',
};

/**
 * Custom hook for managing snackbar notifications
 * Provides easy-to-use methods for showing different types of notifications
 */
export const useSnackbar = (): UseSnackbarReturn => {
  const [snackbar, setSnackbar] = useState<SnackbarState>(DEFAULT_SNACKBAR_STATE);

  const showSnackbar = useCallback((message: string, severity: SnackbarSeverity = 'info') => {
    setSnackbar({
      open: true,
      message,
      severity,
    });
  }, []);

  const showSuccess = useCallback((message: string) => {
    showSnackbar(message, 'success');
  }, [showSnackbar]);

  const showError = useCallback((message: string) => {
    showSnackbar(message, 'error');
  }, [showSnackbar]);

  const showWarning = useCallback((message: string) => {
    showSnackbar(message, 'warning');
  }, [showSnackbar]);

  const showInfo = useCallback((message: string) => {
    showSnackbar(message, 'info');
  }, [showSnackbar]);

  const hideSnackbar = useCallback(() => {
    setSnackbar(prev => ({
      ...prev,
      open: false,
    }));
  }, []);

  return {
    snackbar,
    showSnackbar,
    showSuccess,
    showError,
    showWarning,
    showInfo,
    hideSnackbar,
  };
};

// Predefined CRUD operation messages
export const CRUD_MESSAGES = {
  // Create operations
  CREATE_SUCCESS: {
    gym: 'Gym created successfully',
    task: 'Task created successfully',
    model: 'Model created successfully',
    execution: 'Execution created successfully',
    run: 'Run created successfully',
  },
  CREATE_ERROR: {
    gym: 'Failed to create gym',
    task: 'Failed to create task',
    model: 'Failed to create model',
    execution: 'Failed to create execution',
    run: 'Failed to create run',
  },

  // Update operations
  UPDATE_SUCCESS: {
    gym: 'Gym updated successfully',
    task: 'Task updated successfully',
    model: 'Model updated successfully',
    execution: 'Execution updated successfully',
    run: 'Run updated successfully',
  },
  UPDATE_ERROR: {
    gym: 'Failed to update gym',
    task: 'Failed to update task',
    model: 'Failed to update model',
    execution: 'Failed to update execution',
    run: 'Failed to update run',
  },

  // Delete operations
  DELETE_SUCCESS: {
    gym: 'Gym deleted successfully',
    task: 'Task deleted successfully',
    model: 'Model deleted successfully',
    execution: 'Execution deleted successfully',
    run: 'Run deleted successfully',
  },
  DELETE_ERROR: {
    gym: 'Failed to delete gym',
    task: 'Failed to delete task',
    model: 'Failed to delete model',
    execution: 'Failed to delete execution',
    run: 'Failed to delete run',
  },

  // Execute operations
  EXECUTE_SUCCESS: {
    run: 'Run executed successfully',
    task: 'Task executed successfully',
  },
  EXECUTE_ERROR: {
    run: 'Failed to execute run',
    task: 'Failed to execute task',
  },
} as const;

// Helper type for entity names
export type EntityType = 'gym' | 'task' | 'model' | 'execution' | 'run';

/**
 * Helper functions to get standardized CRUD messages
 */
export const getCrudMessage = (
  operation: 'create' | 'update' | 'delete' | 'execute',
  status: 'success' | 'error',
  entity: EntityType
): string => {
  const messageKey = `${operation.toUpperCase()}_${status.toUpperCase()}` as keyof typeof CRUD_MESSAGES;
  const messages = CRUD_MESSAGES[messageKey] as Record<EntityType, string>;
  return messages[entity];
};
