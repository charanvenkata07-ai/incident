'use client';

import * as React from 'react';
import { useSearch } from '@/context/search-context';
import { Search, X, Command } from 'lucide-react';

export function GlobalSearchBar() {
  const {
    searchQuery,
    setSearchQuery,
    openPalette,
    pageSearch,
  } = useSearch();

  const [isMac, setIsMac] = React.useState(true);

  React.useEffect(() => {
    setIsMac(navigator.platform.toUpperCase().indexOf('MAC') >= 0);

    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        openPalette();
      }
    };

    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [openPalette]);

  const placeholderText = pageSearch
    ? `Search ${pageSearch.pageName}...`
    : 'Search anything...';

  return (
    <div className="flex items-center">
      {/* Desktop / Laptop Wide Search Field */}
      <div
        onClick={openPalette}
        className="hidden md:flex items-center justify-between w-64 lg:w-80 xl:w-96 h-9 px-3 rounded-xl border border-black/[0.08] dark:border-white/[0.08] bg-zinc-100/70 dark:bg-zinc-900/60 hover:bg-zinc-100 dark:hover:bg-zinc-900 hover:border-[#087CFF]/40 dark:hover:border-[#149BFF]/40 transition-all cursor-pointer group shadow-sm"
      >
        <div className="flex items-center space-x-2.5 min-w-0 pr-2">
          <Search className="w-4 h-4 text-zinc-400 group-hover:text-[#087CFF] dark:group-hover:text-[#149BFF] transition-colors shrink-0" />
          <span className="text-xs text-zinc-500 dark:text-zinc-400 truncate select-none">
            {searchQuery ? (
              <span className="text-zinc-900 dark:text-zinc-100 font-medium">{searchQuery}</span>
            ) : (
              placeholderText
            )}
          </span>
        </div>

        <div className="flex items-center space-x-1 shrink-0">
          {searchQuery ? (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setSearchQuery('');
              }}
              className="p-0.5 rounded text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
              title="Clear"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          ) : (
            <kbd className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-white dark:bg-zinc-800 border border-black/[0.08] dark:border-white/[0.08] text-[10px] font-semibold text-zinc-400 dark:text-zinc-400 select-none shadow-xs group-hover:text-zinc-600 dark:group-hover:text-zinc-300">
              {isMac ? '⌘' : 'Ctrl'} K
            </kbd>
          )}
        </div>
      </div>

      {/* Mobile / Tablet Compact Search Button */}
      <button
        onClick={openPalette}
        className="flex md:hidden items-center justify-center h-9 w-9 rounded-xl border border-black/[0.08] dark:border-white/[0.08] bg-zinc-100/70 dark:bg-zinc-900/60 text-zinc-500 hover:text-[#087CFF] dark:hover:text-[#149BFF] transition-colors"
        title="Search (⌘K)"
      >
        <Search className="w-4 h-4" />
      </button>
    </div>
  );
}
