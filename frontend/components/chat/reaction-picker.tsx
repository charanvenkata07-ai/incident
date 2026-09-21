'use client';
import { EMOJI_REACTIONS } from './types';

interface ReactionPickerProps {
  userReactions: string[];
  onToggle: (emoji: string, hasReacted: boolean) => void;
}

export function ReactionPicker({ userReactions, onToggle }: ReactionPickerProps) {
  return (
    <div className="flex items-center gap-0.5">
      {EMOJI_REACTIONS.map(emoji => {
        const hasReacted = userReactions.includes(emoji);
        return (
          <button key={emoji} type="button" onClick={() => onToggle(emoji, hasReacted)}
            className={`text-sm p-1 rounded-full transition-transform hover:scale-125 ${hasReacted ? 'bg-[#087CFF]/20 scale-110' : 'hover:bg-white/10'}`}
            title={`React ${emoji}`}
          >{emoji}</button>
        );
      })}
    </div>
  );
}
