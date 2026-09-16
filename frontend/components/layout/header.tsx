'use client';

import * as React from 'react';
import { Bell, Menu } from 'lucide-react';
import { Button } from '../ui/button';
import { useAuth } from '@/hooks/use-auth';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator } from '../ui/dropdown-menu';
import { Avatar, AvatarFallback } from '../ui/avatar';
import { useNotifications } from '@/hooks/use-notifications';
import Link from 'next/link';

export function Header() {
  const { user, logout } = useAuth();
  const { data: notifications } = useNotifications();
  const unreadCount = notifications?.filter(n => !n.is_read).length || 0;

  return (
    <header className="h-16 border-b bg-background flex items-center justify-between px-4 md:px-6 sticky top-0 z-40">
      <div className="flex items-center md:hidden">
        <span className="font-bold">IncidentFlow</span>
      </div>
      <div className="hidden md:flex flex-1" />
      <div className="flex items-center space-x-4">
        <Button variant="ghost" size="icon" asChild className="relative">
          <Link href="/notifications">
            <Bell className="h-5 w-5" />
            {unreadCount > 0 && (
              <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-destructive" />
            )}
          </Link>
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="relative h-8 w-8 rounded-full">
              <Avatar className="h-8 w-8">
                <AvatarFallback>{user?.full_name?.charAt(0) || 'U'}</AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>My Account</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout}>Log out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
