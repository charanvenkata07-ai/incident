'use client';

import * as React from 'react';
import { Card, CardContent } from './ui/card';
import { StatusBadge } from './status-badge';
import { Button } from './ui/button';
import { formatRelativeTime } from '@/lib/utils';
import { motion } from 'framer-motion';
import Link from 'next/link';
import type { IncidentBrief } from '@/types';

export function IncidentCard({ incident }: { incident: IncidentBrief }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
      <Card className="hover:border-zinc-300 dark:hover:border-zinc-700 transition-colors">
        <CardContent className="p-4 flex flex-col space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <span className="font-mono text-xs text-muted-foreground">{incident.incident_number}</span>
              <StatusBadge status={incident.priority} type="priority" />
              <StatusBadge status={incident.state} type="status" />
            </div>
            {incident.assigned_at && (
              <span className="text-xs text-muted-foreground">{formatRelativeTime(incident.assigned_at)}</span>
            )}
          </div>
          <h4 className="font-medium text-sm line-clamp-1">{incident.short_description}</h4>
          <div className="pt-2 flex justify-end">
            <Button size="sm" variant="secondary" asChild>
              <Link href={`/incidents/${incident.incident_number}`}>Open</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
