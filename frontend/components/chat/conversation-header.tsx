'use client';
import { ChevronLeft, RefreshCw } from 'lucide-react';
import type { ConversationItem, MyTeamChatData } from './types';

interface ConversationHeaderProps {
  conversation: ConversationItem;
  myTeam?: MyTeamChatData | null;
  onBack?: () => void;
  onRefresh: () => void;
}

export function ConversationHeader({ conversation, myTeam, onBack, onRefresh }: ConversationHeaderProps) {
  const isTeamChat = myTeam && conversation.id === myTeam.conversation_id;
  const title = isTeamChat ? myTeam.team_name : (conversation.title || conversation.team_name || 'Chat');

  return (
    <div className="h-14 border-b border-white/10 px-4 flex items-center gap-3 bg-[#071426] flex-shrink-0">
      {onBack && (
        <button type="button" onClick={onBack} className="h-8 w-8 flex items-center justify-center rounded-xl text-white/50 hover:text-white hover:bg-white/5 transition-colors flex-shrink-0">
          <ChevronLeft className="h-5 w-5" />
        </button>
      )}
      <div className="flex-1 min-w-0">
        <div className="font-bold text-sm text-white truncate">{title}</div>
        {isTeamChat && myTeam ? (
          <div className="text-[11px] text-white/40">
            {myTeam.member_count} members • <span className="text-emerald-400">{myTeam.present_count} present</span>
            {myTeam.active_shift_name && ` • ${myTeam.active_shift_name}`}
          </div>
        ) : conversation.type === 'DIRECT' ? (
          <div className="text-[11px] text-white/40">Direct Message</div>
        ) : null}
      </div>
      <button type="button" onClick={onRefresh} className="h-8 w-8 flex items-center justify-center rounded-xl text-white/30 hover:text-white hover:bg-white/5 transition-colors flex-shrink-0" title="Refresh messages">
        <RefreshCw className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
