/**
 * Domain management service
 */

import * as Types from '../types';

class DomainService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  }

  /**
   * Get all domains (admin only)
   */
  async getAllDomains(token: string, skip: number = 0, limit: number = 100): Promise<Types.DomainListResponse> {
    const response = await fetch(`${this.baseUrl}/api/v1/domains/?skip=${skip}&limit=${limit}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Failed to get domains');
    }

    return response.json();
  }

  /**
   * Get active domains (admin only)
   */
  async getActiveDomains(token: string): Promise<Types.Domain[]> {
    const response = await fetch(`${this.baseUrl}/api/v1/domains/active`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Failed to get active domains');
    }

    return response.json();
  }

  /**
   * Get domain by ID (admin only)
   */
  async getDomain(token: string, domainId: string): Promise<Types.Domain> {
    const response = await fetch(`${this.baseUrl}/api/v1/domains/${domainId}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Failed to get domain');
    }

    return response.json();
  }

  /**
   * Create a new domain (admin only)
   */
  async createDomain(token: string, domainData: Types.DomainCreateRequest): Promise<Types.Domain> {
    const response = await fetch(`${this.baseUrl}/api/v1/domains/`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(domainData),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Failed to create domain');
    }

    return response.json();
  }

  /**
   * Whitelist a domain (admin only)
   */
  async whitelistDomain(token: string, domain: string): Promise<Types.Domain> {
    const response = await fetch(`${this.baseUrl}/api/v1/domains/whitelist`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ domain }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Failed to whitelist domain');
    }

    return response.json();
  }

  /**
   * Update domain (admin only)
   */
  async updateDomain(token: string, domainId: string, domainData: Types.DomainUpdateRequest): Promise<Types.Domain> {
    const response = await fetch(`${this.baseUrl}/api/v1/domains/${domainId}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(domainData),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(errorData.detail || 'Failed to update domain');
    }

    return response.json();
  }

  /**
   * Delete domain (admin only)
   */
  async deleteDomain(token: string, domainId: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/v1/domains/${domainId}`, {
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
      throw new Error(errorData.detail || 'Failed to delete domain');
    }
  }

  /**
   * Remove domain from whitelist (admin only)
   */
  async removeDomainFromWhitelist(token: string, domain: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/v1/domains/domain/${domain}`, {
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
      throw new Error(errorData.detail || 'Failed to remove domain from whitelist');
    }
  }
}

export const domainService = new DomainService();
