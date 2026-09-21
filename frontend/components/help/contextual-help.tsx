'use client';

import * as React from 'react';
import Link from 'next/link';
import { HelpCircle, X, ExternalLink, Loader2, BookOpen, ShieldAlert } from 'lucide-react';
import { apiClient } from '@/lib/api-client';

interface ContextualHelpData {
  slug: string;
  title: string;
  category_name?: string;
  what_it_does?: string;
  summary?: string;
  hint?: string;
  important_rules?: string[];
  url?: string;
}

interface ContextualHelpProps {
  featureKey: string;
  label?: string;
  className?: string;
  iconOnly?: boolean;
}

export function ContextualHelp({
  featureKey,
  label,
  className = '',
  iconOnly = true,
}: ContextualHelpProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [data, setData] = React.useState<ContextualHelpData | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const popoverRef = React.useRef<HTMLDivElement>(null);

  const fetchHelp = React.useCallback(async () => {
    if (data) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get<ContextualHelpData>(
        `/api/admin/help/contextual/${encodeURIComponent(featureKey)}`
      );
      setData(res);
    } catch (err: any) {
      setError(err?.message || 'Failed to load contextual help');
    } finally {
      setLoading(false);
    }
  }, [featureKey, data]);

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!isOpen) {
      setIsOpen(true);
      fetchHelp();
    } else {
      setIsOpen(false);
    }
  };

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  return (
    <div className={`relative inline-flex items-center ${className}`} ref={popoverRef}>
      <button
        type="button"
        onClick={handleToggle}
        className={`inline-flex items-center gap-1 rounded-full p-1 text-zinc-400 hover:text-[#087CFF] dark:text-zinc-500 dark:hover:text-[#149BFF] hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors focus:outline-none focus:ring-2 focus:ring-[#087CFF]/40 ${
          isOpen ? 'text-[#087CFF] bg-blue-50 dark:bg-blue-950/40' : ''
        }`}
        title={label || `Help for ${featureKey}`}
        aria-label={label || `Help for ${featureKey}`}
      >
        <HelpCircle className="w-4 h-4 shrink-0" />
        {!iconOnly && label && (
          <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400 pr-1">
            {label}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          className="absolute z-50 left-0 sm:left-auto sm:right-0 top-full mt-2 w-80 sm:w-96 rounded-2xl bg-white dark:bg-[#0b1b30] border border-black/[0.08] dark:border-white/[0.1] shadow-2xl p-4 text-left animate-in fade-in zoom-in-95 duration-150"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-start justify-between gap-2 mb-2 pb-2 border-b border-black/[0.06] dark:border-white/[0.06]">
            <div className="flex items-center gap-2 min-w-0">
              <span className="p-1 rounded-lg bg-blue-50 dark:bg-blue-900/30 text-[#087CFF] dark:text-[#149BFF]">
                <BookOpen className="w-4 h-4 shrink-0" />
              </span>
              <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">
                {data?.title || 'Feature Documentation'}
              </h4>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 rounded-lg text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {loading && (
            <div className="flex items-center justify-center py-6 text-zinc-400 space-x-2">
              <Loader2 className="w-4 h-4 animate-spin text-[#087CFF]" />
              <span className="text-xs">Loading guide...</span>
            </div>
          )}

          {error && !loading && (
            <div className="py-3 text-center text-xs text-red-500">
              <ShieldAlert className="w-5 h-5 mx-auto mb-1 text-red-500" />
              {error}
            </div>
          )}

          {data && !loading && (
            <div className="space-y-3">
              {data.category_name && (
                <span className="inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400">
                  {data.category_name}
                </span>
              )}
              <p className="text-xs text-zinc-600 dark:text-zinc-300 leading-relaxed">
                {data.hint || data.summary || data.what_it_does}
              </p>

              {data.important_rules && data.important_rules.length > 0 && (
                <div className="bg-zinc-50 dark:bg-zinc-900/60 p-2.5 rounded-xl border border-black/[0.04] dark:border-white/[0.04]">
                  <div className="text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                    Key Operating Rules:
                  </div>
                  <ul className="text-[11px] text-zinc-600 dark:text-zinc-400 space-y-1 list-disc list-inside">
                    {data.important_rules.slice(0, 3).map((rule, idx) => (
                      <li key={idx} className="leading-snug">{rule}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="pt-2 border-t border-black/[0.06] dark:border-white/[0.06] flex items-center justify-between">
                <Link
                  href={`/admin/help?article=${data.slug}`}
                  onClick={() => setIsOpen(false)}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#087CFF] dark:text-[#149BFF] hover:underline"
                >
                  Open full guide in Help Center
                  <ExternalLink className="w-3.5 h-3.5" />
                </Link>
                <span className="text-[10px] text-zinc-400">Esc to close</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
