import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * Component that handles authentication redirects
 * Must be placed inside a Router context
 */
const AuthRedirectHandler: React.FC = () => {
  const navigate = useNavigate();
  const { shouldRedirectToLogin, clearRedirectFlag, logout } = useAuth();

  useEffect(() => {
    if (shouldRedirectToLogin) {
      console.log('Redirecting to login page...');
      navigate('/login');
      clearRedirectFlag();
    }
  }, [shouldRedirectToLogin, navigate, clearRedirectFlag]);

  useEffect(() => {
    // Listen for logout events from API service
    const handleLogoutRequired = () => {
      console.log('API service requested logout, redirecting to login...');
      logout();
    };

    window.addEventListener('auth-logout-required', handleLogoutRequired);

    return () => {
      window.removeEventListener('auth-logout-required', handleLogoutRequired);
    };
  }, [logout]);

  return null; // This component doesn't render anything
};

export default AuthRedirectHandler;
