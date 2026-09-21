'use client';
import { Hash } from 'lucide-react';
import type { ConversationItem } from './types';

interface TeamConversationItemProps {
  conversation: ConversationItem;
  isSelected: boolean;
  onClick: () => void;
}

export function TeamConversationItem({ conversation, isSelected, onClick }: TeamConversationItemProps) {
  const title = conversation.title || conversation.team_name || 'Team Chat';
  const hasUnread = conversation.unread_count > 0;
  return (
    <button type="button" onClick={onClick}
      className={`w-full text-left px-3 py-2.5 rounded-xl flex items-center gap-2.5 transition-colors ${isSelected ? 'bg-[#087CFF]/15 border border-[#087CFF]/30' : 'hover:bg-white/5 border border-transparent'}`}>
      <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${isSelected ? 'bg-[#087CFF]/20 text-[#087CFF]' : 'bg-white/5 text-white/40'}`}>
        <Hash className="h-4 w-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className={`text-sm truncate ${isSelected ? 'font-semibold text-white' : 'font-medium text-white/80'}`}>{title}</span>
          {hasUnread && <span className="bg-[#087CFF] text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0 ml-1">{conversation.unread_count}</span>}
        </div>
        {conversation.last_message && (
          <p className="text-[11px] text-white/40 truncate mt-0.5">
            <span className="font-medium text-white/50">{conversation.last_message.sender_name.split(' ')[0]}:</span>{' '}
            {conversation.last_message.is_deleted ? 'Deleted message' : conversation.last_message.content}
          </p>
        )}
      </div>
    </button>
  );
}
