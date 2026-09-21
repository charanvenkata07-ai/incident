'use client';

import * as React from 'react';
import { FileText, FileSpreadsheet, FileArchive, FileCode, File, Download } from 'lucide-react';
import type { ChatAttachment } from './types';

interface FileMessageProps {
  attachment: ChatAttachment;
  downloadUrl: string;
  isSent?: boolean;
}

export function FileMessage({ attachment, downloadUrl, isSent }: FileMessageProps) {
  const ext = React.useMemo(() => {
    const parts = attachment.file_name.split('.');
    return parts.length > 1 ? parts.pop()?.toLowerCase() || '' : '';
  }, [attachment.file_name]);

  const { Icon, colorClass, bgClass, typeLabel } = React.useMemo(() => {
    if (ext === 'pdf') {
      return { Icon: FileText, colorClass: 'text-rose-400', bgClass: 'bg-rose-500/15', typeLabel: 'PDF' };
    }
    if (['doc', 'docx', 'odt', 'rtf'].includes(ext)) {
      return { Icon: FileText, colorClass: 'text-sky-400', bgClass: 'bg-sky-500/15', typeLabel: 'DOC' };
    }
    if (['xls', 'xlsx', 'csv', 'ods'].includes(ext)) {
      return { Icon: FileSpreadsheet, colorClass: 'text-emerald-400', bgClass: 'bg-emerald-500/15', typeLabel: 'SHEET' };
    }
    if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) {
      return { Icon: FileArchive, colorClass: 'text-amber-400', bgClass: 'bg-amber-500/15', typeLabel: 'ARCHIVE' };
    }
    if (['json', 'yaml', 'yml', 'xml', 'sql', 'log', 'txt', 'md'].includes(ext)) {
      return { Icon: FileCode, colorClass: 'text-cyan-400', bgClass: 'bg-cyan-500/15', typeLabel: ext.toUpperCase() };
    }
    return { Icon: File, colorClass: 'text-slate-300', bgClass: 'bg-slate-500/15', typeLabel: ext ? ext.toUpperCase() : 'FILE' };
  }, [ext]);

  const formattedSize = React.useMemo(() => {
    const bytes = attachment.file_size || 0;
    if (bytes >= 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }, [attachment.file_size]);

  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-xl min-w-[240px] max-w-[340px] border transition-all ${
        isSent
          ? 'bg-white/10 border-white/20 hover:bg-white/15'
          : 'bg-[#0F223D] border-white/10 hover:bg-[#132B4C]'
      }`}
    >
      {/* File type icon badge */}
      <div className={`h-10 w-10 rounded-lg flex flex-col items-center justify-center flex-shrink-0 ${bgClass}`}>
        <Icon className={`h-5 w-5 ${colorClass}`} />
      </div>

      {/* File info */}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold text-white/95 truncate" title={attachment.file_name}>
          {attachment.file_name}
        </p>
        <div className="flex items-center gap-2 mt-0.5 text-[10px] text-white/50 font-mono">
          <span className="font-semibold text-white/70">{typeLabel}</span>
          <span>•</span>
          <span>{formattedSize}</span>
        </div>
      </div>

      {/* Download button */}
      <a
        href={downloadUrl}
        download={attachment.file_name}
        target="_blank"
        rel="noopener noreferrer"
        className={`h-8 w-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-transform hover:scale-105 ${
          isSent
            ? 'bg-white/20 hover:bg-white/30 text-white'
            : 'bg-[#087CFF] hover:bg-[#0070e0] text-white shadow-sm'
        }`}
        title={`Download ${attachment.file_name}`}
        aria-label={`Download ${attachment.file_name}`}
      >
        <Download className="h-4 w-4" />
      </a>
    </div>
  );
}
