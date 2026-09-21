'use client';

import * as React from 'react';
import { MessageSquare } from 'lucide-react';
import { ChatProvider } from '@/context/chat-context';
import { ChatShell } from '@/components/chat/chat-shell';
import { ErrorBoundary } from '@/components/error-boundary';
import type { ConversationTabType } from '@/components/chat/types';

/**
 * TeamChatView — thin host wrapper for the IncidentFlow Chat Shell.
 * All logic, state, WebSocket handling, and UI live in chat-shell.tsx.
 * This wrapper provides the ChatProvider context and Error Boundary.
 */
export function TeamChatView({ defaultTab }: { defaultTab?: ConversationTabType } = {}) {
  return (
    <ErrorBoundary>
      <React.Suspense fallback={
        <div className="h-[calc(100vh-4rem)] flex items-center justify-center bg-[#020817]">
          <div className="text-center space-y-3">
            <MessageSquare className="h-8 w-8 text-[#087CFF] animate-pulse mx-auto" />
            <p className="text-xs text-white/40 font-medium">Loading Chat...</p>
          </div>
        </div>
      }>
        <ChatProvider>
          <ChatShell defaultTab={defaultTab} />
        </ChatProvider>
      </React.Suspense>
    </ErrorBoundary>
  );
}

export default function TeamChatPage() {
  return <TeamChatView />;
}
