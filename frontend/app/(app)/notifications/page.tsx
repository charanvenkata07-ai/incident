'use client';

import * as React from 'react';
import { useNotifications, useMarkAllRead, useMarkRead } from '@/hooks/use-notifications';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Bell, CheckCircle2, AlertTriangle, Users,
  Info, Zap, RefreshCw, Clock, MessageSquare,
  MessageCircle, AtSign, ArrowRight, CornerDownLeft,
  ExternalLink, Check, Inbox
} from 'lucide-react';
import { EmptyState } from '@/components/empty-state';
import { formatRelativeTime } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { Notification, NotificationAction } from '@/types';
import { usePageSearch } from '@/hooks/use-page-search';
import { HighlightMatch } from '@/components/search/highlight-match';

/* ── Action Center Type Config ───────────────────────────────────────── */
const TYPE_CONFIG: Record<string, { label: string; icon: any; color: string; bg: string }> = {
  DIRECT_MESSAGE: { label: 'Direct Message', icon: MessageCircle, color: 'text-sky-600', bg: 'bg-sky-50 dark:bg-sky-950/30' },
  CHAT_MESSAGE: { label: 'Chat Message', icon: MessageCircle, color: 'text-sky-600', bg: 'bg-sky-50 dark:bg-sky-950/30' },
  TEAM_CHAT_MESSAGE: { label: 'Team Chat', icon: MessageSquare, color: 'text-indigo-600', bg: 'bg-indigo-50 dark:bg-indigo-950/30' },
  GROUP_CHAT_MESSAGE: { label: 'Group Chat', icon: Users, color: 'text-purple-600', bg: 'bg-purple-50 dark:bg-purple-950/30' },
  INCIDENT_CHAT_MESSAGE: { label: 'Incident Thread', icon: MessageSquare, color: 'text-teal-600', bg: 'bg-teal-50 dark:bg-teal-950/30' },
  MENTION: { label: 'Mentioned You', icon: AtSign, color: 'text-amber-600', bg: 'bg-amber-50 dark:bg-amber-950/30' },
  INCIDENT_ASSIGNED: { label: 'Assigned to You', icon: AlertTriangle, color: 'text-rose-600', bg: 'bg-rose-50 dark:bg-rose-950/30' },
  INCIDENT_REASSIGNED: { label: 'Reassigned', icon: AlertTriangle, color: 'text-orange-600', bg: 'bg-orange-50 dark:bg-orange-950/30' },
  INCIDENT_UPDATED: { label: 'Incident Update', icon: Info, color: 'text-blue-600', bg: 'bg-blue-50 dark:bg-blue-950/30' },
  GROUP_NOTICE: { label: 'Group Notice', icon: Users, color: 'text-indigo-600', bg: 'bg-indigo-50 dark:bg-indigo-950/30' },
  NEW_INCIDENT: { label: 'New Incident', icon: AlertTriangle, color: 'text-amber-600', bg: 'bg-amber-50 dark:bg-amber-950/30' },
  TASK_ASSIGNED: { label: 'Task Assigned', icon: AlertTriangle, color: 'text-rose-600', bg: 'bg-rose-50 dark:bg-rose-950/30' },
  SHIFT_CHANGED: { label: 'Shift Change', icon: Clock, color: 'text-amber-600', bg: 'bg-amber-50 dark:bg-amber-950/30' },
  SYSTEM: { label: 'System', icon: Zap, color: 'text-zinc-600', bg: 'bg-zinc-100 dark:bg-zinc-800/40' },
  SERVICENOW_SYNC: { label: 'ServiceNow Sync', icon: RefreshCw, color: 'text-purple-600', bg: 'bg-purple-50 dark:bg-purple-950/30' },
};

function getTypeConfig(type: string) {
  return TYPE_CONFIG[type] ?? { label: type, icon: Bell, color: 'text-muted-foreground', bg: 'bg-muted' };
}

function TypeBadge({ type }: { type: string }) {
  const cfg = getTypeConfig(type);
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${cfg.bg} ${cfg.color}`}>
      <Icon className="h-3 w-3" />
      {cfg.label}
    </span>
  );
}

export default function NotificationsPage() {
  const router = useRouter();
  const { data: notifications, isLoading } = useNotifications();
  const markAllRead = useMarkAllRead();
  const markRead = useMarkRead();
  const [filterTab, setFilterTab] = React.useState<'ALL' | 'UNREAD' | 'CHAT' | 'WORK'>('ALL');

  if (isLoading) {
    return (
      <div className="space-y-4 max-w-3xl mx-auto">
        <Skeleton className="h-8 w-48 mb-6" />
        {[1, 2, 3].map(i => <Skeleton key={i} className="h-28 w-full" />)}
      </div>
    );
  }

  const unreadCount = notifications?.filter(n => !n.is_read).length || 0;

  // Filtered notifications
  const filteredNotifs = (notifications || []).filter(n => {
    if (filterTab === 'UNREAD') return !n.is_read;
    if (filterTab === 'CHAT') return ['CHAT_MESSAGE', 'DIRECT_MESSAGE', 'TEAM_CHAT_MESSAGE', 'GROUP_CHAT_MESSAGE', 'INCIDENT_CHAT_MESSAGE', 'MENTION'].includes(n.type);
    if (filterTab === 'WORK') return ['INCIDENT_ASSIGNED', 'TASK_ASSIGNED', 'INCIDENT_REASSIGNED', 'GROUP_NOTICE', 'NEW_INCIDENT'].includes(n.type);
    return true;
  });

  const [localSearch, setLocalSearch] = React.useState('');
  const searchedNotifs = filteredNotifs.filter(n => {
    if (!localSearch.trim()) return true;
    const q = localSearch.toLowerCase();
    return (
      n.title?.toLowerCase().includes(q) ||
      n.message?.toLowerCase().includes(q) ||
      n.type?.toLowerCase().includes(q)
    );
  });

  const { searchQuery, setSearchQuery } = usePageSearch({
    pageName: 'Notifications',
    placeholder: 'Filter notifications on this page...',
    itemCount: filteredNotifs.length,
    filteredCount: searchedNotifs.length,
    onSearch: (q) => setLocalSearch(q),
  });

  // Action click handler: mark read and route
  const handleActionClick = (notifId: string, url: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    markRead.mutate(notifId);
    router.push(url);
  };

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Bell className="h-6 w-6 text-indigo-600" />
            <h1 className="text-2xl font-bold tracking-tight">Action Center</h1>
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            Realtime operational alerts, tasks, messages, and mentions
          </p>
        </div>

        {unreadCount > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => markAllRead.mutate()}
            disabled={markAllRead.isPending}
            className="text-xs self-start sm:self-auto border-indigo-200 hover:bg-indigo-50 dark:hover:bg-indigo-950/20 text-indigo-700 dark:text-indigo-400"
          >
            <CheckCircle2 className="mr-1.5 h-4 w-4" />
            Mark all read ({unreadCount})
          </Button>
        )}
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b pb-2 overflow-x-auto text-xs">
        <Button
          variant={filterTab === 'ALL' ? 'default' : 'ghost'}
          size="sm"
          className="h-8 text-xs font-medium"
          onClick={() => setFilterTab('ALL')}
        >
          All ({notifications?.length || 0})
        </Button>
        <Button
          variant={filterTab === 'UNREAD' ? 'default' : 'ghost'}
          size="sm"
          className="h-8 text-xs font-medium"
          onClick={() => setFilterTab('UNREAD')}
        >
          Unread {unreadCount > 0 && <span className="ml-1.5 px-1.5 py-0.2 rounded-full bg-rose-500 text-white text-[10px]">{unreadCount}</span>}
        </Button>
        <Button
          variant={filterTab === 'CHAT' ? 'default' : 'ghost'}
          size="sm"
          className="h-8 text-xs font-medium"
          onClick={() => setFilterTab('CHAT')}
        >
          💬 Chat & Mentions
        </Button>
        <Button
          variant={filterTab === 'WORK' ? 'default' : 'ghost'}
          size="sm"
          className="h-8 text-xs font-medium"
          onClick={() => setFilterTab('WORK')}
        >
          🚨 Incidents & Tasks
        </Button>
      </div>

      {/* Notifications List */}
      {filteredNotifs.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title={filterTab === 'UNREAD' ? 'No unread notifications' : 'No notifications found'}
          description="You are all caught up with your team and operations."
        />
      ) : searchedNotifs.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title="No matching notifications"
          description={`No notifications match "${localSearch}" on this page.`}
        />
      ) : (
        <div className="space-y-3">
          {searchedNotifs.map(notif => {
            const cfg = getTypeConfig(notif.type);
            const isGroupNotice = notif.type === 'GROUP_NOTICE';
            const isAssignment = notif.type === 'INCIDENT_ASSIGNED' || notif.type === 'INCIDENT_REASSIGNED';
            const isChat = notif.type.includes('CHAT') || notif.type === 'DIRECT_MESSAGE' || notif.type === 'MENTION';

            // Resolve actions list: prioritize notif.actions from backend, fallback to deterministic defaults
            const actions: NotificationAction[] = (notif.actions && notif.actions.length > 0)
              ? notif.actions
              : (isChat
                  ? [
                      { label: 'Reply', action: 'REPLY', url: notif.action_url || `/team-chat?conversation=${notif.conversation_id || ''}` },
                      { label: 'View Chat', action: 'VIEW', url: notif.action_url || `/team-chat?conversation=${notif.conversation_id || ''}` }
                    ]
                  : (isAssignment
                      ? [
                          { label: 'View Work', action: 'VIEW_WORK', url: '/my-work' },
                          { label: 'Open Incident', action: 'OPEN_INCIDENT', url: `/incidents/${notif.incident_id || notif.incident_number || ''}` }
                        ]
                      : (isGroupNotice
                          ? [
                              { label: 'View Incident', action: 'OPEN_INCIDENT', url: `/incidents/${notif.incident_id || notif.incident_number || ''}` }
                            ]
                          : []
                        )
                    )
                );

            return (
              <Card
                key={notif.id}
                onClick={() => {
                  if (!notif.is_read) markRead.mutate(notif.id);
                  if (notif.action_url) router.push(notif.action_url);
                }}
                className={`transition-all cursor-pointer hover:shadow-md ${
                  notif.is_read
                    ? 'bg-card border-border/80'
                    : 'bg-indigo-50/40 dark:bg-indigo-950/20 border-indigo-200 dark:border-indigo-800/40 shadow-sm'
                }`}
              >
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    {/* Icon */}
                    <div className={`mt-0.5 p-2 rounded-lg ${cfg.bg} flex-shrink-0`}>
                      <cfg.icon className={`h-4 w-4 ${cfg.color}`} />
                    </div>

                    <div className="flex-1 min-w-0">
                      {/* Top row */}
                      <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                        <div className="flex items-center gap-2">
                          <TypeBadge type={notif.type} />
                          {notif.priority && (
                            <span className="text-xs font-mono font-bold bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 px-2 py-0.5 rounded">
                              {notif.priority}
                            </span>
                          )}
                          {!notif.is_read && (
                            <span className="w-2 h-2 rounded-full bg-indigo-600 inline-block animate-pulse" title="Unread" />
                          )}
                        </div>

                        <span
                          className="text-xs text-muted-foreground whitespace-nowrap"
                          title={notif.created_at ? new Date(notif.created_at).toLocaleString() : ''}
                        >
                          {formatRelativeTime(notif.created_at)}
                        </span>
                      </div>

                      {/* Title */}
                      <p className="font-semibold text-sm leading-tight text-foreground mt-1">
                        <HighlightMatch text={notif.title} query={localSearch} />
                      </p>

                      {/* Message Content */}
                      {isGroupNotice ? (
                        <div className="mt-2 rounded-md bg-zinc-950 text-zinc-100 p-3 font-mono text-xs overflow-x-auto whitespace-pre-wrap leading-relaxed border border-zinc-800">
                          {notif.message}
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap leading-relaxed">
                          {notif.message}
                        </p>
                      )}

                      {/* Action Buttons Bar */}
                      <div className="mt-3.5 pt-2.5 border-t border-border/60 flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          {notif.incident_number && (
                            <span className="text-xs font-mono font-bold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/40 px-2 py-0.5 rounded border border-indigo-200/60 dark:border-indigo-900/60">
                              {notif.incident_number}
                            </span>
                          )}
                        </div>

                        {/* Action Buttons */}
                        <div className="flex items-center gap-2">
                          {actions.map((act, idx) => {
                            const isReply = act.action === 'REPLY' || act.label.toLowerCase().includes('reply');
                            const isOpenWork = act.action === 'VIEW_WORK' || act.label.toLowerCase().includes('work');
                            const isOpenInc = act.action === 'OPEN_INCIDENT' || act.label.toLowerCase().includes('incident');

                            return (
                              <Button
                                key={idx}
                                size="sm"
                                variant={idx === 0 ? 'default' : 'outline'}
                                className={`text-xs h-7 px-3 font-medium transition-all ${
                                  idx === 0
                                    ? 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm'
                                    : 'border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800'
                                }`}
                                onClick={(e) => handleActionClick(notif.id, act.url, e)}
                              >
                                {isReply && <CornerDownLeft className="mr-1 h-3 w-3" />}
                                {isOpenWork && <ArrowRight className="mr-1 h-3 w-3" />}
                                {isOpenInc && <ExternalLink className="mr-1 h-3 w-3" />}
                                <span>{act.label}</span>
                              </Button>
                            );
                          })}

                          {/* Fallback View button if no explicit action */}
                          {actions.length === 0 && notif.action_url && (
                            <Button
                              size="sm"
                              className="text-xs h-7 px-3 bg-indigo-600 hover:bg-indigo-700 text-white"
                              onClick={(e) => handleActionClick(notif.id, notif.action_url!, e)}
                            >
                              <span>View Details</span>
                              <ArrowRight className="ml-1 h-3 w-3" />
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

