'use client';

import { useEffect } from 'react';
import { Button } from '@/components/ui/button';

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('App Error Boundary caught:', error);
  }, [error]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 text-center bg-zinc-50 dark:bg-zinc-950">
      <div className="max-w-md w-full bg-card p-6 rounded-lg border shadow-sm space-y-4">
        <h2 className="text-lg font-bold text-rose-600">Something went wrong</h2>
        <p className="text-xs text-muted-foreground break-all bg-muted p-3 rounded font-mono text-left">
          {error?.message || 'Unknown runtime error'}
        </p>
        <div className="flex gap-2 justify-center">
          <Button size="sm" onClick={() => reset()}>
            Try Again
          </Button>
          <Button size="sm" variant="outline" onClick={() => window.location.href = '/login'}>
            Go to Login
          </Button>
        </div>
      </div>
    </div>
  );
}
