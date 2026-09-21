'use client';
import * as React from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { MessageBubble } from './message-bubble';
import { EmptyChatState } from './empty-chat-state';
import type { ChatMessage, TeamMemberBrief } from './types';

function formatDateSeparator(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === now.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
}

interface MessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
  currentUserId?: string;
  isLeader: boolean;
  highlightedMessageId: string | null;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  getMediaUrl: (url: string) => string;
  onReply: (msg: ChatMessage) => void;
  onDelete: (id: string) => void;
  onModerate: (msg: ChatMessage) => void;
  onToggleReaction: (messageId: string, emoji: string, hasReacted: boolean) => void;
  onScrollToMessage: (id: string) => void;
  onOpenProfile?: (member: TeamMemberBrief) => void;
}

export function MessageList({ messages, isLoading, currentUserId, isLeader, highlightedMessageId, messagesEndRef, getMediaUrl, onReply, onDelete, onModerate, onToggleReaction, onScrollToMessage, onOpenProfile }: MessageListProps) {
  if (isLoading) {
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className={`flex gap-2 ${i % 2 === 0 ? 'flex-row-reverse' : ''}`}>
            <Skeleton className="h-8 w-8 rounded-full flex-shrink-0 bg-white/10" />
            <Skeleton className={`h-12 rounded-2xl bg-white/10 ${i % 2 === 0 ? 'w-48' : 'w-64'}`} />
          </div>
        ))}
      </div>
    );
  }

  if (messages.length === 0) {
    return <EmptyChatState tab="none" />;
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-2">
      {messages.map((msg, index) => {
        const prevMsg = index > 0 ? messages[index - 1] : null;
        const showDateSep = !prevMsg || new Date(msg.created_at).toDateString() !== new Date(prevMsg.created_at).toDateString();
        return (
          <React.Fragment key={`msg-${msg.id || index}`}>
            {showDateSep && (
              <div className="flex justify-center my-4">
                <span className="px-3 py-1 bg-white/5 text-white/40 text-[10px] rounded-full font-medium">
                  {formatDateSeparator(msg.created_at)}
                </span>
              </div>
            )}
            <MessageBubble
              message={msg}
              isCurrentUser={msg.sender_id === currentUserId}
              isLeader={isLeader}
              isHighlighted={highlightedMessageId === msg.id}
              getMediaUrl={getMediaUrl}
              onReply={onReply}
              onDelete={onDelete}
              onModerate={onModerate}
              onToggleReaction={onToggleReaction}
              onScrollToMessage={onScrollToMessage}
              onOpenProfile={onOpenProfile}
            />
          </React.Fragment>
        );
      })}
      <div ref={messagesEndRef} />
    </div>
  );
}
