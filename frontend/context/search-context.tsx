'use client';

import * as React from 'react';

export interface PageSearchConfig {
  pageName: string;
  placeholder?: string;
  itemCount: number;
  filteredCount: number;
  onSearch?: (query: string) => void;
}

interface SearchContextType {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  isPaletteOpen: boolean;
  setIsPaletteOpen: (open: boolean) => void;
  openPalette: () => void;
  closePalette: () => void;
  pageSearch: PageSearchConfig | null;
  registerPageSearch: (config: PageSearchConfig) => void;
  unregisterPageSearch: (pageName: string) => void;
  recentSearches: string[];
  addRecentSearch: (term: string) => void;
  clearRecentSearches: () => void;
}

const SearchContext = React.createContext<SearchContextType | undefined>(undefined);

const RECENT_SEARCHES_KEY = 'incidentflow_recent_searches';

export function SearchProvider({ children }: { children: React.ReactNode }) {
  const [searchQuery, setSearchQueryState] = React.useState('');
  const [isPaletteOpen, setIsPaletteOpen] = React.useState(false);
  const [pageSearch, setPageSearch] = React.useState<PageSearchConfig | null>(null);
  const [recentSearches, setRecentSearches] = React.useState<string[]>([]);

  // Load recent searches from localStorage
  React.useEffect(() => {
    try {
      const stored = localStorage.getItem(RECENT_SEARCHES_KEY);
      if (stored) {
        setRecentSearches(JSON.parse(stored));
      }
    } catch {
      // Ignore localStorage errors
    }
  }, []);

  const addRecentSearch = React.useCallback((term: string) => {
    const trimmed = term.trim();
    if (!trimmed) return;
    setRecentSearches((prev) => {
      const next = [trimmed, ...prev.filter((t) => t.toLowerCase() !== trimmed.toLowerCase())].slice(0, 8);
      try {
        localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next));
      } catch {
        // Ignore
      }
      return next;
    });
  }, []);

  const clearRecentSearches = React.useCallback(() => {
    setRecentSearches([]);
    try {
      localStorage.removeItem(RECENT_SEARCHES_KEY);
    } catch {
      // Ignore
    }
  }, []);

  const pageSearchRef = React.useRef<PageSearchConfig | null>(null);
  pageSearchRef.current = pageSearch;

  const searchQueryRef = React.useRef(searchQuery);
  searchQueryRef.current = searchQuery;

  const setSearchQuery = React.useCallback(
    (query: string) => {
      setSearchQueryState(query);
      if (pageSearchRef.current?.onSearch) {
        pageSearchRef.current.onSearch(query);
      }
    },
    []
  );

  const registerPageSearch = React.useCallback((config: PageSearchConfig) => {
    setPageSearch((prev) => {
      if (
        prev &&
        prev.pageName === config.pageName &&
        prev.placeholder === config.placeholder &&
        prev.itemCount === config.itemCount &&
        prev.filteredCount === config.filteredCount
      ) {
        prev.onSearch = config.onSearch;
        return prev;
      }
      return config;
    });
    // If there's an existing query, apply it immediately
    if (config.onSearch && searchQueryRef.current) {
      config.onSearch(searchQueryRef.current);
    }
  }, []);

  const unregisterPageSearch = React.useCallback((pageName: string) => {
    setPageSearch((current) => (current?.pageName === pageName ? null : current));
  }, []);

  const openPalette = React.useCallback(() => setIsPaletteOpen(true), []);
  const closePalette = React.useCallback(() => setIsPaletteOpen(false), []);

  return (
    <SearchContext.Provider
      value={{
        searchQuery,
        setSearchQuery,
        isPaletteOpen,
        setIsPaletteOpen,
        openPalette,
        closePalette,
        pageSearch,
        registerPageSearch,
        unregisterPageSearch,
        recentSearches,
        addRecentSearch,
        clearRecentSearches,
      }}
    >
      {children}
    </SearchContext.Provider>
  );
}

export function useSearch() {
  const context = React.useContext(SearchContext);
  if (!context) {
    throw new Error('useSearch must be used within a SearchProvider');
  }
  return context;
}
