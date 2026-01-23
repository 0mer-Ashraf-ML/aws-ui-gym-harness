import React from 'react';
import { Navigate } from 'react-router-dom';
import { Box, CircularProgress, Typography } from '@mui/material';
import { useAuth } from '../contexts/AuthContext';

/**
 * RoleBasedRedirect Component
 * 
 * This component handles role-based routing for the application's landing page.
 * - Admin users are redirected to /gyms
 * - Regular users are redirected to /tasks
 * 
 * This prevents regular users from landing on admin-only pages and seeing
 * "Access Denied" errors.
 */
const RoleBasedRedirect: React.FC = () => {
  const { isAdmin, isLoading } = useAuth();

  if (isLoading) {
    return (
      <Box
        display="flex"
        flexDirection="column"
        justifyContent="center"
        alignItems="center"
        minHeight="100vh"
        gap={2}
      >
        <CircularProgress />
        <Typography variant="body1">Loading...</Typography>
      </Box>
    );
  }

  // Redirect based on user role
  return <Navigate to={isAdmin ? "/gyms" : "/tasks"} replace />;
};

export default RoleBasedRedirect;

