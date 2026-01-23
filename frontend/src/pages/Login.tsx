import React, { useEffect } from 'react';
import { Box, Container, Paper, Typography, Alert } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import GoogleSignIn from '../components/GoogleSignIn';
import { useAuth } from '../contexts/AuthContext';

const Login: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated && !isLoading) {
      navigate('/');
    }
  }, [isAuthenticated, isLoading, navigate]);

  const handleLoginSuccess = () => {
    navigate('/');
  };

  const handleLoginError = (error: string) => {
    console.error('Login error:', error);
  };

  if (isLoading) {
    return (
      <Container maxWidth="sm">
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight="100vh"
        >
          <Typography>Loading...</Typography>
        </Box>
      </Container>
    );
  }

  if (isAuthenticated) {
    return null; // Will redirect via useEffect
  }

  return (
    <Container maxWidth="sm">
      <Box
        display="flex"
        justifyContent="center"
        alignItems="center"
        minHeight="100vh"
      >
        <Paper
          elevation={3}
          sx={{
            p: 4,
            width: '100%',
            maxWidth: 400,
            textAlign: 'center',
          }}
        >
          <Typography variant="h4" component="h1" gutterBottom>
            RL Gym Harness
          </Typography>
          
          <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
            Sign in to access the task execution system
          </Typography>

          <Alert severity="warning" sx={{ mb: 3, textAlign: 'left' }}>
            <Typography variant="body2">
              <strong>Access Restricted:</strong> Only whitelisted users can log in. 
              If you don't have access, please contact your administrator to be added to the whitelist.
            </Typography>
          </Alert>

          <GoogleSignIn
            onSuccess={handleLoginSuccess}
            onError={handleLoginError}
          />
        </Paper>
      </Box>
    </Container>
  );
};

export default Login;
