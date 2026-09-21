'use client';

import * as React from 'react';
import { Paperclip, Mic, Send, X, Image as ImageIcon, Video as VideoIcon, FileText, Loader2 } from 'lucide-react';
import type { ChatAttachment } from './types';

interface MessageComposerProps {
  value: string;
  onChange: (val: string) => void;
  onSubmit: (e?: React.FormEvent) => void;
  onPickMedia: (type: 'image' | 'video' | 'document' | 'all') => void;
  onPasteFile?: (file: File) => void;
  onStartRecording: () => void;
  isSending: boolean;
  isUploadingAttachment: boolean;
  uploadProgress?: number;
  pendingAttachment: ChatAttachment | null;
  onClearAttachment: () => void;
  placeholder: string;
  inputRef: React.RefObject<HTMLInputElement | null>;
}

export function MessageComposer({
  value,
  onChange,
  onSubmit,
  onPickMedia,
  onPasteFile,
  onStartRecording,
  isSending,
  isUploadingAttachment,
  uploadProgress = 0,
  pendingAttachment,
  onClearAttachment,
  placeholder,
  inputRef,
}: MessageComposerProps) {
  const [menuOpen, setMenuOpen] = React.useState(false);
  const menuRef = React.useRef<HTMLDivElement | null>(null);

  // Close menu on click outside
  React.useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [menuOpen]);

  // Handle clipboard paste (Ctrl/Cmd+V)
  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    if (isUploadingAttachment || isSending) return;
    const items = e.clipboardData?.items;
    if (!items) return;

    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind === 'file') {
        const file = item.getAsFile();
        if (file && onPasteFile) {
          e.preventDefault();
          onPasteFile(file);
          return;
        }
      }
    }
  };

  const getAttachmentIcon = () => {
    if (!pendingAttachment) return null;
    if (pendingAttachment.mime_type.startsWith('image/')) {
      return <ImageIcon className="h-4 w-4 text-[#087CFF] flex-shrink-0" />;
    }
    if (pendingAttachment.mime_type.startsWith('video/')) {
      return <VideoIcon className="h-4 w-4 text-purple-400 flex-shrink-0" />;
    }
    return <FileText className="h-4 w-4 text-amber-400 flex-shrink-0" />;
  };

  const formatFileSize = (bytes: number) => {
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${Math.round(bytes / 1024)} KB`;
  };

  return (
    <div className="px-4 py-3 border-t border-white/10 bg-[#071426] flex-shrink-0">
      {/* Upload Progress Bar */}
      {isUploadingAttachment && (
        <div className="mb-2 px-3 py-2 rounded-xl bg-[#0B1B31] border border-white/10 flex items-center gap-3">
          <Loader2 className="h-4 w-4 text-[#087CFF] animate-spin flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex justify-between text-[11px] mb-1">
              <span className="text-white/80 font-medium">Uploading attachment...</span>
              <span className="text-white/60 font-mono">{uploadProgress}%</span>
            </div>
            <div className="h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-[#087CFF] to-[#20C7FF] rounded-full transition-all duration-150"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Pending Attachment Preview Strip */}
      {pendingAttachment && !isUploadingAttachment && (
        <div className="flex items-center gap-2.5 mb-2.5 px-3 py-1.5 rounded-xl bg-[#0B1B31] border border-white/10">
          {getAttachmentIcon()}
          <span className="text-xs text-white/90 truncate flex-1 font-medium">
            {pendingAttachment.file_name}
          </span>
          <span className="text-[10px] text-white/50 font-mono flex-shrink-0">
            {formatFileSize(pendingAttachment.file_size)}
          </span>
          <button
            type="button"
            onClick={onClearAttachment}
            className="h-5 w-5 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center flex-shrink-0 transition-colors"
            title="Remove attachment"
            aria-label="Remove attachment"
          >
            <X className="h-3 w-3 text-white/70" />
          </button>
        </div>
      )}

      <form onSubmit={onSubmit} className="flex items-center gap-2 relative">
        {/* Attachment menu trigger */}
        <div ref={menuRef} className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen(prev => !prev)}
            disabled={isUploadingAttachment || isSending}
            className="h-10 w-10 flex items-center justify-center rounded-xl text-white/50 hover:text-[#20C7FF] hover:bg-white/5 transition-colors flex-shrink-0 disabled:opacity-40"
            title="Attach file"
            aria-label="Attach file"
          >
            <Paperclip className="h-[18px] w-[18px]" />
          </button>

          {/* Attachment type dropdown menu */}
          {menuOpen && (
            <div className="absolute bottom-12 left-0 z-30 w-48 rounded-xl bg-[#0B1B31] border border-white/15 p-1.5 shadow-2xl backdrop-blur-md animate-in fade-in slide-in-from-bottom-2 duration-150">
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onPickMedia('image');
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium text-white/80 hover:text-white hover:bg-white/10 rounded-lg transition-colors text-left"
              >
                <ImageIcon className="h-4 w-4 text-[#087CFF]" />
                <span>Image / Photo</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onPickMedia('video');
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium text-white/80 hover:text-white hover:bg-white/10 rounded-lg transition-colors text-left"
              >
                <VideoIcon className="h-4 w-4 text-purple-400" />
                <span>Video file</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onPickMedia('document');
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium text-white/80 hover:text-white hover:bg-white/10 rounded-lg transition-colors text-left"
              >
                <FileText className="h-4 w-4 text-amber-400" />
                <span>Document / File</span>
              </button>
            </div>
          )}
        </div>

        {/* Voice recorder trigger */}
        <button
          type="button"
          onClick={onStartRecording}
          disabled={isSending || isUploadingAttachment}
          className="h-10 w-10 flex items-center justify-center rounded-xl text-white/50 hover:text-red-400 hover:bg-white/5 transition-colors flex-shrink-0 disabled:opacity-40"
          title="Record voice note"
          aria-label="Record voice note"
        >
          <Mic className="h-[18px] w-[18px]" />
        </button>

        {/* Text Input */}
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          onPaste={handlePaste}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder={placeholder}
          disabled={isSending}
          className="flex-1 h-10 bg-[#0B1B31] border border-white/10 rounded-xl px-4 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-[#087CFF]/50 transition-colors"
        />

        {/* Send button */}
        <button
          type="submit"
          disabled={(!value.trim() && !pendingAttachment) || isSending || isUploadingAttachment}
          className="h-10 w-10 flex items-center justify-center bg-[#087CFF] hover:bg-[#0070e0] disabled:opacity-40 text-white rounded-xl transition-colors flex-shrink-0 shadow-sm"
          title="Send message"
          aria-label="Send message"
        >
          {isSending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </form>
    </div>
  );
}
