'use client';

import * as React from 'react';
import { AlertCircle } from 'lucide-react';
import { Button } from './ui/button';

export function ErrorDisplay({ error, retry }: { error: any; retry?: () => void }) {
  const message = error?.message || 'Something went wrong. Please try again.';
  
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <AlertCircle className="h-8 w-8 text-destructive mb-4" />
      <h3 className="text-lg font-semibold mb-2 text-destructive">Error Loading Data</h3>
      <p className="text-sm text-muted-foreground mb-6 max-w-sm">{message}</p>
      {retry && (
        <Button onClick={retry} variant="outline">
          Try Again
        </Button>
      )}
    </div>
  );
}
