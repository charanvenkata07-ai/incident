'use client';

import * as React from 'react';
import { useMyWork } from '@/hooks/use-my-work';
import { IncidentListSkeleton } from '@/components/skeletons';
import { IncidentCard } from '@/components/incident-card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { EmptyState } from '@/components/empty-state';
import { ClipboardList } from 'lucide-react';

import { usePageSearch } from '@/hooks/use-page-search';

export default function MyWorkPage() {
  const [filter, setFilter] = React.useState('ACTIVE');
  const [localSearch, setLocalSearch] = React.useState('');
  const { data: incidents, isLoading } = useMyWork();

  const filteredIncidents = React.useMemo(() => {
    if (!Array.isArray(incidents)) return [];
    if (filter === 'ACTIVE') {
      return incidents.filter(i => i && ['NEW', 'ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS'].includes(i.state));
    }
    if (filter === 'COMPLETED') {
      return incidents.filter(i => i && ['COMPLETED', 'RESOLVED', 'CLOSED'].includes(i.state));
    }
    return incidents;
  }, [incidents, filter]);

  const searchedIncidents = React.useMemo(() => {
    const q = localSearch.trim().toLowerCase();
    if (!q) return filteredIncidents;
    return filteredIncidents.filter((inc) => {
      return (
        inc.incident_number?.toLowerCase().includes(q) ||
        inc.short_description?.toLowerCase().includes(q) ||
        inc.priority?.toLowerCase().includes(q) ||
        inc.assignment_group?.toLowerCase().includes(q) ||
        inc.state?.toLowerCase().includes(q)
      );
    });
  }, [filteredIncidents, localSearch]);

  const { searchQuery, setSearchQuery } = usePageSearch({
    pageName: 'My Work',
    placeholder: 'Filter my work on this page...',
    itemCount: filteredIncidents.length,
    filteredCount: searchedIncidents.length,
    onSearch: (q) => setLocalSearch(q),
  });

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
          ) : searchedIncidents.length === 0 ? (
            <EmptyState
              icon={ClipboardList}
              title={localSearch ? "No matching work items" : "No incidents found"}
              description={localSearch ? `No work items match "${localSearch}" on this page.` : `You have no ${filter.toLowerCase()} incidents.`}
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {searchedIncidents.map(incident => (
                <IncidentCard key={incident.id} incident={incident} />
              ))}
            </div>
          )}
        </div>
      </Tabs>
    </div>
  );
}
