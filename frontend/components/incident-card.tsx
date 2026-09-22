'use client';

import * as React from 'react';
import { Card, CardContent } from './ui/card';
import { StatusBadge } from './status-badge';
import { Button } from './ui/button';
import { formatRelativeTime } from '@/lib/utils';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { useAcknowledgeIncident, useStartWork, useCompleteWork } from '@/hooks/use-incident';
import { CheckCircle2, Play, CheckCircle, ExternalLink, Check, Users } from 'lucide-react';
import type { IncidentBrief } from '@/types';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';

export function IncidentCard({ incident }: { incident: IncidentBrief }) {
  const [showCompleteConfirm, setShowCompleteConfirm] = React.useState(false);

  const ackMut = useAcknowledgeIncident();
  const startMut = useStartWork();
  const completeMut = useCompleteWork();

  const effectiveState = incident.assignment_status || incident.state;
  const isAssigned = effectiveState === 'ASSIGNED';
  const isAcked = effectiveState === 'ACKNOWLEDGED';
  const isInProgress = effectiveState === 'IN_PROGRESS';
  const isCompleted = ['COMPLETED', 'RESOLVED', 'CLOSED'].includes(effectiveState);

  const taskDescription = incident.work_instructions || incident.short_description;

  const handleComplete = async () => {
    await completeMut.mutateAsync(incident.incident_number);
    setShowCompleteConfirm(false);
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
      <Card className="hover:border-zinc-300 dark:hover:border-zinc-700 transition-colors shadow-sm">
        <CardContent className="p-4 flex flex-col space-y-3">
          {/* Header Row */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="font-mono text-xs font-bold text-zinc-900 dark:text-zinc-100">{incident.incident_number}</span>
              <StatusBadge status={incident.priority} type="priority" />
              <StatusBadge status={effectiveState} type="status" />
            </div>
            {incident.assigned_at && (
              <span
                className="text-xs font-medium text-zinc-500"
                title={new Date(incident.assigned_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
              >
                {formatRelativeTime(incident.assigned_at)}
              </span>
            )}
          </div>

          {/* Group and Short Description */}
          <div>
            {incident.assignment_group && (
              <div className="flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 font-medium mb-1">
                <Users className="h-3 w-3" />
                <span>{incident.assignment_group}</span>
              </div>
            )}
            <h4 className="font-semibold text-sm line-clamp-1 text-zinc-950 dark:text-zinc-50">{incident.short_description}</h4>
          </div>

          {/* YOUR TASK box */}
          <div className="bg-zinc-50 dark:bg-zinc-900/60 p-2.5 rounded-md border border-zinc-200 dark:border-zinc-800 text-xs">
            <span className="font-bold text-zinc-500 uppercase tracking-wider block text-[10px] mb-0.5">Your Task</span>
            <p className="text-zinc-800 dark:text-zinc-200 line-clamp-2 font-medium">{taskDescription}</p>
          </div>

          {/* Action Buttons */}
          <div className="pt-1 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 flex-1">
              {isAssigned && (
                <Button
                  size="sm"
                  variant="outline"
                  className="text-xs h-7 px-2.5 text-blue-600 border-blue-200 hover:bg-blue-50 dark:hover:bg-blue-950/20"
                  onClick={() => ackMut.mutate(incident.incident_number)}
                  disabled={ackMut.isPending}
                >
                  <CheckCircle2 className="mr-1 h-3 w-3" />
                  {ackMut.isPending ? 'Saving...' : 'Acknowledge'}
                </Button>
              )}

              {isAcked && (
                <Button
                  size="sm"
                  variant="outline"
                  className="text-xs h-7 px-2.5 text-amber-600 border-amber-200 hover:bg-amber-50 dark:hover:bg-amber-950/20"
                  onClick={() => startMut.mutate(incident.incident_number)}
                  disabled={startMut.isPending}
                >
                  <Play className="mr-1 h-3 w-3" />
                  {startMut.isPending ? 'Starting...' : 'Start Work'}
                </Button>
              )}

              {isInProgress && (
                <Button
                  size="sm"
                  className="text-xs h-7 px-2.5 bg-green-600 hover:bg-green-700 text-white"
                  onClick={() => setShowCompleteConfirm(true)}
                  disabled={completeMut.isPending}
                >
                  <Check className="mr-1 h-3 w-3" />
                  Complete
                </Button>
              )}

              {isCompleted && (
                <span className="text-xs text-green-600 dark:text-green-400 font-medium flex items-center gap-1">
                  <CheckCircle className="h-3.5 w-3.5" /> Completed
                </span>
              )}
            </div>

            <Button size="sm" variant="ghost" asChild className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground">
              <Link href={`/incidents/${incident.incident_number}`}>
                <ExternalLink className="h-3 w-3 mr-1" /> View
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Completion Confirmation Dialog */}
      <Dialog open={showCompleteConfirm} onOpenChange={setShowCompleteConfirm}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Complete Task on {incident.incident_number}?</DialogTitle>
            <DialogDescription>
              Confirm that you have completed the assigned task:
              <br />
              <strong className="text-foreground mt-1 block font-medium">"{taskDescription}"</strong>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" size="sm" onClick={() => setShowCompleteConfirm(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              className="bg-green-600 hover:bg-green-700 text-white"
              onClick={handleComplete}
              disabled={completeMut.isPending}
            >
              {completeMut.isPending ? 'Completing...' : 'Confirm & Complete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
