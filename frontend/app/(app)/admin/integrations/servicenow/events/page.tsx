'use client';

import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { apiClient } from '@/lib/api-client';
import { ArrowLeft, RefreshCw, Eye, ShieldCheck, Radio, AlertCircle } from 'lucide-react';
import Link from 'next/link';

interface WebhookEvent {
  id: string;
  incident_number: string;
  sys_id: string;
  event_type: string;
  source: string;
  status: string;
  error_message: string | null;
  created_at: string | null;
  processed_at: string | null;
  payload_sanitized: Record<string, any>;
}

export default function WebhookEventsPage() {
  const [selectedEvent, setSelectedEvent] = React.useState<WebhookEvent | null>(null);

  const { data: events, isLoading, refetch } = useQuery<WebhookEvent[]>({
    queryKey: ['servicenow-webhook-events'],
    queryFn: () => apiClient.get<WebhookEvent[]>('/api/admin/integrations/servicenow/events?limit=50'),
    refetchInterval: 10000,
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16 px-1 sm:px-0">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-4">
        <div className="flex items-center gap-3">
          <Link href="/admin/integrations">
            <Button variant="ghost" size="sm" className="h-9 w-9 p-0">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Webhook Event Inspector</h1>
            <p className="text-xs sm:text-sm text-muted-foreground">
              Audit received ServiceNow incident events with automatic credential masking
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} className="h-9 text-xs gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : !events || events.length === 0 ? (
        <Card className="p-8 text-center text-muted-foreground">
          <Radio className="h-10 w-10 mx-auto mb-2 opacity-40 text-primary" />
          <div className="font-semibold text-sm">No Webhook Events Recorded Yet</div>
          <p className="text-xs mt-1">
            Incoming POST requests from ServiceNow to /api/integrations/servicenow/incidents will appear here in real time.
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {events.map((ev) => (
            <Card key={ev.id} className="shadow-sm hover:border-border/80 transition-colors">
              <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1 overflow-hidden">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-sm font-mono">{ev.incident_number}</span>
                    <Badge variant={ev.status === 'PROCESSED' ? 'default' : (ev.status === 'DUPLICATE' ? 'outline' : 'destructive')} className="text-[10px]">
                      {ev.status}
                    </Badge>
                    <span className="text-xs text-muted-foreground font-mono">sys_id: {ev.sys_id}</span>
                  </div>
                  <div className="text-xs text-muted-foreground flex items-center gap-4 flex-wrap">
                    <span>Type: {ev.event_type}</span>
                    <span>Received: {ev.created_at ? new Date(ev.created_at).toLocaleString() : 'N/A'}</span>
                    {ev.error_message && (
                      <span className="text-rose-500 font-medium">Error: {ev.error_message}</span>
                    )}
                  </div>
                </div>

                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setSelectedEvent(ev)}
                  className="h-8 text-xs shrink-0 gap-1.5 self-end sm:self-center"
                >
                  <Eye className="h-3.5 w-3.5" /> View Details
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* View Details Modal with Sanitized Payload */}
      <Dialog open={!!selectedEvent} onOpenChange={() => setSelectedEvent(null)}>
        <DialogContent className="sm:max-w-2xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-500" />
              Event Details & Sanitized Payload
            </DialogTitle>
            <DialogDescription className="text-xs">
              Event ID: <span className="font-mono">{selectedEvent?.id}</span> (Secrets and tokens automatically redacted)
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto space-y-3 py-2 text-xs">
            <div className="grid grid-cols-2 gap-2 bg-muted/40 p-3 rounded font-mono text-[11px]">
              <div>Incident Number: {selectedEvent?.incident_number}</div>
              <div>ServiceNow Sys ID: {selectedEvent?.sys_id}</div>
              <div>Status: {selectedEvent?.status}</div>
              <div>Source: {selectedEvent?.source}</div>
            </div>

            <div>
              <div className="font-semibold mb-1 text-muted-foreground">Sanitized Ingested Payload:</div>
              <pre className="bg-zinc-950 text-zinc-100 p-3 rounded-lg overflow-x-auto text-[11px] font-mono max-h-72">
                {JSON.stringify(selectedEvent?.payload_sanitized, null, 2)}
              </pre>
            </div>
          </div>

          <DialogFooter>
            <Button size="sm" variant="outline" onClick={() => setSelectedEvent(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
