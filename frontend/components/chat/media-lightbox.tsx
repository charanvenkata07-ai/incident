'use client';

import * as React from 'react';
import { X, Download, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';

interface MediaLightboxProps {
  src: string;
  alt: string;
  isOpen: boolean;
  onClose: () => void;
  isVideo?: boolean;
}

export function MediaLightbox({ src, alt, isOpen, onClose, isVideo }: MediaLightboxProps) {
  const [scale, setScale] = React.useState(1);

  React.useEffect(() => {
    if (!isOpen) {
      setScale(1);
      return;
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const zoomIn = () => setScale(s => Math.min(3, s + 0.25));
  const zoomOut = () => setScale(s => Math.max(0.5, s - 0.25));
  const resetZoom = () => setScale(1);

  return (
    <div
      className="fixed inset-0 z-[120] bg-black/90 backdrop-blur-md flex flex-col items-center justify-center p-4 select-none animate-in fade-in duration-200"
      onClick={onClose}
    >
      {/* Top action toolbar */}
      <div
        className="absolute top-4 inset-x-4 flex items-center justify-between pointer-events-auto z-10"
        onClick={e => e.stopPropagation()}
      >
        <span className="text-xs font-medium text-white/80 truncate max-w-sm drop-shadow">
          {alt}
        </span>

        <div className="flex items-center gap-2">
          {!isVideo && (
            <>
              <button
                type="button"
                onClick={zoomOut}
                disabled={scale <= 0.5}
                className="h-9 w-9 rounded-lg bg-black/60 hover:bg-white/20 text-white/80 hover:text-white flex items-center justify-center transition-colors disabled:opacity-40"
                title="Zoom out"
                aria-label="Zoom out"
              >
                <ZoomOut className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={resetZoom}
                className="h-9 px-2.5 rounded-lg bg-black/60 hover:bg-white/20 text-white/80 hover:text-white text-xs font-mono flex items-center justify-center transition-colors"
                title="Reset zoom"
                aria-label="Reset zoom"
              >
                {Math.round(scale * 100)}%
              </button>
              <button
                type="button"
                onClick={zoomIn}
                disabled={scale >= 3}
                className="h-9 w-9 rounded-lg bg-black/60 hover:bg-white/20 text-white/80 hover:text-white flex items-center justify-center transition-colors disabled:opacity-40"
                title="Zoom in"
                aria-label="Zoom in"
              >
                <ZoomIn className="h-4 w-4" />
              </button>
            </>
          )}

          <a
            href={src}
            download={alt || 'media'}
            target="_blank"
            rel="noopener noreferrer"
            className="h-9 w-9 rounded-lg bg-black/60 hover:bg-white/20 text-white/80 hover:text-white flex items-center justify-center transition-colors"
            title="Download original"
            aria-label="Download original"
          >
            <Download className="h-4 w-4" />
          </a>

          <button
            type="button"
            onClick={onClose}
            className="h-9 w-9 rounded-lg bg-black/60 hover:bg-red-500/30 text-white/80 hover:text-red-300 flex items-center justify-center transition-colors"
            title="Close (Esc)"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Main media display */}
      <div
        className="relative max-w-full max-h-full flex items-center justify-center overflow-auto pointer-events-auto"
        onClick={e => e.stopPropagation()}
      >
        {isVideo ? (
          <video
            src={src}
            controls
            autoPlay
            playsInline
            className="max-w-[90vw] max-h-[85vh] rounded-xl shadow-2xl object-contain"
          />
        ) : (
          <img
            src={src}
            alt={alt}
            style={{ transform: `scale(${scale})`, transition: 'transform 150ms ease-out' }}
            className="max-w-[90vw] max-h-[85vh] rounded-xl shadow-2xl object-contain cursor-zoom-in"
            onClick={zoomIn}
          />
        )}
      </div>
    </div>
  );
}
