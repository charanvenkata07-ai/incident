'use client';

import * as React from 'react';
import { Trash2, Send, Mic } from 'lucide-react';

interface VoiceRecorderProps {
  duration: number;
  onCancel: () => void;
  onSend: () => void;
  audioLevel?: number; // Optional live amplitude 0..1
}

export function VoiceRecorder({ duration, onCancel, onSend }: VoiceRecorderProps) {
  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="flex items-center justify-between gap-3 bg-red-950/40 px-4 py-3 border-t border-red-900/30 backdrop-blur-md">
      {/* Left recording indicator & timer */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
          </span>
          <div className="flex items-center gap-1.5 text-xs font-semibold text-red-400">
            <Mic className="h-3.5 w-3.5" />
            <span>Recording</span>
          </div>
        </div>

        {/* Pulsing audio wave animation */}
        <div className="flex items-center gap-1 h-5 px-2">
          {[40, 75, 55, 90, 60, 85, 45, 95, 70, 50, 80, 60].map((h, i) => (
            <span
              key={i}
              style={{
                height: `${h}%`,
                animationDelay: `${i * 80}ms`,
                animationDuration: '900ms',
              }}
              className="w-0.5 bg-red-400/80 rounded-full animate-pulse"
            />
          ))}
        </div>

        <span className="font-mono text-xs font-semibold text-white/90 ml-1">
          {formatTime(duration)}
        </span>
      </div>

      {/* Right action controls */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="flex items-center gap-1.5 text-xs font-medium text-white/60 hover:text-red-300 px-3 py-1.5 rounded-lg hover:bg-white/5 transition-colors"
          aria-label="Cancel voice note"
        >
          <Trash2 className="h-3.5 w-3.5" />
          <span>Cancel</span>
        </button>
        <button
          type="button"
          onClick={onSend}
          className="flex items-center gap-1.5 bg-[#087CFF] hover:bg-[#0070e0] text-white text-xs font-semibold px-4 py-1.5 rounded-lg shadow transition-colors"
          aria-label="Send voice note"
        >
          <Send className="h-3.5 w-3.5" />
          <span>Send</span>
        </button>
      </div>
    </div>
  );
}
