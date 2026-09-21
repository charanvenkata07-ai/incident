'use client';

import * as React from 'react';

interface HighlightMatchProps {
  text: string | null | undefined;
  query: string;
  className?: string;
}

export function HighlightMatch({ text, query, className = '' }: HighlightMatchProps) {
  if (!text) return null;
  const q = query.trim();
  if (!q) return <span className={className}>{text}</span>;

  // Escape regex special characters
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${escaped})`, 'gi');
  const parts = text.split(regex);

  return (
    <span className={className}>
      {parts.map((part, index) =>
        regex.test(part) ? (
          <mark
            key={index}
            className="bg-blue-100 dark:bg-blue-900/60 text-[#087CFF] dark:text-[#149BFF] font-semibold px-0.5 rounded"
          >
            {part}
          </mark>
        ) : (
          <React.Fragment key={index}>{part}</React.Fragment>
        )
      )}
    </span>
  );
}
