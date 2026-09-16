'use client';

import * as React from 'react';
import { useAuth } from '@/hooks/use-auth';
import { useMyWork } from '@/hooks/use-my-work';
import { useMyShift } from '@/hooks/use-my-shift';
import { DashboardSkeleton } from '@/components/skeletons';
import { IncidentCard } from '@/components/incident-card';
import { EmptyState } from '@/components/empty-state';
import { CheckCircle2, Clock } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { StatusBadge } from '@/components/status-badge';
import { getGreeting, formatDate } from '@/lib/utils';

export default function DashboardPage() {
  const { user } = useAuth();
  const { data: myWork, isLoading: workLoading } = useMyWork();
  const { data: myShift, isLoading: shiftLoading } = useMyShift();

  if (workLoading || shiftLoading) return <DashboardSkeleton />;

  const activeIncidents = myWork?.filter(i => ['NEW', 'ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS'].includes(i.state)) || [];

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{getGreeting()}, {user?.full_name?.split(' ')[0]}</h1>
        <p className="text-muted-foreground">{formatDate(new Date().toISOString())}</p>
      </div>

      <Card>
        <CardContent className="p-6 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className="p-3 bg-zinc-100 dark:bg-zinc-800 rounded-full">
              <Clock className="h-6 w-6" />
            </div>
            <div>
              <h3 className="font-semibold">{myShift ? 'On Shift' : 'Off Shift'}</h3>
              <p className="text-sm text-muted-foreground">
                {myShift ? `${myShift.shift.start_time} - ${myShift.shift.end_time} ${myShift.shift.timezone}` : 'No active shift'}
              </p>
            </div>
          </div>
          {myShift && <StatusBadge status={myShift.employee.availability_status} type="availability" />}
        </CardContent>
      </Card>

      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Your Work</h2>
          <div className="flex space-x-2 text-sm text-muted-foreground">
            <span>{activeIncidents.length} active</span>
          </div>
        </div>
        
        {activeIncidents.length === 0 ? (
          <EmptyState
            icon={CheckCircle2}
            title="You're all caught up"
            description="No active incidents assigned to you at the moment."
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {activeIncidents.map(incident => (
              <IncidentCard key={incident.id} incident={incident} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
