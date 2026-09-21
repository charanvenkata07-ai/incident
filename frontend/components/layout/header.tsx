'use client';

import * as React from 'react';
import { Bell, Menu, HelpCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { useAuth } from '@/hooks/use-auth';
import { useRouter } from 'next/navigation';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator } from '../ui/dropdown-menu';
import { Avatar, AvatarFallback } from '../ui/avatar';
import { useNotifications } from '@/hooks/use-notifications';
import Link from 'next/link';

import { wsClient, ConnectionState } from '@/lib/websocket';
import { apiClient } from '@/lib/api-client';
import { AvatarImage } from '../ui/avatar';
import { GlobalSearchBar } from '../search/global-search-bar';
import { CommandPalette } from '../search/command-palette';

export function Header() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const { data: notifications } = useNotifications();
  const unreadCount = Array.isArray(notifications) ? notifications.filter(n => n && !n.is_read).length : 0;
  const [wsState, setWsState] = React.useState<ConnectionState>(wsClient.getState());

  React.useEffect(() => {
    return wsClient.onStateChange((state) => {
      setWsState(state);
    });
  }, []);

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd + / or Ctrl + / opens Help Center
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault();
        router.push('/admin/help');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [router]);

  const stateInfo = {
    CONNECTED: { label: 'Connected', color: 'bg-emerald-500', text: 'text-emerald-700 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800' },
    CONNECTING: { label: 'Connecting...', color: 'bg-blue-500 animate-pulse', text: 'text-blue-700 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800' },
    RECONNECTING: { label: 'Reconnecting...', color: 'bg-amber-500 animate-pulse', text: 'text-amber-700 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800' },
    DISCONNECTED: { label: 'Offline', color: 'bg-zinc-400', text: 'text-zinc-600 dark:text-zinc-400', bg: 'bg-zinc-50 dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800' }
  }[wsState] || { label: 'Offline', color: 'bg-zinc-400', text: 'text-zinc-600', bg: 'bg-zinc-50' };

  return (
    <header className="h-16 border-b border-black/[0.08] dark:border-white/[0.08] bg-white/80 dark:bg-[#071426]/80 backdrop-blur-xl text-zinc-900 dark:text-zinc-100 flex items-center justify-between px-4 md:px-6 sticky top-0 z-40 transition-colors">
      <div className="flex items-center space-x-2.5 md:hidden">
        <img src="/brand/incidentflow-mark.png" alt="IncidentFlow" className="h-7 w-7 object-contain shrink-0" />
        <span className="font-bold text-[#071A33] dark:text-white tracking-tight">IncidentFlow</span>
      </div>
      <div className="hidden md:flex items-center space-x-3">
        {/* Real-time connection badge */}
        <div className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${stateInfo.bg} ${stateInfo.text}`} title={`WebSocket: ${wsClient.getWsUrl()}`}>
          <span className={`h-2 w-2 rounded-full ${stateInfo.color}`} />
          <span>{stateInfo.label}</span>
        </div>
      </div>

      {/* Global Present-Page Search Bar */}
      <div className="flex-1 flex items-center justify-center px-2 md:px-6 max-w-xl">
        <GlobalSearchBar />
      </div>

      <div className="flex items-center space-x-2 md:space-x-3">
        {/* Help Center Shortcut & Button */}
        {(user?.role === 'ADMIN' || user?.role === 'SUPERVISOR') && (
          <Button variant="ghost" size="icon" asChild className="relative rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800" title="Help Center (⌘ /)">
            <Link href="/admin/help">
              <HelpCircle className="h-5 w-5 text-zinc-700 dark:text-zinc-200" />
            </Link>
          </Button>
        )}

        <Button variant="ghost" size="icon" asChild className="relative rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800">
          <Link href="/employee/notifications" title="Notifications">
            <Bell className="h-5 w-5 text-zinc-700 dark:text-zinc-200" />
            {unreadCount > 0 && (
              <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-red-500 animate-pulse" />
            )}
          </Link>
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="relative h-9 w-9 rounded-full p-0 ring-1 ring-black/[0.08] dark:ring-white/[0.1] hover:ring-2 hover:ring-[#087CFF] transition-all">
              <Avatar className="h-9 w-9">
                {user?.avatar_url && (
                  <AvatarImage src={apiClient.getMediaUrl(user.avatar_url)} alt={user.full_name} />
                )}
                <AvatarFallback className="bg-blue-100 text-[#087CFF] dark:bg-blue-950 dark:text-[#149BFF] font-semibold text-xs">
                  {user?.full_name?.charAt(0) || 'U'}
                </AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56 rounded-2xl p-1.5 shadow-xl border-black/[0.08] dark:border-white/[0.08]">
            <DropdownMenuLabel className="px-3 py-2">
              <div className="flex flex-col space-y-0.5">
                <p className="text-sm font-semibold leading-none text-zinc-900 dark:text-zinc-100">{user?.full_name}</p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">{user?.email}</p>
                <div className="pt-1">
                  <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-50 text-[#087CFF] dark:bg-blue-950 dark:text-[#149BFF]">
                    {user?.role}
                  </span>
                </div>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="my-1" />
            <DropdownMenuItem asChild className="rounded-xl cursor-pointer">
              <Link href="/employee/profile">Profile & Settings</Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator className="my-1" />
            <DropdownMenuItem onClick={logout} className="rounded-xl text-red-600 dark:text-red-400 cursor-pointer focus:bg-red-50 dark:focus:bg-red-950/40">
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <CommandPalette />
    </header>
  );
}
