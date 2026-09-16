'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, ClipboardList, Clock, Bell } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/hooks/use-auth';

export function MobileNav() {
  const pathname = usePathname();
  const { user } = useAuth();
  
  const isEmployee = user?.role === 'EMPLOYEE' || user?.role === 'SUPERVISOR';
  const isAdmin = user?.role === 'ADMIN' || user?.role === 'SUPERVISOR';

  const employeeLinks = [
    { href: '/dashboard', icon: LayoutDashboard, label: 'Home' },
    { href: '/my-work', icon: ClipboardList, label: 'Work' },
    { href: '/my-shift', icon: Clock, label: 'Shift' },
    { href: '/notifications', icon: Bell, label: 'Alerts' },
  ];

  const adminLinks = [
    { href: '/admin', icon: LayoutDashboard, label: 'Command' },
    { href: '/admin/employees', icon: ClipboardList, label: 'Staff' },
    { href: '/admin/assignments', icon: Clock, label: 'Queue' },
    { href: '/admin/settings', icon: Bell, label: 'Safety' },
  ];

  const links = user?.role === 'ADMIN' ? adminLinks : employeeLinks;


  return (
    <div className="md:hidden fixed bottom-0 left-0 right-0 border-t bg-background flex items-center justify-around h-16 pb-safe z-50">
      {links.map((link) => {
        const Icon = link.icon;
        const isActive = pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={cn(
              "flex flex-col items-center justify-center w-full h-full space-y-1 text-xs font-medium transition-colors",
              isActive ? "text-primary" : "text-muted-foreground"
            )}
          >
            <Icon className="h-5 w-5" />
            <span>{link.label}</span>
          </Link>
        );
      })}
    </div>
  );
}
