'use client';
import { CornerDownRight, Copy, Trash2, Shield } from 'lucide-react';
import { ReactionPicker } from './reaction-picker';
import type { ChatMessage } from './types';

interface MessageActionsProps {
  message: ChatMessage;
  isCurrentUser: boolean;
  isLeader: boolean;
  isSent: boolean;
  onReply: () => void;
  onCopy: () => void;
  onDelete: () => void;
  onModerate: () => void;
  onToggleReaction: (emoji: string, hasReacted: boolean) => void;
}

export function MessageActions({ message, isCurrentUser, isLeader, isSent, onReply, onCopy, onDelete, onModerate, onToggleReaction }: MessageActionsProps) {
  return (
    <div className={`opacity-0 group-hover:opacity-100 transition-all flex items-center gap-1 absolute ${isSent ? 'left-2' : 'right-2'} top-0 -translate-y-full z-20 bg-[#071426] border border-white/10 shadow-xl rounded-full px-2 py-1`}>
      <ReactionPicker userReactions={message.user_reactions || []} onToggle={onToggleReaction} />
      <div className="w-px h-4 bg-white/10 mx-0.5" />
      <button type="button" onClick={onReply} className="p-1 text-white/50 hover:text-[#20C7FF] rounded transition-colors" title="Reply">
        <CornerDownRight className="h-3.5 w-3.5" />
      </button>
      <button type="button" onClick={onCopy} className="p-1 text-white/50 hover:text-white rounded transition-colors" title="Copy">
        <Copy className="h-3.5 w-3.5" />
      </button>
      {isCurrentUser && (
        <button type="button" onClick={onDelete} className="p-1 text-white/50 hover:text-red-400 rounded transition-colors" title="Delete">
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
      {!isCurrentUser && isLeader && (
        <button type="button" onClick={onModerate} className="p-1 text-white/50 hover:text-rose-400 rounded transition-colors" title="Moderate (Group Leader)">
          <Shield className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
