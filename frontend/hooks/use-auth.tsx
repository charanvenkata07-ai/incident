'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import type { User } from '@/types';
import { useRouter, usePathname } from 'next/navigation';

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (
    credentialsOrEmail: string | { email?: string; employee_id?: string; password: string; team_id?: string },
    optionalPassword?: string,
    optionalTeamId?: string
  ) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  isLoading: boolean;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    let active = true;
    const initAuth = async () => {
      let storedToken: string | null = null;
      try {
        if (typeof window !== 'undefined') {
          storedToken = localStorage.getItem('auth_token');
        }
      } catch {
        storedToken = null;
      }

      if (storedToken) {
        if (active) setToken(storedToken);
        apiClient.setToken(storedToken);
        try {
          // Timeout guard: 4000ms max for /api/auth/me during initial boot
          const fetchPromise = apiClient.get<User>('/api/auth/me');
          const timeoutPromise = new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error('Auth request timed out')), 4000)
          );
          const userData = await Promise.race([fetchPromise, timeoutPromise]);
          if (active) setUser(userData);
        } catch (error) {
          try {
            if (typeof window !== 'undefined') {
              localStorage.removeItem('auth_token');
            }
          } catch {}
          if (active) {
            setToken(null);
            setUser(null);
          }
          apiClient.clearToken();
        }
      }
      if (active) setIsLoading(false);
    };

    initAuth();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!isLoading && !user && pathname !== '/login') {
      router.push('/login');
    }
  }, [isLoading, user, pathname, router]);

  const login = async (
    credentialsOrEmail: string | { email?: string; employee_id?: string; password: string; team_id?: string },
    optionalPassword?: string,
    optionalTeamId?: string
  ) => {
    let payload: any = {};
    if (typeof credentialsOrEmail === 'string') {
      payload = { email: credentialsOrEmail, password: optionalPassword };
      if (optionalTeamId) payload.team_id = optionalTeamId;
    } else {
      payload = credentialsOrEmail;
    }

    const response = await apiClient.post<{ access_token: string }>('/api/auth/login', payload);
    const newToken = response.access_token;
    try {
      localStorage.setItem('auth_token', newToken);
    } catch {}
    setToken(newToken);
    apiClient.setToken(newToken);
    const userData = await apiClient.get<User>('/api/auth/me');
    setUser(userData);
    if (userData.role === 'ADMIN') {
      router.push('/admin');
    } else {
      router.push('/dashboard');
    }
  };

  const logout = () => {
    try {
      localStorage.removeItem('auth_token');
    } catch {}
    setToken(null);
    setUser(null);
    apiClient.clearToken();
    router.push('/login');
  };

  const refreshUser = async () => {
    try {
      const userData = await apiClient.get<User>('/api/auth/me');
      setUser(userData);
    } catch {}
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, refreshUser, isLoading, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
