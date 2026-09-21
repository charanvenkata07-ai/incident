'use client';

import * as React from 'react';
import type { TeamMemberBrief } from '@/components/chat/types';

interface ChatContextValue {
  activeConversationId: string | null;
  setActiveConversationId: (id: string | null) => void;
  profileDrawerOpen: boolean;
  profileDrawerUser: TeamMemberBrief | null;
  openProfileDrawer: (user: TeamMemberBrief) => void;
  closeProfileDrawer: () => void;
}

const ChatContext = React.createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [activeConversationId, setActiveConversationIdState] = React.useState<string | null>(null);
  const [profileDrawerOpen, setProfileDrawerOpen] = React.useState(false);
  const [profileDrawerUser, setProfileDrawerUser] = React.useState<TeamMemberBrief | null>(null);

  const setActiveConversationId = React.useCallback((id: string | null) => {
    setActiveConversationIdState(id);
    // Broadcast to useWebSocket hook via custom event for cross-component coordination
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('incidentflow:active-conversation', { detail: { conversationId: id } }));
    }
  }, []);

  const openProfileDrawer = React.useCallback((user: TeamMemberBrief) => {
    setProfileDrawerUser(user);
    setProfileDrawerOpen(true);
  }, []);

  const closeProfileDrawer = React.useCallback(() => {
    setProfileDrawerOpen(false);
    setTimeout(() => setProfileDrawerUser(null), 300);
  }, []);

  return (
    <ChatContext.Provider value={{
      activeConversationId,
      setActiveConversationId,
      profileDrawerOpen,
      profileDrawerUser,
      openProfileDrawer,
      closeProfileDrawer,
    }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChatContext(): ChatContextValue {
  const ctx = React.useContext(ChatContext);
  if (!ctx) throw new Error('useChatContext must be used within ChatProvider');
  return ctx;
}
