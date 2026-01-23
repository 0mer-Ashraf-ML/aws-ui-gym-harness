import * as Types from '../types';

const API_CONFIG = {
  baseUrl: import.meta.env.VITE_API_URL || "http://localhost:8000",
} as const;

class AuthService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = API_CONFIG.baseUrl;
  }

  /**
   * Authenticate with Google OAuth
   */
  async authenticateWithGoogle(code: string): Promise<Types.AuthToken> {
    const response = await fetch(`${this.baseUrl}/api/v1/auth/google`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code } as Types.GoogleAuthRequest),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Authentication failed');
    }

    return response.json();
  }

  /**
   * Refresh access token using refresh token
   */
  async refreshToken(refreshToken: string): Promise<Types.AuthToken> {
    const response = await fetch(`${this.baseUrl}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Token refresh failed');
    }

    return response.json();
  }

  /**
   * Get current user information
   */
  async getCurrentUser(token: string): Promise<Types.User> {
    const response = await fetch(`${this.baseUrl}/api/v1/auth/me`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Failed to get user information');
    }

    return response.json();
  }

  /**
   * Get all users (admin only)
   */
  async getAllUsers(token: string, skip: number = 0, limit: number = 100): Promise<Types.User[]> {
    const response = await fetch(`${this.baseUrl}/api/v1/auth/users?skip=${skip}&limit=${limit}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Failed to get users');
    }

    return response.json();
  }

  /**
   * Get whitelisted users (admin only)
   */
  async getWhitelistedUsers(token: string, skip: number = 0, limit: number = 100): Promise<Types.User[]> {
    const response = await fetch(`${this.baseUrl}/api/v1/auth/users/whitelisted?skip=${skip}&limit=${limit}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Failed to get whitelisted users');
    }

    return response.json();
  }

  /**
   * Whitelist a user (admin only)
   */
  async whitelistUser(token: string, email: string, isAdmin: boolean = false): Promise<Types.User> {
    const response = await fetch(`${this.baseUrl}/api/v1/auth/whitelist`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, is_admin: isAdmin } as Types.WhitelistRequest),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Failed to whitelist user');
    }

    return response.json();
  }

  /**
   * Remove user from whitelist (admin only)
   */
  async removeFromWhitelist(token: string, email: string): Promise<{ message: string }> {
    const response = await fetch(`${this.baseUrl}/api/v1/auth/whitelist/${encodeURIComponent(email)}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Failed to remove user from whitelist');
    }

    return response.json();
  }
}

// Create and export a singleton instance
export const authService = new AuthService();
