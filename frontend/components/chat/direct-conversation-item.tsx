'use client';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Shield } from 'lucide-react';
import type { TeamMemberBrief, ConversationItem } from './types';

interface DirectConversationItemProps {
  member: TeamMemberBrief;
  conversation?: ConversationItem;
  isSelected: boolean;
  currentUserId?: string;
  onClick: () => void;
  getMediaUrl: (url: string) => string;
}

export function DirectConversationItem({ member, conversation, isSelected, currentUserId, onClick, getMediaUrl }: DirectConversationItemProps) {
  const isSelf = member.user_id === currentUserId;
  const isAvailable = member.is_present && member.availability_status === 'AVAILABLE';
  const isBusy = member.is_present && member.availability_status !== 'AVAILABLE';
  const hasUnread = (conversation?.unread_count ?? 0) > 0;
  const avatarSrc = member.avatar_url ? (member.avatar_url.startsWith('http') ? member.avatar_url : getMediaUrl(member.avatar_url)) : undefined;
  return (
    <button type="button" onClick={onClick}
      className={`w-full text-left px-3 py-2.5 rounded-xl flex items-center gap-2.5 transition-colors ${isSelected ? 'bg-[#087CFF]/15 border border-[#087CFF]/30' : 'hover:bg-white/5 border border-transparent'}`}>
      <div className="relative flex-shrink-0">
        <Avatar className="h-9 w-9">
          {avatarSrc && <AvatarImage src={avatarSrc} alt={member.full_name} />}
          <AvatarFallback className="text-[11px] font-bold bg-[#0B1B31] text-white/70">{member.full_name?.charAt(0) || 'U'}</AvatarFallback>
        </Avatar>
        <span className={`absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full ring-2 ring-[#020817] ${isAvailable ? 'bg-emerald-500' : isBusy ? 'bg-amber-500' : 'bg-zinc-600'}`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 justify-between">
          <div className="flex items-center gap-1 min-w-0">
            <span className={`text-sm truncate ${isSelected ? 'font-semibold text-white' : 'font-medium text-white/80'}`}>
              {member.full_name}{isSelf && <span className="text-white/30 font-normal text-xs ml-1">(You)</span>}
            </span>
            {member.is_group_leader && <Shield className="h-3 w-3 text-amber-400 flex-shrink-0" />}
          </div>
          {hasUnread && <span className="bg-[#087CFF] text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0">{conversation!.unread_count}</span>}
        </div>
        <div className="text-[10px] text-white/35 truncate">
          {member.is_present ? member.availability_status : 'Offline'}{member.on_shift && ' • On Shift'}
        </div>
      </div>
    </button>
  );
}
