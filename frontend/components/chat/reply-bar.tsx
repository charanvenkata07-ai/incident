'use client';
import { X, CornerDownRight } from 'lucide-react';
import type { ChatMessage } from './types';

export function ReplyBar({ message, onCancel }: { message: ChatMessage; onCancel: () => void }) {
  return (
    <div className="px-4 py-2 bg-[#0B1B31] border-t border-white/10 flex items-center gap-3">
      <CornerDownRight className="h-4 w-4 text-[#087CFF] flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="text-[11px] font-bold text-[#087CFF]">{message.sender_name}</span>
        <p className="text-[11px] text-white/50 truncate">{message.is_deleted ? 'This message was deleted' : message.content}</p>
      </div>
      <button type="button" onClick={onCancel} className="h-6 w-6 rounded-full hover:bg-white/10 flex items-center justify-center text-white/50 hover:text-white transition-colors flex-shrink-0">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
