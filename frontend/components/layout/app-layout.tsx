'use client';

import * as React from 'react';
import { Sidebar } from './sidebar';
import { Header } from './header';
import { MobileNav } from './mobile-nav';
import { useAuth } from '@/hooks/use-auth';
import { useWebSocket } from '@/hooks/use-websocket';
import { SearchProvider } from '@/context/search-context';

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const [mounted, setMounted] = React.useState(false);
  const [loadingTimedOut, setLoadingTimedOut] = React.useState(false);
  useWebSocket(); // Initialize WS connection

  React.useEffect(() => {
    setMounted(true);
    const timer = setTimeout(() => {
      setLoadingTimedOut(true);
    }, 4500);
    return () => clearTimeout(timer);
  }, []);

  if (!mounted || isLoading) {
    if (loadingTimedOut) {
      return (
        <div className="flex flex-col h-screen items-center justify-center bg-zinc-50 dark:bg-[#020817] text-zinc-900 dark:text-zinc-100 p-6">
          <div className="max-w-md w-full text-center space-y-4 bg-white dark:bg-[#071426] p-8 rounded-2xl border border-zinc-200 dark:border-white/10 shadow-lg">
            <div className="w-12 h-12 rounded-xl bg-amber-500/10 text-amber-500 flex items-center justify-center mx-auto text-xl font-bold">
              !
            </div>
            <h2 className="text-lg font-bold text-zinc-900 dark:text-white">Connecting to IncidentFlow</h2>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Loading is taking longer than expected. Please check your network or sign in again.
            </p>
            <div className="flex items-center justify-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="px-4 py-2 text-xs font-semibold bg-[#087CFF] hover:bg-blue-600 text-white rounded-lg transition-colors"
              >
                Refresh Page
              </button>
              <button
                type="button"
                onClick={() => {
                  try { localStorage.removeItem('auth_token'); } catch {}
                  window.location.href = '/login';
                }}
                className="px-4 py-2 text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white rounded-lg hover:bg-zinc-100 dark:hover:bg-white/5 transition-colors"
              >
                Sign In Again
              </button>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="flex h-screen items-center justify-center bg-zinc-50 dark:bg-[#020817] text-zinc-900 dark:text-zinc-100">
        <div className="text-center space-y-3">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#087CFF] mx-auto" />
          <p className="text-xs text-zinc-400 font-medium tracking-wide">Loading IncidentFlow...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col h-screen items-center justify-center bg-zinc-50 dark:bg-[#020817] text-zinc-900 dark:text-zinc-100 p-6">
        <div className="text-center space-y-3">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#087CFF] mx-auto" />
          <p className="text-xs text-zinc-400">Redirecting to login...</p>
        </div>
      </div>
    );
  }

  return (
    <SearchProvider>
      <div className="flex h-screen overflow-hidden bg-zinc-50 text-zinc-900">
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <Header />
          <main className="flex-1 overflow-y-auto p-4 md:p-6 pb-20 md:pb-6">
            {children}
          </main>
        </div>
        <MobileNav />
      </div>
    </SearchProvider>
  );
}
