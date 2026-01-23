import React, { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import * as Types from '../types';
import { authService } from '../services/auth';

interface AuthContextType {
  user: Types.User | null;
  token: string | null;
  refreshToken: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
   isUser: boolean;
  login: (authData: Types.AuthToken) => void;
  logout: () => void;
  checkAuth: () => Promise<void>;
  refreshAccessToken: () => Promise<boolean>;
  shouldRedirectToLogin: boolean;
  clearRedirectFlag: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

const TOKEN_COOKIE = 'auth_token';
const REFRESH_TOKEN_COOKIE = 'refresh_token';
const USER_COOKIE = 'user_data';

// Helper functions for cookie management
const setCookie = (name: string, value: string, days: number = 7): void => {
  const expires = new Date();
  expires.setTime(expires.getTime() + (days * 24 * 60 * 60 * 1000));
  document.cookie = `${name}=${value}; expires=${expires.toUTCString()}; path=/`;
};

const getCookie = (name: string): string | null => {
  const nameEQ = name + "=";
  const ca = document.cookie.split(';');
  for (let i = 0; i < ca.length; i++) {
    let c = ca[i];
    while (c.charAt(0) === ' ') c = c.substring(1, c.length);
    if (c.indexOf(nameEQ) === 0) return c.substring(nameEQ.length, c.length);
  }
  return null;
};

const removeCookie = (name: string): void => {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
};

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<Types.User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [shouldRedirectToLogin, setShouldRedirectToLogin] = useState(false);

  // Check if authentication is disabled via environment variable
  const disableAuth = import.meta.env.VITE_DISABLE_AUTH === "true";

  // Create dummy user for auth bypass
  const dummyUser: Types.User = {
    uuid: "dummy-user-uuid",
    email: "dummy@auth-bypass.example.com",
    name: "Dummy User (Auth Bypass)",
    picture: undefined,
    is_admin: true,
    is_whitelisted: true,
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    last_login: new Date().toISOString(),
    role: "admin",
  };

  const isAuthenticated = disableAuth || (!!user && !!token);
  const isAdmin = disableAuth || (user?.role === "admin" || user?.is_admin || false);
  const isUser = disableAuth || (user?.role === "user" || (!user?.is_admin && !!user));

  // Initialize auth state from cookies
  useEffect(() => {
    const initializeAuth = () => {
      if (disableAuth) {
        // Set dummy user when auth is disabled
        setUser(dummyUser);
        setToken("dummy-token");
        setRefreshToken("dummy-refresh-token");
        console.log("🔓 Authentication bypass enabled - using dummy user");
      } else {
        // Normal authentication flow
        const savedToken = getCookie(TOKEN_COOKIE);
        const savedRefreshToken = getCookie(REFRESH_TOKEN_COOKIE);
        const savedUser = getCookie(USER_COOKIE);

        if (savedToken && savedRefreshToken && savedUser) {
          try {
            const userData = JSON.parse(savedUser);
            setToken(savedToken);
            setRefreshToken(savedRefreshToken);
            setUser(userData);
          } catch (error) {
            console.error('Error parsing saved user data:', error);
            // Clear invalid cookies
            removeCookie(TOKEN_COOKIE);
            removeCookie(REFRESH_TOKEN_COOKIE);
            removeCookie(USER_COOKIE);
          }
        }
      }
      setIsLoading(false);
    };

    initializeAuth();
  }, [disableAuth]);

  const login = (authData: Types.AuthToken) => {
    setToken(authData.access_token);
    setRefreshToken(authData.refresh_token);
    setUser(authData.user);
    
    // Save to cookies (expires in 7 days)
    setCookie(TOKEN_COOKIE, authData.access_token, 7);
    setCookie(REFRESH_TOKEN_COOKIE, authData.refresh_token, 7);
    setCookie(USER_COOKIE, JSON.stringify(authData.user), 7);
  };

  const logout = () => {
    setToken(null);
    setRefreshToken(null);
    setUser(null);
    
    // Clear cookies
    removeCookie(TOKEN_COOKIE);
    removeCookie(REFRESH_TOKEN_COOKIE);
    removeCookie(USER_COOKIE);
    
    // Set flag to trigger redirect
    setShouldRedirectToLogin(true);
  };

  const clearRedirectFlag = () => {
    setShouldRedirectToLogin(false);
  };

  const refreshAccessToken = async (): Promise<boolean> => {
    if (!refreshToken) {
      console.warn('No refresh token available, redirecting to login');
      logout();
      return false;
    }

    try {
      const authData = await authService.refreshToken(refreshToken);
      setToken(authData.access_token);
      setRefreshToken(authData.refresh_token);
      setUser(authData.user);
      
      // Update cookies
      setCookie(TOKEN_COOKIE, authData.access_token, 7);
      setCookie(REFRESH_TOKEN_COOKIE, authData.refresh_token, 7);
      setCookie(USER_COOKIE, JSON.stringify(authData.user), 7);
      
      console.log('Token refreshed successfully');
      return true;
    } catch (error) {
      console.error('Error refreshing token:', error);
      console.log('Refresh token failed, redirecting to login');
      logout();
      return false;
    }
  };

  const checkAuth = async () => {
    if (disableAuth) {
      // Skip authentication check when auth is disabled
      console.log('🔓 Authentication bypass enabled - skipping auth check');
      setIsLoading(false);
      return;
    }

    if (!token) {
      console.log('No access token available, redirecting to login');
      logout();
      return;
    }

    try {
      const response = await fetch('/api/v1/auth/me', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
        setCookie(USER_COOKIE, JSON.stringify(userData), 7);
      } else if (response.status === 401) {
        // Token expired, try to refresh
        console.log('Access token expired, attempting to refresh');
        const refreshed = await refreshAccessToken();
        if (!refreshed) {
          console.log('Token refresh failed, redirecting to login');
          logout();
        }
      } else {
        // Other error (403, 500, etc.), logout
        console.error(`Auth check failed with status ${response.status}, redirecting to login`);
        logout();
      }
    } catch (error) {
      console.error('Error checking auth:', error);
      console.log('Network error during auth check, redirecting to login');
      logout();
    } finally {
      setIsLoading(false);
    }
  };

  const value: AuthContextType = {
    user: disableAuth ? dummyUser : user,
    token,
    refreshToken,
    isLoading,
    isAuthenticated,
    isAdmin,
    isUser,
    login,
    logout,
    checkAuth,
    refreshAccessToken,
    shouldRedirectToLogin,
    clearRedirectFlag,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
