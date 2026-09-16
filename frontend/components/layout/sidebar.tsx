'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { LayoutDashboard, ClipboardList, Clock, Bell, Settings, Users, Calendar, GitBranch, TrendingUp, ScrollText } from 'lucide-react';
import { useAuth } from '@/hooks/use-auth';
import { Avatar, AvatarFallback } from '../ui/avatar';
import { StatusBadge } from '../status-badge';

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  const isEmployee = user?.role === 'EMPLOYEE' || user?.role === 'SUPERVISOR';
  const isAdmin = user?.role === 'ADMIN' || user?.role === 'SUPERVISOR';

  const employeeLinks = [
    { href: '/dashboard', label: 'Home', icon: LayoutDashboard },
    { href: '/my-work', label: 'My Work', icon: ClipboardList },
    { href: '/my-shift', label: 'My Shift', icon: Clock },
    { href: '/notifications', label: 'Notifications', icon: Bell },
  ];

  const adminLinks = [
    { href: '/admin', label: 'Admin Dashboard', icon: LayoutDashboard },
    { href: '/admin/employees', label: 'Employees', icon: Users },
    { href: '/admin/shifts', label: 'Shifts', icon: Calendar },
    { href: '/admin/assignments', label: 'Assignments', icon: GitBranch },
    { href: '/admin/analytics', label: 'Analytics', icon: TrendingUp },
    { href: '/admin/audit-logs', label: 'Audit Logs', icon: ScrollText },
    { href: '/admin/settings', label: 'Settings', icon: Settings },
  ];

  return (
    <div className="hidden md:flex flex-col w-64 border-r bg-background h-screen sticky top-0">
      <div className="p-6">
        <h1 className="text-xl font-bold tracking-tight">IncidentFlow</h1>
      </div>

      <nav className="flex-1 px-4 space-y-1 overflow-y-auto">
        {isEmployee && (
          <div className="mb-6 space-y-1">
            <div className="text-xs font-semibold text-muted-foreground px-2 mb-2 uppercase tracking-wider">Employee</div>
            {employeeLinks.map((link) => {
              const Icon = link.icon;
              const isActive = pathname === link.href || pathname.startsWith(`${link.href}/`);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "flex items-center space-x-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                    isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span>{link.label}</span>
                </Link>
              );
            })}
          </div>
        )}

        {isAdmin && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-muted-foreground px-2 mb-2 uppercase tracking-wider">Admin</div>
            {adminLinks.map((link) => {
              const Icon = link.icon;
              const isActive = pathname === link.href || pathname.startsWith(`${link.href}/`);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "flex items-center space-x-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                    isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span>{link.label}</span>
                </Link>
              );
            })}
          </div>
        )}
      </nav>

      <div className="p-4 border-t mt-auto">
        <div className="flex items-center space-x-3">
          <Avatar>
            <AvatarFallback>{user?.full_name?.charAt(0) || 'U'}</AvatarFallback>
          </Avatar>
          <div className="flex flex-col flex-1 overflow-hidden">
            <span className="text-sm font-medium truncate">{user?.full_name}</span>
            <div className="flex items-center space-x-1">
               <span className="h-2 w-2 rounded-full bg-green-500" />
               <span className="text-xs text-muted-foreground">Available</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
