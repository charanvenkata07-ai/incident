'use client';
import * as React from 'react';
import { Search, X } from 'lucide-react';
import { ChatSectionTabs } from './chat-section-tabs';
import { TeamConversationItem } from './team-conversation-item';
import { DirectConversationItem } from './direct-conversation-item';
import type { ConversationItem, ConversationTabType, TeamMemberBrief } from './types';

interface ChatSidebarProps {
  conversations: ConversationItem[];
  colleagues: TeamMemberBrief[];
  activeTab: ConversationTabType;
  selectedConvId: string | null;
  currentUserId?: string;
  onTabChange: (tab: ConversationTabType) => void;
  onSelectConversation: (id: string) => void;
  onSelectColleague: (member: TeamMemberBrief) => void;
  getMediaUrl: (url: string) => string;
}

export function ChatSidebar({ conversations, colleagues, activeTab, selectedConvId, currentUserId, onTabChange, onSelectConversation, onSelectColleague, getMediaUrl }: ChatSidebarProps) {
  const [search, setSearch] = React.useState('');

  const teamConversations = conversations.filter(c => c.type === 'TEAM' || c.type === 'ADMIN_TEAM');
  const directConversations = conversations.filter(c => c.type === 'DIRECT');
  const teamUnread = teamConversations.reduce((s, c) => s + c.unread_count, 0);
  const directUnread = directConversations.reduce((s, c) => s + c.unread_count, 0);

  const filteredTeam = search.trim()
    ? teamConversations.filter(c => (c.title || c.team_name || '').toLowerCase().includes(search.toLowerCase()))
    : teamConversations;

  const getDirectConvForMember = (userId: string) =>
    directConversations.find(c =>
      c.members?.some(m => m.user_id === userId && m.user_id !== currentUserId) ||
      (c.members?.length === 2 && c.members.some(m => m.user_id === userId))
    );

  const filteredColleagues = search.trim()
    ? colleagues.filter(c => c.full_name.toLowerCase().includes(search.toLowerCase()) || c.email.toLowerCase().includes(search.toLowerCase()))
    : colleagues;

  return (
    <div className="flex flex-col h-full bg-[#020817] border-r border-white/10">
      <div className="px-4 py-3 border-b border-white/10 flex-shrink-0">
        <h2 className="text-xs font-bold text-white/40 uppercase tracking-wider mb-2">Messages</h2>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-white/30" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search..."
            className="w-full h-8 bg-white/5 border border-white/10 rounded-lg pl-8 pr-7 text-xs text-white placeholder:text-white/25 focus:outline-none focus:border-[#087CFF]/50 transition-colors"
          />
          {search && (
            <button type="button" onClick={() => setSearch('')} className="absolute right-2 top-2 text-white/30 hover:text-white transition-colors">
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>
      <ChatSectionTabs active={activeTab} onChange={onTabChange} teamUnread={teamUnread} directUnread={directUnread} />
      <div className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
        {activeTab === 'TEAM' ? (
          filteredTeam.length === 0
            ? <div className="text-center text-xs text-white/30 py-8">No channels</div>
            : filteredTeam.map(conv => (
                <TeamConversationItem key={conv.id} conversation={conv} isSelected={conv.id === selectedConvId} onClick={() => onSelectConversation(conv.id)} />
              ))
        ) : (
          filteredColleagues.length === 0
            ? <div className="text-center text-xs text-white/30 py-8">No teammates</div>
            : filteredColleagues.map(member => {
                const existingConv = getDirectConvForMember(member.user_id);
                return (
                  <DirectConversationItem
                    key={member.user_id}
                    member={member}
                    conversation={existingConv}
                    isSelected={!!existingConv && existingConv.id === selectedConvId}
                    currentUserId={currentUserId}
                    onClick={() => onSelectColleague(member)}
                    getMediaUrl={getMediaUrl}
                  />
                );
              })
        )}
      </div>
    </div>
  );
}
