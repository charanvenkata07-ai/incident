'use client';

import * as React from 'react';
import { Play, Pause } from 'lucide-react';

interface AudioMessageProps {
  src: string;
  duration?: number;
  isSent: boolean;
}

// Generate a deterministic pseudo-waveform pattern from the source string
function generateWaveformBars(seed: string, count = 28): number[] {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0;
  }
  const bars: number[] = [];
  for (let i = 0; i < count; i++) {
    const pseudo = Math.abs(Math.sin((hash + i * 17) * 0.25));
    // Bar height between 20% and 100%
    const height = Math.round(20 + pseudo * 80);
    bars.push(height);
  }
  return bars;
}

export function AudioMessage({ src, duration, isSent }: AudioMessageProps) {
  const [isPlaying, setIsPlaying] = React.useState(false);
  const [currentTime, setCurrentTime] = React.useState(0);
  const [totalDuration, setTotalDuration] = React.useState(duration || 0);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const waveformRef = React.useRef<HTMLDivElement | null>(null);

  const bars = React.useMemo(() => generateWaveformBars(src, 28), [src]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().catch(() => {});
      setIsPlaying(true);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current && (!totalDuration || isNaN(totalDuration))) {
      setTotalDuration(audioRef.current.duration);
    }
  };

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!waveformRef.current || !audioRef.current || totalDuration <= 0) return;
    const rect = waveformRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, clickX / rect.width));
    const newTime = ratio * totalDuration;
    audioRef.current.currentTime = newTime;
    setCurrentTime(newTime);
  };

  const formatTime = (s: number) => {
    if (isNaN(s) || s < 0) return '0:00';
    const mins = Math.floor(s / 60);
    const secs = Math.floor(s % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const progressRatio = totalDuration > 0 ? Math.min(1, currentTime / totalDuration) : 0;
  const activeBarIndex = Math.floor(progressRatio * bars.length);

  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-2xl min-w-[240px] max-w-[320px] transition-all select-none ${
        isSent ? 'bg-white/10 border border-white/20' : 'bg-[#0F223D] border border-white/10'
      }`}
    >
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={() => setCurrentTime(audioRef.current?.currentTime || 0)}
        onEnded={() => {
          setIsPlaying(false);
          setCurrentTime(0);
        }}
        className="hidden"
      />

      {/* Play / Pause toggle button */}
      <button
        type="button"
        onClick={togglePlay}
        className={`h-9 w-9 rounded-full flex items-center justify-center flex-shrink-0 shadow-md transition-all hover:scale-105 ${
          isSent
            ? 'bg-white text-[#087CFF] hover:bg-white/90'
            : 'bg-[#087CFF] text-white hover:bg-[#0070e0]'
        }`}
        aria-label={isPlaying ? 'Pause voice message' : 'Play voice message'}
      >
        {isPlaying ? (
          <Pause className="h-4 w-4" fill="currentColor" />
        ) : (
          <Play className="h-4 w-4 ml-0.5" fill="currentColor" />
        )}
      </button>

      {/* Waveform track and timer */}
      <div className="flex-1 min-w-0 flex flex-col justify-center gap-1.5">
        <div
          ref={waveformRef}
          onClick={handleSeek}
          className="flex items-center gap-[2.5px] h-7 cursor-pointer py-1 group/wave"
          title="Click to seek"
        >
          {bars.map((barHeight, idx) => {
            const isPlayed = idx <= activeBarIndex;
            return (
              <span
                key={idx}
                style={{ height: `${barHeight}%` }}
                className={`w-[3px] rounded-full transition-all duration-75 ${
                  isPlayed
                    ? isSent
                      ? 'bg-white'
                      : 'bg-[#087CFF]'
                    : isSent
                    ? 'bg-white/30 group-hover/wave:bg-white/40'
                    : 'bg-white/15 group-hover/wave:bg-white/25'
                }`}
              />
            );
          })}
        </div>

        {/* Time footer */}
        <div className="flex items-center justify-between text-[10px] font-mono opacity-70">
          <span>{formatTime(currentTime)}</span>
          <span>{totalDuration > 0 ? formatTime(totalDuration) : 'Voice note'}</span>
        </div>
      </div>
    </div>
  );
}
