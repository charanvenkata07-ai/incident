'use client';

import * as React from 'react';
import { useSearch, PageSearchConfig } from '@/context/search-context';

export interface UsePageSearchOptions {
  pageName: string;
  placeholder?: string;
  itemCount: number;
  filteredCount: number;
  onSearch?: (query: string) => void;
}

export function usePageSearch({
  pageName,
  placeholder,
  itemCount,
  filteredCount,
  onSearch,
}: UsePageSearchOptions) {
  const { searchQuery, setSearchQuery, registerPageSearch, unregisterPageSearch } = useSearch();

  const onSearchRef = React.useRef(onSearch);
  onSearchRef.current = onSearch;

  const stableOnSearch = React.useCallback((query: string) => {
    onSearchRef.current?.(query);
  }, []);

  React.useEffect(() => {
    registerPageSearch({
      pageName,
      placeholder,
      itemCount,
      filteredCount,
      onSearch: onSearch ? stableOnSearch : undefined,
    });

    return () => {
      unregisterPageSearch(pageName);
    };
  }, [pageName, placeholder, itemCount, filteredCount, registerPageSearch, unregisterPageSearch, stableOnSearch, !onSearch]);

  const clearSearch = React.useCallback(() => setSearchQuery(''), [setSearchQuery]);

  return {
    searchQuery,
    setSearchQuery,
    clearSearch,
  };
}
