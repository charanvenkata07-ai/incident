'use client';

import * as React from 'react';
import { useMyWork } from '@/hooks/use-my-work';
import { IncidentListSkeleton } from '@/components/skeletons';
import { IncidentCard } from '@/components/incident-card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { EmptyState } from '@/components/empty-state';
import { ClipboardList } from 'lucide-react';

export default function MyWorkPage() {
  const [filter, setFilter] = React.useState('ACTIVE');
  const { data: incidents, isLoading } = useMyWork();

  const filteredIncidents = React.useMemo(() => {
    if (!incidents) return [];
    if (filter === 'ACTIVE') {
      return incidents.filter(i => ['NEW', 'ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS'].includes(i.state));
    }
    if (filter === 'COMPLETED') {
      return incidents.filter(i => ['COMPLETED', 'RESOLVED', 'CLOSED'].includes(i.state));
    }
    return incidents;
  }, [incidents, filter]);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">My Work</h1>
      </div>

      <Tabs value={filter} onValueChange={setFilter}>
        <TabsList>
          <TabsTrigger value="ACTIVE">Active</TabsTrigger>
          <TabsTrigger value="COMPLETED">Completed</TabsTrigger>
          <TabsTrigger value="ALL">All</TabsTrigger>
        </TabsList>

        <div className="mt-6">
          {isLoading ? (
            <IncidentListSkeleton />
          ) : filteredIncidents.length === 0 ? (
            <EmptyState
              icon={ClipboardList}
              title="No incidents found"
              description={`You have no ${filter.toLowerCase()} incidents.`}
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredIncidents.map(incident => (
                <IncidentCard key={incident.id} incident={incident} />
              ))}
            </div>
          )}
        </div>
      </Tabs>
    </div>
  );
}
