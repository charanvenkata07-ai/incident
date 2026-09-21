'use client';
import { MessageSquare, Users } from 'lucide-react';

export function EmptyChatState({ tab }: { tab: 'TEAM' | 'DIRECT' | 'none' }) {
  if (tab === 'TEAM') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center p-8 select-none">
        <div className="w-16 h-16 rounded-2xl bg-[#087CFF]/10 flex items-center justify-center mb-4">
          <MessageSquare className="h-8 w-8 text-[#087CFF]" />
        </div>
        <p className="text-sm font-bold text-white/90">Team Chat</p>
        <p className="text-xs text-white/40 mt-1 max-w-[220px]">Your team channel is ready. Send the first message!</p>
      </div>
    );
  }
  if (tab === 'DIRECT') {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center p-8 select-none">
        <div className="w-16 h-16 rounded-2xl bg-[#20C7FF]/10 flex items-center justify-center mb-4">
          <Users className="h-8 w-8 text-[#20C7FF]" />
        </div>
        <p className="text-sm font-bold text-white/90">Direct Messages</p>
        <p className="text-xs text-white/40 mt-1 max-w-[220px]">Tap a teammate to start a private conversation.</p>
      </div>
    );
  }
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center p-8 select-none">
      <MessageSquare className="h-10 w-10 text-white/20 mb-3" />
      <p className="text-sm font-semibold text-white/60">Select a conversation</p>
      <p className="text-xs text-white/30 mt-1">Choose from Team or Direct messages on the left</p>
    </div>
  );
}
