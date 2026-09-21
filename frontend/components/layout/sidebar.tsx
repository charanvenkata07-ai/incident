'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard, ClipboardList, Bell, Settings, Users, Users2,
  Calendar, GitBranch, TrendingUp, ScrollText, Zap, MessageSquare,
  UserCheck, Activity, HelpCircle
} from 'lucide-react';
import { useAuth } from '@/hooks/use-auth';
import { Avatar, AvatarFallback } from '../ui/avatar';
import { StatusBadge } from '../status-badge';

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  const isEmployee = user?.role === 'EMPLOYEE' || user?.role === 'SUPERVISOR';
  const isAdmin = user?.role === 'ADMIN' || user?.role === 'SUPERVISOR';

  const employeeLinks = [
    { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, aliases: ['/dashboard'] },
    { href: '/employee/work', label: 'My Work', icon: ClipboardList, aliases: ['/my-work', '/employee/work'] },
    { href: '/employee/team', label: 'My Team', icon: Users2, aliases: ['/my-shift', '/employee/team'] },
    { href: '/employee/team-chat', label: 'Chat', icon: MessageSquare, aliases: ['/team-chat', '/employee/team-chat', '/employee/chat'] },
    { href: '/employee/notifications', label: 'Notifications', icon: Bell, aliases: ['/notifications', '/employee/notifications'] },
    { href: '/employee/profile', label: 'Profile', icon: UserCheck, aliases: ['/profile', '/employee/profile'] },
  ];

  const adminLinks = [
    { href: '/admin', label: 'Admin Dashboard', icon: LayoutDashboard },
    { href: '/employee/team-chat', label: 'Team Chat', icon: MessageSquare },
    { href: '/admin/live-pilot', label: 'Live Pilot', icon: Zap },
    { href: '/admin/integrations', label: 'Integrations', icon: GitBranch },
    { href: '/admin/employees', label: 'Employees', icon: Users },
    { href: '/admin/groups', label: 'Groups', icon: Users2 },
    { href: '/admin/shifts', label: 'Shifts', icon: Calendar },
    { href: '/admin/assignments', label: 'Assignments', icon: ClipboardList },
    { href: '/admin/analytics', label: 'Analytics', icon: TrendingUp },
    { href: '/admin/system/diagnostics', label: 'Diagnostics', icon: Activity },
    { href: '/admin/audit-logs', label: 'Audit Logs', icon: ScrollText },
    { href: '/admin/settings', label: 'Settings', icon: Settings },
    { href: '/admin/help', label: 'Help', icon: HelpCircle },
  ];

  return (
    <div className="hidden md:flex flex-col w-64 border-r border-black/[0.08] dark:border-white/[0.08] bg-white/95 dark:bg-[#071426]/95 backdrop-blur-md text-zinc-900 dark:text-zinc-100 h-screen sticky top-0">
      <div className="px-5 py-4 border-b border-black/[0.06] dark:border-white/[0.06]">
        <Link href="/dashboard" className="flex items-center space-x-3 group">
          <img
            src="/brand/incidentflow-mark.png"
            alt="IncidentFlow Mark"
            className="h-9 w-9 object-contain shrink-0 transition-transform duration-200 group-hover:scale-105"
          />
          <div className="flex flex-col">
            <div className="flex items-center">
              <span className="font-bold text-lg tracking-tight text-[#071A33] dark:text-white">Incident</span>
              <span className="font-bold text-lg tracking-tight text-[#087CFF] dark:text-[#149BFF]">Flow</span>
            </div>
            <span className="text-[9px] font-bold tracking-widest text-[#667085] dark:text-zinc-400 uppercase">
              Detect · Assign · Resolve
            </span>
          </div>
        </Link>
      </div>

      <nav className="flex-1 px-3 py-3 space-y-1 overflow-y-auto">
        {isEmployee && (
          <div className="mb-6 space-y-1">
            <div className="text-[10px] font-bold text-zinc-600 dark:text-zinc-400 px-3 mb-2 uppercase tracking-wider">Employee</div>
            {employeeLinks.map((link) => {
              const Icon = link.icon;
              const isActive = pathname
                ? link.aliases.some(alias => pathname === alias || (alias !== '/dashboard' && pathname.startsWith(`${alias}/`)))
                : false;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "flex items-center space-x-3 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-150 active:scale-[0.98]",
                    isActive
                      ? "bg-blue-50/80 text-[#087CFF] dark:bg-blue-950/40 dark:text-[#149BFF] font-semibold shadow-sm"
                      : "text-zinc-600 hover:bg-zinc-100/70 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/40 dark:hover:text-zinc-100"
                  )}
                >
                  <Icon className={cn("h-4 w-4", isActive ? "text-[#087CFF] dark:text-[#149BFF]" : "text-zinc-600 dark:text-zinc-400")} />
                  <span>{link.label}</span>
                </Link>
              );
            })}
          </div>
        )}

        {isAdmin && (
          <div className="space-y-1">
            <div className="text-[10px] font-bold text-zinc-600 dark:text-zinc-400 px-3 mb-2 uppercase tracking-wider">Admin</div>
            {adminLinks.map((link) => {
              const Icon = link.icon;
              const isActive = pathname ? (pathname === link.href || (link.href !== '/admin' && pathname.startsWith(`${link.href}/`))) : false;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "flex items-center space-x-3 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-150 active:scale-[0.98]",
                    isActive
                      ? "bg-blue-50/80 text-[#087CFF] dark:bg-blue-950/40 dark:text-[#149BFF] font-semibold shadow-sm"
                      : "text-zinc-600 hover:bg-zinc-100/70 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/40 dark:hover:text-zinc-100"
                  )}
                >
                  <Icon className={cn("h-4 w-4", isActive ? "text-[#087CFF] dark:text-[#149BFF]" : "text-zinc-600 dark:text-zinc-400")} />
                  <span>{link.label}</span>
                </Link>
              );
            })}
          </div>
        )}
      </nav>

      <div className="p-4 border-t border-zinc-200 mt-auto">
        <Link
          href="/employee/profile"
          className="flex items-center space-x-3 p-2 rounded-lg hover:bg-zinc-100 transition-colors group cursor-pointer"
          title="View & Edit Profile"
        >
          <Avatar>
            <AvatarFallback className="bg-zinc-200 text-zinc-900 group-hover:bg-indigo-100 group-hover:text-indigo-700 transition-colors">
              {user?.full_name?.charAt(0) || 'U'}
            </AvatarFallback>
          </Avatar>
          <div className="flex flex-col flex-1 overflow-hidden">
            <span className="text-sm font-semibold truncate text-zinc-900 group-hover:text-indigo-600 transition-colors">
              {user?.full_name}
            </span>
            <div className="flex items-center space-x-1">
               <span className="h-2 w-2 rounded-full bg-green-500" />
               <span className="text-xs font-medium text-zinc-600">Profile & Settings</span>
            </div>
          </div>
        </Link>
      </div>
    </div>
  );
}
