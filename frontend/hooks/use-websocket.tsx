'use client';

import { useEffect, useRef, useState } from 'react';
import { wsClient } from '@/lib/websocket';
import { useAuth } from './use-auth';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { IncidentBrief } from '@/types';

// Track seen event_ids to prevent duplicate popups
const seenEventIds = new Set<string>();

export function useWebSocket() {
  const { isAuthenticated, token, user } = useAuth();
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState(false);
  // activeConversationId is set by the chat shell via window state for cross-component coordination
  const activeConvIdRef = useRef<string | null>(null);

  // Allow chat shell to register the currently active conversation
  useEffect(() => {
    const handler = (e: Event) => {
      const custom = e as CustomEvent<{ conversationId: string | null }>;
      activeConvIdRef.current = custom.detail.conversationId;
    };
    window.addEventListener('incidentflow:active-conversation', handler);
    return () => window.removeEventListener('incidentflow:active-conversation', handler);
  }, []);

  useEffect(() => {
    if (isAuthenticated && token) {
      wsClient.setToken(token);
      wsClient.connect();
      setIsConnected(true);

      const handleIncidentAssigned = (data: unknown) => {
        const d = data as Record<string, unknown>;
        queryClient.invalidateQueries({ queryKey: ['my-work'] });
        queryClient.invalidateQueries({ queryKey: ['notifications'] });
        const incNum = (d?.incident_number as string) || 'INCIDENT';
        const taskText = (d?.task as string) || (d?.short_description as string) || 'Check My Work for instructions';
        toast.success(`✅ INCIDENT ASSIGNED TO YOU — ${incNum}`, {
          description: `YOUR TASK: ${taskText}`,
          duration: 8000,
        });
      };

      const handleIncidentUpdated = (data: unknown) => {
        const d = data as Record<string, unknown>;
        const incNum = (d?.incident_number as string) || '';
        const newStatus = ((d?.status as string) || (d?.state as string) || (d?.assignment_status as string)) as string | undefined;

        if (incNum) {
          if (newStatus) {
            queryClient.setQueriesData<IncidentBrief[]>({ queryKey: ['my-work'] }, (old) => {
              if (!old || !Array.isArray(old)) return old;
              return old.map((item) =>
                item.incident_number === incNum || item.id === incNum
                  ? {
                      ...item,
                      state: newStatus,
                      assignment_status: newStatus,
                    }
                  : item
              );
            });
          }
          queryClient.invalidateQueries({ queryKey: ['incident', incNum] });
        }
        queryClient.invalidateQueries({ queryKey: ['my-work'] });
      };

      const handleMyWorkUpdated = (data: unknown) => {
        const d = data as Record<string, unknown>;
        const incNum = (d?.incident_number as string) || '';
        const newStatus = ((d?.status as string) || (d?.state as string) || (d?.assignment_status as string)) as string | undefined;

        if (incNum && newStatus) {
          queryClient.setQueriesData<IncidentBrief[]>({ queryKey: ['my-work'] }, (old) => {
            if (!old || !Array.isArray(old)) return old;
            return old.map((item) =>
              item.incident_number === incNum || item.id === incNum
                ? {
                    ...item,
                    state: newStatus,
                    assignment_status: newStatus,
                  }
                : item
            );
          });
        }
        queryClient.invalidateQueries({ queryKey: ['my-work'] });
      };

      const handleGroupNotice = (data: unknown) => {
        const d = data as Record<string, unknown>;
        queryClient.invalidateQueries({ queryKey: ['notifications'] });
        const incNum = (d?.incident_number as string) || 'NEW INCIDENT';
        const issue = (d?.issue as string) || (d?.short_description as string) || (d?.title as string) || 'Operational Notice';
        const group = (d?.team_name as string) || (d?.assignment_group as string) || '';
        const priority = d?.priority ? ` [${d.priority}]` : '';
        toast.info(`🚨 NEW INCIDENT — ${incNum}${priority}`, {
          description: `${issue}${group ? ` (${group})` : ''}`,
          duration: 8000,
        });
      };

      const handleNotification = () => {
        queryClient.invalidateQueries({ queryKey: ['notifications'] });
      };

      // RECONNECTED: invalidate all stale caches to catch up missed realtime events
      const handleReconnected = () => {
        queryClient.invalidateQueries({ queryKey: ['my-work'] });
        queryClient.invalidateQueries({ queryKey: ['notifications'] });
        queryClient.invalidateQueries({ queryKey: ['chat-conversations'] });
        queryClient.invalidateQueries({ queryKey: ['team-chat'] });
        queryClient.invalidateQueries({ queryKey: ['incidents'] });
      };

      // CHAT_MESSAGE_CREATED: show popup for employees only, when not in that conversation
      const handleChatMessage = (data: unknown) => {
        const d = data as Record<string, unknown>;

        // Update conversation list cache
        queryClient.invalidateQueries({ queryKey: ['chat-conversations'] });

        // ADMIN/SUPERVISOR: NEVER show popup
        if (!user || user.role === 'ADMIN' || user.role === 'SUPERVISOR') return;

        // Sender: never show popup to yourself
        if (d?.sender_id === user.id) return;

        // Active conversation: never show popup if already viewing this conversation
        if (activeConvIdRef.current && activeConvIdRef.current === d?.conversation_id) return;

        // Deduplication by event_id
        const eventId = (d?.event_id as string) || (d?.id as string);
        if (eventId && seenEventIds.has(eventId)) return;
        if (eventId) {
          seenEventIds.add(eventId);
          if (seenEventIds.size > 500) {
            // Prune oldest entries
            const iter = seenEventIds.values();
            for (let i = 0; i < 100; i++) {
              const val = iter.next().value;
              if (val) seenEventIds.delete(val);
            }
          }
        }

        // Show WhatsApp-style toast
        const senderName = (d?.sender_name as string) || 'Someone';
        const content = (d?.content as string) || '';
        const conversationId = (d?.conversation_id as string) || '';
        const teamName = (d?.team_name as string) || undefined;
        const senderAvatar = (d?.sender_avatar_url as string) || undefined;

        toast(
          <div
            className="flex items-center gap-3 cursor-pointer"
            onClick={() => {
              window.dispatchEvent(new CustomEvent('incidentflow:navigate-to-conversation', {
                detail: { conversationId }
              }));
            }}
          >
            <div className="relative flex-shrink-0">
              <div className="w-10 h-10 rounded-full bg-[#087CFF]/20 flex items-center justify-center text-[#087CFF] font-bold text-sm overflow-hidden">
                {senderAvatar ? (
                  <img src={senderAvatar} alt={senderName} className="w-full h-full object-cover" />
                ) : (
                  senderName.charAt(0)
                )}
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-bold text-white">{senderName}</span>
                {teamName && <span className="text-[10px] text-white/40">in {teamName}</span>}
              </div>
              <p className="text-xs text-white/60 truncate">{content}</p>
            </div>
          </div>,
          {
            duration: 5000,
            style: { background: '#071426', border: '1px solid rgba(255,255,255,0.1)', color: 'white' },
          }
        );
      };

      wsClient.on('INCIDENT_ASSIGNED', handleIncidentAssigned);
      wsClient.on('INCIDENT_UPDATED', handleIncidentUpdated);
      wsClient.on('MY_WORK_UPDATED', handleMyWorkUpdated);
      wsClient.on('INCIDENT_ACKNOWLEDGED', handleMyWorkUpdated);
      wsClient.on('GROUP_NOTICE_CREATED', handleGroupNotice);
      wsClient.on('NOTIFICATION_CREATED', handleNotification);
      wsClient.on('RECONNECTED', handleReconnected);
      wsClient.on('CHAT_MESSAGE_CREATED', handleChatMessage);

      return () => {
        wsClient.off('INCIDENT_ASSIGNED', handleIncidentAssigned);
        wsClient.off('INCIDENT_UPDATED', handleIncidentUpdated);
        wsClient.off('MY_WORK_UPDATED', handleMyWorkUpdated);
        wsClient.off('INCIDENT_ACKNOWLEDGED', handleMyWorkUpdated);
        wsClient.off('GROUP_NOTICE_CREATED', handleGroupNotice);
        wsClient.off('NOTIFICATION_CREATED', handleNotification);
        wsClient.off('RECONNECTED', handleReconnected);
        wsClient.off('CHAT_MESSAGE_CREATED', handleChatMessage);
        wsClient.disconnect();
        setIsConnected(false);
      };
    }
  }, [isAuthenticated, token, user, queryClient]);

  return { isConnected };
}
