'use client';
import * as React from 'react';
import Link from 'next/link';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { ReactionRow } from './reaction-row';
import { MessageActions } from './message-actions';
import { AttachmentPreview } from './attachment-preview';
import { AudioMessage } from './audio-message';
import { VideoPlayer } from './video-player';
import { FileMessage } from './file-message';
import type { ChatMessage, TeamMemberBrief } from './types';

interface MessageBubbleProps {
  message: ChatMessage;
  isCurrentUser: boolean;
  isLeader: boolean;
  isHighlighted: boolean;
  getMediaUrl: (url: string) => string;
  onReply: (msg: ChatMessage) => void;
  onDelete: (id: string) => void;
  onModerate: (msg: ChatMessage) => void;
  onToggleReaction: (messageId: string, emoji: string, hasReacted: boolean) => void;
  onScrollToMessage: (id: string) => void;
  onOpenProfile?: (member: TeamMemberBrief) => void;
}

export function MessageBubble({ message: msg, isCurrentUser, isLeader, isHighlighted, getMediaUrl, onReply, onDelete, onModerate, onToggleReaction, onScrollToMessage, onOpenProfile }: MessageBubbleProps) {
  const isSystem = msg.sender_role === 'SYSTEM' || !msg.sender_id;
  const isAdminSender = msg.sender_role === 'ADMIN' || msg.sender_role === 'SUPERVISOR';
  const senderAvatar = msg.sender_avatar_url
    ? (msg.sender_avatar_url.startsWith('http') ? msg.sender_avatar_url : getMediaUrl(msg.sender_avatar_url))
    : undefined;
  const parts = msg.content ? msg.content.split(/(#INC-[A-Z0-9]+|#INC\d+)/gi) : [''];

  const handleCopy = () => { if (msg.content) navigator.clipboard.writeText(msg.content).catch(() => {}); };

  const makeProfileBrief = (): TeamMemberBrief => ({
    user_id: msg.sender_id || '',
    employee_id: '',
    full_name: msg.sender_name,
    email: msg.sender_email || '',
    role: msg.sender_role,
    avatar_url: msg.sender_avatar_url,
    is_present: false,
    availability_status: 'AVAILABLE',
    on_shift: false,
  });

  return (
    <div
      id={`msg-${msg.id}`}
      className={`group relative flex gap-2 py-0.5 ${isCurrentUser ? 'flex-row-reverse' : ''} transition-all duration-500 ${isHighlighted ? 'bg-[#087CFF]/10 ring-1 ring-[#087CFF]/40 rounded-2xl px-2' : ''}`}
    >
      {!isCurrentUser && (
        <button type="button" onClick={() => onOpenProfile && msg.sender_id && onOpenProfile(makeProfileBrief())} className="flex-shrink-0 mt-0.5">
          <Avatar className="h-8 w-8">
            {senderAvatar && <AvatarImage src={senderAvatar} alt={msg.sender_name} />}
            <AvatarFallback className={`text-[10px] font-bold ${isAdminSender ? 'bg-purple-900 text-purple-200' : 'bg-[#0B1B31] text-white/70'}`}>
              {msg.sender_name?.charAt(0) || 'U'}
            </AvatarFallback>
          </Avatar>
        </button>
      )}

      <div className={`min-w-0 space-y-1 flex flex-col ${isCurrentUser ? 'items-end' : 'items-start'}`} style={{ maxWidth: '68%' }}>
        {!isCurrentUser && !isSystem && (
          <div className="flex items-center gap-1.5">
            <button type="button" onClick={() => onOpenProfile && msg.sender_id && onOpenProfile(makeProfileBrief())} className="text-[11px] font-semibold text-white/80 hover:text-white transition-colors">
              {msg.sender_name}
            </button>
            {isAdminSender && <span className="text-[9px] font-bold bg-purple-900/60 text-purple-300 px-1.5 py-0.5 rounded">ADMIN</span>}
            <span className="text-[10px] text-white/30">{new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            {msg.is_edited && <span className="text-[9px] text-white/30 italic">(edited)</span>}
          </div>
        )}

        <div className={`relative px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap shadow-sm ${
          isCurrentUser ? 'bg-[#087CFF] text-white rounded-2xl rounded-br-sm'
            : isSystem ? 'bg-white/5 text-white/50 italic rounded-2xl text-xs'
            : 'bg-[#0B1B31] text-white/90 rounded-2xl rounded-bl-sm'
        }`}>
          {msg.reply_to && (
            <button type="button" onClick={() => onScrollToMessage(msg.reply_to!.id)}
              className={`mb-2 block w-full text-left p-2 rounded-lg text-[11px] border-l-4 transition-colors ${
                isCurrentUser ? 'bg-white/10 border-white/50 hover:bg-white/20' : 'bg-white/5 border-[#087CFF] hover:bg-white/10'
              }`}>
              <span className="font-bold block text-[10px] opacity-90">{msg.reply_to.sender_name}</span>
              <span className="block opacity-70 truncate italic">{msg.reply_to.is_deleted ? 'This message was deleted' : msg.reply_to.content}</span>
            </button>
          )}

          {msg.is_deleted ? (
            <span className="italic opacity-50">
              {msg.deleted_by && msg.sender_id && msg.deleted_by !== msg.sender_id ? 'This message was removed by a Group Leader' : 'This message was deleted'}
            </span>
          ) : (
            <>
              {(!msg.attachment || (msg.content && msg.content !== `[${msg.attachment.file_name}]` && msg.content !== 'Voice note' && msg.content !== '🎤 Voice note')) && (
                <div>
                  {parts.map((p, idx) => {
                    if (p.toUpperCase().startsWith('#INC')) {
                      return (
                        <Link key={idx} href={`/incidents/${p.replace('#', '')}`}
                          className={`font-mono font-bold underline hover:opacity-80 ${isCurrentUser ? 'text-amber-200' : 'text-[#20C7FF]'}`}>
                          {p}
                        </Link>
                      );
                    }
                    return <span key={idx}>{p}</span>;
                  })}
                </div>
              )}
              {msg.attachment?.mime_type?.startsWith('image/') && (
                <AttachmentPreview src={getMediaUrl(msg.attachment.url)} alt={msg.attachment.file_name} />
              )}
              {msg.attachment && (msg.attachment.mime_type?.startsWith('video/') || msg.message_type === 'VIDEO') && (
                <div className="mt-2">
                  <VideoPlayer src={getMediaUrl(msg.attachment.url)} fileName={msg.attachment.file_name} isSent={isCurrentUser} />
                </div>
              )}
              {msg.attachment && (msg.attachment.mime_type?.startsWith('audio/') || msg.message_type === 'AUDIO') && (
                <div className="mt-2">
                  <AudioMessage src={getMediaUrl(msg.attachment.url)} duration={msg.attachment.duration_seconds} isSent={isCurrentUser} />
                </div>
              )}
              {msg.attachment &&
                !msg.attachment.mime_type?.startsWith('image/') &&
                !msg.attachment.mime_type?.startsWith('video/') &&
                !msg.attachment.mime_type?.startsWith('audio/') && (
                  <div className="mt-2">
                    <FileMessage attachment={msg.attachment} downloadUrl={getMediaUrl(msg.attachment.url)} isSent={isCurrentUser} />
                  </div>
                )}
            </>
          )}
        </div>

        {isCurrentUser && (
          <div className="flex items-center gap-1 pr-1">
            <span className="text-[10px] text-white/30">{new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            {msg.is_edited && <span className="text-[9px] text-white/30 italic">(edited)</span>}
          </div>
        )}

        {!msg.is_deleted && (
          <ReactionRow reactions={msg.reactions || []} userReactions={msg.user_reactions || []} isSent={isCurrentUser} onToggle={(emoji, hasReacted) => onToggleReaction(msg.id, emoji, hasReacted)} />
        )}
      </div>

      {!msg.is_deleted && (
        <MessageActions message={msg} isCurrentUser={isCurrentUser} isLeader={isLeader} isSent={isCurrentUser}
          onReply={() => onReply(msg)} onCopy={handleCopy} onDelete={() => onDelete(msg.id)} onModerate={() => onModerate(msg)}
          onToggleReaction={(emoji, hasReacted) => onToggleReaction(msg.id, emoji, hasReacted)} />
      )}
    </div>
  );
}
