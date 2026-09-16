'use client';

import * as React from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useIncident, useAcknowledgeIncident, useStartWork, useCompleteWork } from '@/hooks/use-incident';
import { IncidentDetailSkeleton } from '@/components/skeletons';
import { StatusBadge } from '@/components/status-badge';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ArrowLeft, CheckCircle, Play } from 'lucide-react';
import { formatRelativeTime } from '@/lib/utils';
import { motion } from 'framer-motion';

export default function IncidentDetailPage() {
  const { id } = useParams() as { id: string };
  const router = useRouter();
  
  const { data: incident, isLoading } = useIncident(id);
  const ackMut = useAcknowledgeIncident();
  const startMut = useStartWork();
  const completeMut = useCompleteWork();

  if (isLoading) return <IncidentDetailSkeleton />;
  if (!incident) return <div>Incident not found</div>;

  const isAssigned = incident.state === 'ASSIGNED';
  const isAcked = incident.state === 'ACKNOWLEDGED';
  const isInProgress = incident.state === 'IN_PROGRESS';

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6 max-w-4xl mx-auto">
      <Button variant="ghost" size="sm" onClick={() => router.back()} className="-ml-4 text-muted-foreground">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back
      </Button>

      <div>
        <div className="flex items-center space-x-3 mb-2">
          <h1 className="text-2xl font-bold tracking-tight">{incident.incident_number}</h1>
          <StatusBadge status={incident.priority} type="priority" />
          <StatusBadge status={incident.state} type="status" />
        </div>
        <p className="text-lg font-medium">{incident.short_description}</p>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <div className="md:col-span-2 space-y-6">
          <Card className="bg-zinc-50 dark:bg-zinc-900/50 border-zinc-200 dark:border-zinc-800">
            <CardContent className="p-6">
              <h3 className="font-semibold text-sm text-muted-foreground mb-4">YOUR TASK</h3>
              <div className="prose dark:prose-invert text-sm whitespace-pre-wrap">
                {incident.work_instructions || incident.description || incident.short_description}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <h3 className="font-semibold mb-4">Details</h3>
              <dl className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <dt className="text-muted-foreground">Category</dt>
                  <dd className="font-medium">{incident.category || '-'}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Assignment Group</dt>
                  <dd className="font-medium">{incident.assignment_group || '-'}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Impact</dt>
                  <dd className="font-medium">{incident.impact || '-'}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Opened At</dt>
                  <dd className="font-medium">{incident.opened_at ? formatRelativeTime(incident.opened_at) : '-'}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardContent className="p-6 space-y-4">
              <h3 className="font-semibold">Actions</h3>
              {isAssigned && (
                <Button className="w-full" onClick={() => ackMut.mutate(id)} loading={ackMut.isPending}>
                  <CheckCircle className="mr-2 h-4 w-4" /> Acknowledge
                </Button>
              )}
              {isAcked && (
                <Button className="w-full bg-blue-600 hover:bg-blue-700 text-white" onClick={() => startMut.mutate(id)} loading={startMut.isPending}>
                  <Play className="mr-2 h-4 w-4" /> Start Work
                </Button>
              )}
              {isInProgress && (
                <Button className="w-full bg-green-600 hover:bg-green-700 text-white" onClick={() => completeMut.mutate(id)} loading={completeMut.isPending}>
                  <CheckCircle className="mr-2 h-4 w-4" /> Complete Work
                </Button>
              )}
              {(!isAssigned && !isAcked && !isInProgress) && (
                <p className="text-sm text-muted-foreground">No actions available in current state.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Activity Timeline */}
      {incident.activity_timeline && incident.activity_timeline.length > 0 && (
        <Card>
          <CardContent className="p-6">
            <h3 className="font-semibold mb-6">Activity</h3>
            <div className="relative space-y-0">
              {incident.activity_timeline.map((event, index) => {
                const isLast = index === incident.activity_timeline.length - 1;
                const actionLabels: Record<string, string> = {
                  INCIDENT_CREATED: 'Incident created',
                  INCIDENT_RECEIVED: 'Incident received by IncidentFlow',
                  AUTO_ASSIGN: 'Automatically assigned',
                  MANUAL_ASSIGN: 'Manually assigned',
                  ACKNOWLEDGE: 'Acknowledged',
                  START_WORK: 'Work started',
                  COMPLETE: 'Work completed',
                  REASSIGN: 'Reassigned',
                  UNASSIGN: 'Unassigned',
                  SN_SYNC: 'Synchronized with ServiceNow',
                  SN_SYNC_FAILED: 'ServiceNow sync failed',
                  AUTO_ASSIGN_FAILED: 'Auto-assignment failed',
                  MANUAL_OVERRIDE: 'Manual override',
                };
                const label = actionLabels[event.action] || event.action;
                const actor = event.actor_name || 'System';
                const details = event.new_value 
                  ? (event.new_value as Record<string, unknown>).employee_name 
                    ? `to ${(event.new_value as Record<string, unknown>).employee_name}`
                    : event.reason || ''
                  : event.reason || '';

                return (
                  <div key={event.id} className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <div className="w-2.5 h-2.5 rounded-full bg-zinc-400 dark:bg-zinc-500 mt-1.5 shrink-0" />
                      {!isLast && <div className="w-px h-full bg-zinc-200 dark:bg-zinc-700 min-h-[2rem]" />}
                    </div>
                    <div className="pb-6">
                      <p className="text-sm font-medium">{label}{details ? ` ${details}` : ''}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {actor} · {formatRelativeTime(event.created_at)}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}
