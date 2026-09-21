'use client';

export function TypingIndicator({ names }: { names: string[] }) {
  if (names.length === 0) return null;
  return (
    <div className="flex items-center gap-2 px-4 py-1.5 text-[11px] text-[#087CFF] italic border-t border-white/5">
      <span className="flex gap-[3px] items-center">
        {[0, 1, 2].map(i => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-[#087CFF] animate-bounce"
            style={{ animationDelay: `${i * 0.15}s`, animationDuration: '0.9s' }}
          />
        ))}
      </span>
      {names.join(', ')} {names.length === 1 ? 'is' : 'are'} typing...
    </div>
  );
}
