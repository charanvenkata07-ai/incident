'use client';
import type { ReactionCount } from './types';

interface ReactionRowProps {
  reactions: ReactionCount[];
  userReactions: string[];
  isSent: boolean;
  onToggle: (emoji: string, hasReacted: boolean) => void;
}

export function ReactionRow({ reactions, userReactions, isSent, onToggle }: ReactionRowProps) {
  if (reactions.length === 0) return null;
  return (
    <div className={`flex flex-wrap gap-1 mt-1 ${isSent ? 'justify-end' : ''}`}>
      {reactions.map(r => {
        const hasReacted = userReactions.includes(r.emoji);
        return (
          <button key={r.emoji} type="button" onClick={() => onToggle(r.emoji, hasReacted)}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium transition-all border ${
              hasReacted ? 'bg-[#087CFF]/20 border-[#087CFF]/50 text-[#087CFF]' : 'bg-white/5 border-white/10 text-white/70 hover:bg-white/10'
            }`}>
            <span>{r.emoji}</span>
            <span className="text-[10px] font-bold">{r.count}</span>
          </button>
        );
      })}
    </div>
  );
}
