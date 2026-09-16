'use client';

import * as React from 'react';
import { useMyShift } from '@/hooks/use-my-shift';
import { Card, CardContent } from '@/components/ui/card';
import { EmployeeCard } from '@/components/employee-card';
import { StatusBadge } from '@/components/status-badge';
import { Clock } from 'lucide-react';
import { EmptyState } from '@/components/empty-state';
import { Skeleton } from '@/components/ui/skeleton';

export default function MyShiftPage() {
  const { data, isLoading } = useMyShift();

  if (isLoading) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <Skeleton className="h-8 w-48" />
        <Card><CardContent className="h-32" /></Card>
      </div>
    );
  }

  if (!data || !data.shift) {
    return (
      <div className="max-w-5xl mx-auto pt-10">
        <EmptyState icon={Clock} title="No active shift" description="You are not currently assigned to any shift." />
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Your Shift</h1>
      </div>

      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div>
              <h2 className="text-xl font-semibold mb-1">{data.shift.name}</h2>
              <p className="text-muted-foreground">{data.shift.start_time} - {data.shift.end_time} {data.shift.timezone}</p>
            </div>
            <div className="flex items-center space-x-3">
              <StatusBadge status="ON_SHIFT" />
              <StatusBadge status={data.employee.availability_status} type="availability" />
            </div>
          </div>
        </CardContent>
      </Card>

      <div>
        <h3 className="text-lg font-semibold mb-4">Team Status</h3>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <EmployeeCard employee={data.employee} />
        </div>
      </div>
    </div>
  );
}
