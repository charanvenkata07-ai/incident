import * as React from 'react';
import { Skeleton } from './ui/skeleton';
import { Card, CardContent } from './ui/card';

export function DashboardSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <Skeleton className="h-8 w-64" />
      <Card>
        <CardContent className="p-6 space-y-4">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-4 w-48" />
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <IncidentListSkeleton count={2} />
      </div>
    </div>
  );
}

export function IncidentListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, i) => (
        <Card key={i}>
          <CardContent className="p-4 space-y-3">
            <div className="flex justify-between">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-16" />
            </div>
            <Skeleton className="h-5 w-3/4" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function IncidentDetailSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-8 w-1/3" />
      <Card>
        <CardContent className="p-6 space-y-4">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-10 w-32" />
        </CardContent>
      </Card>
    </div>
  );
}
