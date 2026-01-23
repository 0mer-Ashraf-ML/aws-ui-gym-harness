import React, { useEffect, useState } from 'react';
import { Box, Typography, Alert, CircularProgress } from '@mui/material';
import { useAuth } from '../contexts/AuthContext';
import { authService } from '../services/auth';

interface GoogleSignInProps {
  onSuccess?: () => void;
  onError?: (error: string) => void;
}

declare global {
  interface Window {
    google: any;
  }
}

const GoogleSignIn: React.FC<GoogleSignInProps> = ({ onSuccess, onError }) => {
  const { login } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isGoogleLoaded, setIsGoogleLoaded] = useState(false);

  useEffect(() => {
    // Load Google Identity Services (the new library)
    const loadGoogleScript = () => {
      if (window.google) {
        setIsGoogleLoaded(true);
        return;
      }

      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.defer = true;
      script.onload = () => {
        setIsGoogleLoaded(true);
      };
      script.onerror = () => {
        setError('Failed to load Google Sign-In');
      };
      document.head.appendChild(script);
    };

    loadGoogleScript();
  }, []);

  useEffect(() => {
    if (!isGoogleLoaded || !window.google) return;

    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    console.log('Google Client ID:', clientId);

    // Initialize Google Identity Services
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: handleCredentialResponse,
      auto_select: false,
      cancel_on_tap_outside: false,
    });
    
    console.log('Google Identity Services initialized');
    
    // Render the Google Sign-In button immediately
    const buttonContainer = document.getElementById('google-signin-button');
    if (buttonContainer) {
      buttonContainer.innerHTML = ''; // Clear any existing content
      
      window.google.accounts.id.renderButton(buttonContainer, {
        theme: 'outline',
        size: 'large',
        width: '100%',
        text: 'signin_with',
        shape: 'rectangular',
        logo_alignment: 'left'
      });
      
      console.log('Google Sign-In button rendered');
    }
  }, [isGoogleLoaded]);

  const handleCredentialResponse = async (response: any) => {
    console.log('Google credential response received:', response);
    setIsLoading(true);
    setError(null);

    try {
      // Send the credential to our backend
      console.log('Sending credential to backend...');
      const authData = await authService.authenticateWithGoogle(response.credential);
      console.log('Backend authentication successful:', authData);
      
      // Login the user
      login(authData);
      
      onSuccess?.();
    } catch (err) {
      console.error('Authentication error:', err);
      let errorMessage = err instanceof Error ? err.message : 'Authentication failed';
      
      // Enhance error message for whitelist-related errors
      if (errorMessage.toLowerCase().includes('whitelist') || 
          errorMessage.toLowerCase().includes('access denied')) {
        errorMessage = errorMessage; // Use the server's detailed message
      } else if (errorMessage.toLowerCase().includes('403') || 
                 errorMessage.toLowerCase().includes('forbidden')) {
        errorMessage = 'Access denied. Your email is not whitelisted. Please contact an administrator to request access.';
      }
      
      setError(errorMessage);
      onError?.(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };


  if (!isGoogleLoaded) {
    return (
      <Box display="flex" alignItems="center" gap={2}>
        <CircularProgress size={20} />
        <Typography>Loading Google Sign-In...</Typography>
      </Box>
    );
  }

  return (
    <Box>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      
      {isLoading && (
        <Box display="flex" alignItems="center" justifyContent="center" sx={{ mb: 2 }}>
          <CircularProgress size={20} sx={{ mr: 1 }} />
          <Typography>Signing in...</Typography>
        </Box>
      )}
      
      <Box id="google-signin-button" sx={{ width: '100%' }} />
    </Box>
  );
};

export default GoogleSignIn;