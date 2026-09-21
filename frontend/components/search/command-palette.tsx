'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useSearch } from '@/context/search-context';
import { apiClient } from '@/lib/api-client';
import { HighlightMatch } from './highlight-match';
import {
  Search,
  X,
  AlertCircle,
  Clock,
  Shield,
  Users,
  MessageSquare,
  Briefcase,
  CheckCircle2,
  FileText,
  Bell,
  ArrowRight,
  CornerDownLeft,
  Layers,
  Sparkles,
  Loader2,
  ExternalLink,
  HelpCircle
} from 'lucide-react';

interface SearchResults {
  query: string;
  total_count: number;
  categories: {
    incidents: any[];
    employees: any[];
    teams: any[];
    work: any[];
    chat: any[];
    notifications: any[];
    tasks: any[];
    help?: any[];
  };
}

export function CommandPalette() {
  const router = useRouter();
  const {
    searchQuery,
    setSearchQuery,
    isPaletteOpen,
    closePalette,
    pageSearch,
    recentSearches,
    addRecentSearch,
    clearRecentSearches,
  } = useSearch();

  const [activeScope, setActiveScope] = React.useState<string>('all');
  const [results, setResults] = React.useState<SearchResults | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [hasError, setHasError] = React.useState(false);
  const [selectedIndex, setSelectedIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const listRef = React.useRef<HTMLDivElement>(null);

  // Focus input on open
  React.useEffect(() => {
    if (isPaletteOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isPaletteOpen]);

  // Debounced API search
  React.useEffect(() => {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      setResults(null);
      setIsLoading(false);
      setHasError(false);
      return;
    }

    setIsLoading(true);
    setHasError(false);
    const handler = setTimeout(async () => {
      try {
        const data = await apiClient.get<SearchResults>(
          `/api/search?q=${encodeURIComponent(trimmed)}&scope=${activeScope}&limit=8`
        );
        setResults(data);
        setSelectedIndex(0);
      } catch (err) {
        setHasError(true);
      } finally {
        setIsLoading(false);
      }
    }, 200);

    return () => clearTimeout(handler);
  }, [searchQuery, activeScope]);

  // Flattened list of clickable items for keyboard navigation
  const flatItems = React.useMemo(() => {
    const list: { id: string; type: string; title: string; subtitle?: string; url: string; badge?: string }[] = [];

    // 1. Page Search quick action (if on an active searchable page)
    if (pageSearch && searchQuery.trim()) {
      list.push({
        id: 'page_search_action',
        type: 'PAGE',
        title: `Filter on current page: ${pageSearch.pageName}`,
        subtitle: `${pageSearch.filteredCount} match${pageSearch.filteredCount === 1 ? '' : 'es'} found out of ${pageSearch.itemCount}`,
        url: '#current-page',
        badge: 'This Page',
      });
    }

    if (!results) return list;

    // 2. Global Results
    const cats = results.categories;
    if (activeScope === 'all' || activeScope === 'incidents') {
      cats.incidents.forEach((inc) => {
        list.push({
          id: `inc_${inc.id}`,
          type: 'INCIDENT',
          title: `${inc.incident_number} — ${inc.short_description}`,
          subtitle: `${inc.assignment_group || 'Assignment Pending'} · ${inc.priority} · ${inc.state}`,
          url: inc.url,
          badge: inc.priority,
        });
      });
    }

    if (activeScope === 'all' || activeScope === 'employees') {
      cats.employees.forEach((emp) => {
        list.push({
          id: `emp_${emp.id}`,
          type: 'EMPLOYEE',
          title: emp.full_name,
          subtitle: `${emp.team_name || 'No Team'} · ${emp.employee_code || ''} · ${emp.availability_status}`,
          url: emp.url,
          badge: emp.is_group_leader ? 'Leader' : emp.availability_status,
        });
      });
    }

    if (activeScope === 'all' || activeScope === 'teams') {
      cats.teams.forEach((t) => {
        list.push({
          id: `team_${t.id}`,
          type: 'TEAM',
          title: t.name,
          subtitle: t.work_domain || t.description || 'IncidentFlow Team',
          url: t.url,
          badge: 'Team',
        });
      });
    }

    if (activeScope === 'all' || activeScope === 'work') {
      cats.work.forEach((w) => {
        list.push({
          id: `work_${w.id}`,
          type: 'WORK',
          title: `${w.incident_number || 'Work Item'}: ${w.short_description || ''}`,
          subtitle: `Status: ${w.status} · Priority: ${w.priority || 'Standard'}`,
          url: w.url,
          badge: w.status,
        });
      });
    }

    if (activeScope === 'all' || activeScope === 'chat') {
      cats.chat.forEach((c) => {
        list.push({
          id: `chat_${c.id}`,
          type: 'CHAT',
          title: `${c.sender_name}: "${c.content}"`,
          subtitle: `In ${c.conversation_title} (${c.conversation_type})`,
          url: c.url,
          badge: c.conversation_type,
        });
      });
    }

    if (activeScope === 'all' || activeScope === 'tasks') {
      cats.tasks.forEach((t) => {
        list.push({
          id: `task_${t.id}`,
          type: 'TASK',
          title: t.title,
          subtitle: `${t.team_name || 'Global'} · ${t.description || ''}`,
          url: t.url,
          badge: t.priority,
        });
      });
    }

    if (activeScope === 'all' || activeScope === 'notifications') {
      cats.notifications.forEach((n) => {
        list.push({
          id: `notif_${n.id}`,
          type: 'NOTIFICATION',
          title: n.title,
          subtitle: n.message,
          url: n.url,
          badge: n.notification_type,
        });
      });
    }

    if (activeScope === 'all' || activeScope === 'help') {
      cats.help?.forEach((h) => {
        list.push({
          id: `help_${h.id || h.slug}`,
          type: 'HELP',
          title: h.title,
          subtitle: h.category_name ? `${h.category_name} · ${h.summary || ''}` : h.summary,
          url: h.url || `/admin/help?article=${h.slug}`,
          badge: 'Help Doc',
        });
      });
    }

    return list;
  }, [pageSearch, results, activeScope, searchQuery]);

  const handleSelect = (item: (typeof flatItems)[0]) => {
    if (searchQuery.trim()) {
      addRecentSearch(searchQuery.trim());
    }
    closePalette();
    if (item.url && item.url !== '#current-page') {
      router.push(item.url);
    }
  };

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      closePalette();
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (flatItems.length > 0 ? (prev + 1) % flatItems.length : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (flatItems.length > 0 ? (prev - 1 + flatItems.length) % flatItems.length : 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (flatItems.length > 0 && flatItems[selectedIndex]) {
        handleSelect(flatItems[selectedIndex]);
      }
    }
  };

  const getCategoryIcon = (type: string) => {
    switch (type) {
      case 'PAGE':
        return <Layers className="w-4 h-4 text-emerald-500" />;
      case 'INCIDENT':
        return <AlertCircle className="w-4 h-4 text-red-500" />;
      case 'EMPLOYEE':
        return <Users className="w-4 h-4 text-[#087CFF]" />;
      case 'TEAM':
        return <Shield className="w-4 h-4 text-purple-500" />;
      case 'WORK':
        return <Briefcase className="w-4 h-4 text-amber-500" />;
      case 'CHAT':
        return <MessageSquare className="w-4 h-4 text-cyan-500" />;
      case 'TASK':
        return <FileText className="w-4 h-4 text-blue-500" />;
      case 'NOTIFICATION':
        return <Bell className="w-4 h-4 text-orange-500" />;
      case 'HELP':
        return <HelpCircle className="w-4 h-4 text-purple-600" />;
      default:
        return <Search className="w-4 h-4 text-zinc-400" />;
    }
  };

  if (!isPaletteOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-14 md:pt-20 px-3 md:px-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={closePalette}
    >
      <div
        className="w-full max-w-2xl bg-white dark:bg-[#071426] rounded-2xl shadow-2xl border border-black/[0.08] dark:border-white/[0.08] overflow-hidden flex flex-col max-h-[80vh] transition-all"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Search Header */}
        <div className="relative flex items-center px-4 py-3.5 border-b border-black/[0.08] dark:border-white/[0.08]">
          <Search className="w-5 h-5 text-zinc-400 shrink-0 mr-3" />
          <input
            ref={inputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={
              pageSearch
                ? `Search on this page (${pageSearch.pageName}) or global IncidentFlow...`
                : 'Search anything across IncidentFlow...'
            }
            className="w-full bg-transparent text-base md:text-lg font-medium text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="p-1 rounded-lg text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 mr-2"
              title="Clear search"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={closePalette}
            className="px-2 py-1 text-xs font-semibold rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700"
          >
            ESC
          </button>
        </div>

        {/* Scope Filter Tabs */}
        <div className="flex items-center space-x-1.5 px-4 py-2 border-b border-black/[0.06] dark:border-white/[0.06] overflow-x-auto text-xs scrollbar-none bg-zinc-50/50 dark:bg-zinc-900/40">
          {[
            { id: 'all', label: 'All Results' },
            { id: 'incidents', label: 'Incidents' },
            { id: 'employees', label: 'Employees' },
            { id: 'teams', label: 'Teams' },
            { id: 'work', label: 'My Work' },
            { id: 'chat', label: 'Chat' },
            { id: 'tasks', label: 'Task Catalog' },
            { id: 'notifications', label: 'Notifications' },
            { id: 'help', label: 'Help Docs' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveScope(tab.id)}
              className={`px-2.5 py-1 rounded-full font-medium whitespace-nowrap transition-colors ${
                activeScope === tab.id
                  ? 'bg-[#087CFF] text-white shadow-sm'
                  : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200/60 dark:hover:bg-zinc-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Results Container */}
        <div ref={listRef} className="flex-1 overflow-y-auto p-2 space-y-1">
          {/* Loading Indicator */}
          {isLoading && (
            <div className="flex items-center justify-center py-10 text-zinc-500 dark:text-zinc-400 space-x-2">
              <Loader2 className="w-5 h-5 animate-spin text-[#087CFF]" />
              <span className="text-sm">Searching authorized records...</span>
            </div>
          )}

          {/* Error State */}
          {hasError && !isLoading && (
            <div className="p-6 text-center">
              <AlertCircle className="w-8 h-8 text-red-500 mx-auto mb-2" />
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                Search couldn't be completed
              </p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                Please verify your network connection and try again.
              </p>
              <button
                onClick={() => setSearchQuery(searchQuery + ' ')}
                className="mt-3 px-3 py-1.5 text-xs font-semibold bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded-xl"
              >
                Retry Search
              </button>
            </div>
          )}

          {/* Empty Query / Recent Searches */}
          {!searchQuery.trim() && !isLoading && (
            <div className="py-4 px-3">
              {pageSearch && (
                <div className="mb-4 p-3 rounded-xl bg-blue-50/60 dark:bg-blue-950/30 border border-blue-100 dark:border-blue-900/40">
                  <div className="flex items-center space-x-2 text-xs font-semibold text-[#087CFF] dark:text-[#149BFF]">
                    <Layers className="w-4 h-4" />
                    <span>Active Page: {pageSearch.pageName}</span>
                  </div>
                  <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">
                    Start typing to filter {pageSearch.itemCount} item{pageSearch.itemCount === 1 ? '' : 's'} on this page or search all of IncidentFlow.
                  </p>
                </div>
              )}

              {recentSearches.length > 0 && (
                <div>
                  <div className="flex items-center justify-between text-xs font-semibold text-zinc-500 dark:text-zinc-400 px-1 mb-2">
                    <span className="flex items-center space-x-1.5">
                      <Clock className="w-3.5 h-3.5" />
                      <span>Recent Searches</span>
                    </span>
                    <button
                      onClick={clearRecentSearches}
                      className="text-[11px] text-zinc-400 hover:text-red-500 transition-colors"
                    >
                      Clear
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {recentSearches.map((term, i) => (
                      <button
                        key={i}
                        onClick={() => setSearchQuery(term)}
                        className="px-3 py-1.5 text-xs rounded-xl bg-zinc-100 dark:bg-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors"
                      >
                        {term}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="mt-6 pt-4 border-t border-black/[0.04] dark:border-white/[0.04] text-center text-xs text-zinc-400 dark:text-zinc-500">
                <span>Tip: Press </span>
                <kbd className="px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-[10px] font-mono">↑</kbd>
                <span> </span>
                <kbd className="px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-[10px] font-mono">↓</kbd>
                <span> to navigate, </span>
                <kbd className="px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-[10px] font-mono">Enter</kbd>
                <span> to open</span>
              </div>
            </div>
          )}

          {/* No Results State */}
          {searchQuery.trim() && !isLoading && !hasError && flatItems.length === 0 && (
            <div className="py-12 px-4 text-center">
              <Sparkles className="w-8 h-8 text-zinc-400 mx-auto mb-2 opacity-60" />
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                No results found for &ldquo;{searchQuery}&rdquo;
              </p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 max-w-sm mx-auto">
                Try searching for an incident number (e.g. INC0010245), employee name, team, task, or chat keyword.
              </p>
            </div>
          )}

          {/* Render List of Results */}
          {!isLoading && !hasError && flatItems.length > 0 && (
            <div className="space-y-0.5">
              {flatItems.map((item, idx) => {
                const isSelected = idx === selectedIndex;
                return (
                  <div
                    key={item.id}
                    onClick={() => handleSelect(item)}
                    onMouseEnter={() => setSelectedIndex(idx)}
                    className={`flex items-center justify-between px-3.5 py-2.5 rounded-xl cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-blue-50 dark:bg-blue-950/50 text-[#087CFF] dark:text-[#149BFF]'
                        : 'text-zinc-900 dark:text-zinc-100 hover:bg-zinc-100/70 dark:hover:bg-zinc-800/60'
                    }`}
                  >
                    <div className="flex items-center space-x-3 min-w-0 pr-3">
                      <div className="p-2 rounded-lg bg-zinc-100 dark:bg-zinc-800 shrink-0">
                        {getCategoryIcon(item.type)}
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-medium leading-snug truncate">
                          <HighlightMatch text={item.title} query={searchQuery} />
                        </div>
                        {item.subtitle && (
                          <div className="text-xs text-zinc-500 dark:text-zinc-400 truncate mt-0.5">
                            <HighlightMatch text={item.subtitle} query={searchQuery} />
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center space-x-2 shrink-0">
                      {item.badge && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 border border-black/[0.04] dark:border-white/[0.04]">
                          {item.badge}
                        </span>
                      )}
                      <ArrowRight className={`w-4 h-4 transition-transform ${isSelected ? 'translate-x-0.5 opacity-100' : 'opacity-0'}`} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2.5 bg-zinc-50 dark:bg-[#061120] border-t border-black/[0.06] dark:border-white/[0.06] flex items-center justify-between text-[11px] text-zinc-500 dark:text-zinc-400">
          <div className="flex items-center space-x-3">
            <span className="flex items-center space-x-1">
              <kbd className="px-1 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 font-mono text-[9px]">↑↓</kbd>
              <span>Navigate</span>
            </span>
            <span className="flex items-center space-x-1">
              <kbd className="px-1 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 font-mono text-[9px]">↵</kbd>
              <span>Select</span>
            </span>
            <span className="flex items-center space-x-1">
              <kbd className="px-1 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 font-mono text-[9px]">ESC</kbd>
              <span>Close</span>
            </span>
          </div>
          {results && results.total_count > 0 && (
            <span className="font-medium text-zinc-700 dark:text-zinc-300">
              {results.total_count} result{results.total_count === 1 ? '' : 's'} across IncidentFlow
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
