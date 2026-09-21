'use client';
import type { ConversationTabType } from './types';

interface ChatSectionTabsProps {
  active: ConversationTabType;
  onChange: (tab: ConversationTabType) => void;
  teamUnread: number;
  directUnread: number;
}

export function ChatSectionTabs({ active, onChange, teamUnread, directUnread }: ChatSectionTabsProps) {
  const tabs: { key: ConversationTabType; label: string; unread: number }[] = [
    { key: 'TEAM', label: 'Team', unread: teamUnread },
    { key: 'DIRECT', label: 'Direct', unread: directUnread },
  ];
  return (
    <div className="flex p-1.5 gap-1 border-b border-white/10 flex-shrink-0">
      {tabs.map(tab => (
        <button key={tab.key} type="button" onClick={() => onChange(tab.key)}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${active === tab.key ? 'bg-[#087CFF]/15 text-[#087CFF]' : 'text-white/40 hover:text-white/70 hover:bg-white/5'}`}>
          {tab.label}
          {tab.unread > 0 && <span className="bg-[#087CFF] text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full">{tab.unread}</span>}
        </button>
      ))}
    </div>
  );
}
