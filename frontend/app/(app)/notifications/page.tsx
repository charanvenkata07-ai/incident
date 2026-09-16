'use client';

import * as React from 'react';
import { useNotifications, useMarkAllRead } from '@/hooks/use-notifications';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Bell, CheckCircle2 } from 'lucide-react';
import { EmptyState } from '@/components/empty-state';
import { formatRelativeTime } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import Link from 'next/link';

export default function NotificationsPage() {
  const { data: notifications, isLoading } = useNotifications();
  const markAllRead = useMarkAllRead();

  if (isLoading) return <div className="space-y-4 max-w-4xl mx-auto"><Skeleton className="h-8 w-48 mb-6" /><Skeleton className="h-24 w-full" /><Skeleton className="h-24 w-full" /></div>;

  const unreadCount = notifications?.filter(n => !n.is_read).length || 0;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Notifications</h1>
        {unreadCount > 0 && (
          <Button variant="outline" size="sm" onClick={() => markAllRead.mutate()} loading={markAllRead.isPending}>
            <CheckCircle2 className="mr-2 h-4 w-4" /> Mark all as read
          </Button>
        )}
      </div>

      {!notifications || notifications.length === 0 ? (
        <EmptyState icon={Bell} title="No notifications" description="You're all caught up." />
      ) : (
        <div className="space-y-4">
          {notifications.map(notif => (
            <Card key={notif.id} className={notif.is_read ? 'bg-background' : 'bg-blue-50/50 dark:bg-blue-900/10'}>
              <CardContent className="p-4 flex items-start gap-4">
                <div className="mt-1">
                  <Bell className="h-5 w-5 text-muted-foreground" />
                </div>
                <div className="flex-1 space-y-1">
                  <div className="flex justify-between items-start">
                    <p className="font-medium text-sm">{notif.title}</p>
                    <span className="text-xs text-muted-foreground">{formatRelativeTime(notif.created_at)}</span>
                  </div>
                  <p className="text-sm text-muted-foreground">{notif.message}</p>
                  {notif.incident_number && (
                    <div className="mt-2">
                      <Link href={`/incidents/${notif.incident_number}`} className="text-sm text-blue-600 dark:text-blue-400 hover:underline">
                        View Incident {notif.incident_number}
                      </Link>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
