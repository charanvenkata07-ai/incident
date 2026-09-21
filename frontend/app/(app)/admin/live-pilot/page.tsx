'use client';

import * as React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import {
  ShieldAlert, ShieldCheck, Play, Pause, RefreshCw, AlertTriangle,
  CheckCircle2, XCircle, Lock, Zap, Clock, Users, ArrowRight, Activity, RotateCcw
} from 'lucide-react';
import Link from 'next/link';
import { ContextualHelp } from '@/components/help/contextual-help';

interface PilotSummary {
  status?: 'OFF' | 'READY' | 'ACTIVE' | 'PAUSED';
  pilot_status?: 'OFF' | 'READY' | 'ACTIVE' | 'PAUSED';
  automation_mode?: string;
  auto_assignment_enabled?: boolean;
  pilot_assignment_group?: string;
  allowed_employees?: string[];
  max_active_assignments?: number;
  failed_syncs?: number;
  dlq_count?: number;
  pilot_config?: {
    enabled?: boolean;
    assignment_group?: string;
    max_active_assignments?: number;
    allowed_employees?: string[];
    require_eligibility?: boolean;
    require_service_now_sync?: boolean;
  };
  metrics?: {
    active_assignments?: number;
    max_allowed?: number;
    total_assigned_today?: number;
    successful_syncs?: number;
    failed_syncs?: number;
    dlq_count?: number;
  };
  active_assignments?: Array<{
    id: string;
    incident_id?: string;
    incident_number: string;
    short_description: string;
    priority: string;
    employee_name?: string;
    assigned_to?: string;
    assigned_at?: string;
    servicenow_sync_status?: string;
    sync_status?: string;
    assignment_type: string;
  }> | number;
}

interface ReadinessReport {
  environment: string;
  automation_mode: string;
  servicenow_url: string;
  servicenow_hostname: string;
  servicenow_reachable: boolean;
  servicenow_authenticated: boolean;
  servicenow_read_access: boolean;
  servicenow_write_test: boolean;
  database_ready: boolean;
  redis_ready: boolean;
  worker_ready: boolean;
  webhook_ready: boolean;
  assignment_engine_ready: boolean;
  audit_ready: boolean;
  audit_logging_active: boolean;
  notification_ready: boolean;
  rollback_ready: boolean;
  fail_closed_guard_active: boolean;
  dlq_operational: boolean;
  pilot_group_configured: boolean;
  pilot_roster_configured: boolean;
  ready_for_live: boolean;
  blocker_reason: string | null;
}

export default function LivePilotControlPage() {
  const queryClient = useQueryClient();

  // Safety Confirmation Modal state
  const [isLiveModalOpen, setIsLiveModalOpen] = React.useState(false);
  const [confirmationPhrase, setConfirmationPhrase] = React.useState('');
  const [isActivating, setIsActivating] = React.useState(false);

  // Config editing state
  const [groupInput, setGroupInput] = React.useState('');
  const [maxActiveInput, setMaxActiveInput] = React.useState(5);
  const [rosterInput, setRosterInput] = React.useState('');
  const [configInitialized, setConfigInitialized] = React.useState(false);

  // 1. Fetch live pilot summary
  const { data: summary, isLoading: isSummaryLoading, refetch: refetchSummary } = useQuery<PilotSummary>({
    queryKey: ['live-pilot-summary'],
    queryFn: () => apiClient.get<PilotSummary>('/api/admin/live-pilot/summary'),
    refetchInterval: 10000,
  });

  // 2. Fetch readiness checklist
  const { data: readiness, isLoading: isReadinessLoading, refetch: refetchReadiness } = useQuery<ReadinessReport>({
    queryKey: ['live-pilot-readiness'],
    queryFn: () => apiClient.get<ReadinessReport>('/api/admin/live-pilot/readiness'),
    refetchInterval: 15000,
  });

  // Synchronize local form when summary loads
  React.useEffect(() => {
    if (summary && !configInitialized) {
      setGroupInput(summary.pilot_config?.assignment_group || summary.pilot_assignment_group || '');
      setMaxActiveInput(summary.pilot_config?.max_active_assignments || summary.max_active_assignments || 5);
      setRosterInput((summary.pilot_config?.allowed_employees || summary.allowed_employees || []).join(', '));
      setConfigInitialized(true);
    }
  }, [summary, configInitialized]);

  // Pause / Resume mutation
  const togglePauseMutation = useMutation({
    mutationFn: async (currentlyPaused: boolean) => {
      const endpoint = currentlyPaused ? '/api/admin/automation/resume' : '/api/admin/automation/pause';
      return apiClient.post(endpoint);
    },
    onSuccess: (_, currentlyPaused) => {
      toast.success(currentlyPaused ? 'Automation resumed' : 'Emergency Pause triggered: All automated assignments halted');
      queryClient.invalidateQueries({ queryKey: ['live-pilot-summary'] });
      queryClient.invalidateQueries({ queryKey: ['live-pilot-readiness'] });
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to update pause state');
    },
  });

  // Mode change mutation (Rollback to SHADOW or DRY_RUN)
  const setModeMutation = useMutation({
    mutationFn: async (targetMode: string) => {
      return apiClient.post('/api/admin/automation/mode', { mode: targetMode });
    },
    onSuccess: (_, targetMode) => {
      toast.success(`Automation mode switched to ${targetMode}`);
      queryClient.invalidateQueries({ queryKey: ['live-pilot-summary'] });
      queryClient.invalidateQueries({ queryKey: ['live-pilot-readiness'] });
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to switch automation mode');
    },
  });

  // Live Activation mutation
  const handleActivateLive = async () => {
    if (confirmationPhrase.trim() !== 'ENABLE LIVE ASSIGNMENT') {
      toast.error('Exact phrase required: ENABLE LIVE ASSIGNMENT');
      return;
    }
    setIsActivating(true);
    try {
      await apiClient.post('/api/admin/automation/mode', {
        mode: 'LIVE',
        confirmed: true,
        confirmation_phrase: confirmationPhrase.trim(),
      });
      // Also ensure pilot config is marked enabled
      await apiClient.patch('/api/admin/live-pilot/config', {
        enabled: true,
      });
      toast.success('CONTROLLED LIVE PILOT ACTIVATED. Outbound mutations enabled for pilot group.');
      setIsLiveModalOpen(false);
      setConfirmationPhrase('');
      queryClient.invalidateQueries({ queryKey: ['live-pilot-summary'] });
      queryClient.invalidateQueries({ queryKey: ['live-pilot-readiness'] });
    } catch (err: any) {
      toast.error(err.message || 'Failed to activate LIVE pilot mode');
    } finally {
      setIsActivating(false);
    }
  };

  // Update pilot config mutation
  const updateConfigMutation = useMutation({
    mutationFn: async () => {
      const rosterList = rosterInput
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      return apiClient.patch('/api/admin/live-pilot/config', {
        assignment_group: groupInput.trim(),
        max_active_assignments: Number(maxActiveInput) || 5,
        allowed_employees: rosterList,
      });
    },
    onSuccess: () => {
      toast.success('Live pilot configuration saved');
      queryClient.invalidateQueries({ queryKey: ['live-pilot-summary'] });
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to save configuration');
    },
  });

  const currentPilotStatus = summary?.status || summary?.pilot_status || 'OFF';
  const isPaused = currentPilotStatus === 'PAUSED' || summary?.auto_assignment_enabled === false;
  const isLiveActive = currentPilotStatus === 'ACTIVE' || (summary?.automation_mode === 'LIVE' && summary?.pilot_config?.enabled);

  return (
    <div className="space-y-6 pb-12">
      {/* HEADER & TOP CONTROLS */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">Controlled LIVE Pilot Management</h1>
            <ContextualHelp featureKey="live_mode" label="Pilot guide" iconOnly={false} />
            {currentPilotStatus === 'ACTIVE' && (
              <Badge className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold animate-pulse">
                ● LIVE PILOT ACTIVE
              </Badge>
            )}
            {currentPilotStatus === 'READY' && (
              <Badge variant="outline" className="border-blue-500 text-blue-600 font-semibold bg-blue-50/50 dark:bg-blue-950/30">
                ● READY FOR PILOT
              </Badge>
            )}
            {currentPilotStatus === 'PAUSED' && (
              <Badge className="bg-rose-600 text-white font-semibold">
                ● AUTOMATION PAUSED
              </Badge>
            )}
            {currentPilotStatus === 'OFF' && (
              <Badge variant="secondary" className="font-semibold">
                ○ PILOT OFF (SHADOW MODE)
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Reversible, auditable, and fail-closed staging pilot. Isolated to designated assignment group and approved employee roster.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Emergency Pause / Resume Button */}
          <Button
            variant={isPaused ? 'default' : 'destructive'}
            size="sm"
            onClick={() => togglePauseMutation.mutate(isPaused)}
            disabled={togglePauseMutation.isPending}
            className="flex items-center gap-2"
          >
            {isPaused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
            {isPaused ? 'Resume Automation' : 'Emergency Pause'}
          </Button>

          {/* Rollback to Shadow */}
          {summary?.automation_mode === 'LIVE' && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setModeMutation.mutate('SHADOW')}
              disabled={setModeMutation.isPending}
              className="flex items-center gap-2 border-amber-500 text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950"
            >
              <RotateCcw className="h-4 w-4" />
              Revert to SHADOW
            </Button>
          )}

          {/* Activate Live Pilot Button */}
          {summary?.automation_mode !== 'LIVE' && (
            <Button
              variant="default"
              size="sm"
              onClick={() => {
                setConfirmationPhrase('');
                setIsLiveModalOpen(true);
              }}
              className="flex items-center gap-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white"
            >
              <Zap className="h-4 w-4" />
              Activate LIVE Pilot
            </Button>
          )}

          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              refetchSummary();
              refetchReadiness();
            }}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* METRIC TELEMETRY CARDS */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-xs">Active Pilot Assignments</CardDescription>
            <CardTitle className="text-2xl font-bold flex items-center justify-between">
              <span>{summary?.metrics?.active_assignments ?? (typeof summary?.active_assignments === 'number' ? summary.active_assignments : 0)}</span>
              <span className="text-xs font-normal text-muted-foreground">
                / {summary?.metrics?.max_allowed ?? summary?.max_active_assignments ?? 5} max
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-xs text-muted-foreground">
            Capacity ceiling guard active
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-xs">Assigned Today</CardDescription>
            <CardTitle className="text-2xl font-bold">
              {summary?.metrics?.total_assigned_today ?? (typeof summary?.active_assignments === 'number' ? summary.active_assignments : 0)}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-xs text-muted-foreground">
            Within pilot group
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-xs">ServiceNow Syncs</CardDescription>
            <CardTitle className="text-2xl font-bold text-emerald-600">
              {summary?.metrics?.successful_syncs ?? 0}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-xs text-muted-foreground">
            Successful outbound mutations
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-xs">Sync Failures</CardDescription>
            <CardTitle className="text-2xl font-bold text-rose-600">
              {summary?.metrics?.failed_syncs ?? summary?.failed_syncs ?? 0}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-xs text-muted-foreground">
            Isolated; incident assigned locally
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-xs">Dead Letter Queue</CardDescription>
            <CardTitle className="text-2xl font-bold text-amber-600">
              {summary?.metrics?.dlq_count ?? summary?.dlq_count ?? 0}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-xs text-muted-foreground">
            <Link href="/admin/integrations" className="hover:underline flex items-center gap-1">
              View DLQ <ArrowRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* PRE-LIVE READINESS CHECKLIST */}
      <Card className="border-t-4 border-t-indigo-500">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-indigo-600" />
                Pre-Live Readiness & Safety Checklist
              </CardTitle>
              <CardDescription>
                Automated gatekeeping checks. All gates must pass before uncontrolled LIVE assignment can proceed.
              </CardDescription>
            </div>
            <div className="text-right">
              <Badge variant={readiness?.ready_for_live ? 'default' : 'destructive'} className="text-sm px-3 py-1">
                {readiness?.ready_for_live ? 'READY FOR LIVE: YES' : 'READY FOR LIVE: NO'}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {!readiness?.ready_for_live && readiness?.blocker_reason && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-300 flex items-start gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Live Mutation Blocker Active</p>
                <p className="text-xs mt-0.5">{readiness.blocker_reason}</p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
            <ChecklistItem
              title="ServiceNow Host Reachable"
              status={readiness?.servicenow_reachable}
              detail={readiness?.servicenow_hostname || 'Not configured'}
            />
            <ChecklistItem
              title="ServiceNow Authentication"
              status={readiness?.servicenow_authenticated}
              detail="Credentials verified"
            />
            <ChecklistItem
              title="Incident Table Read Access"
              status={readiness?.servicenow_read_access}
              detail="Schema mapped 17/17"
            />
            <ChecklistItem
              title="Assignment Group Isolated"
              status={readiness?.pilot_group_configured}
              detail={summary?.pilot_config?.assignment_group || summary?.pilot_assignment_group || 'Not set'}
            />
            <ChecklistItem
              title="Employee Roster Isolated"
              status={readiness?.pilot_roster_configured}
              detail={`${summary?.pilot_config?.allowed_employees?.length || summary?.allowed_employees?.length || 0} approved`}
            />
            <ChecklistItem
              title="Fail-Closed Guard Active"
              status={readiness?.fail_closed_guard_active}
              detail="Non-pilot groups filtered"
            />
            <ChecklistItem
              title="Tamper-Evident Audit Logging"
              status={readiness?.audit_logging_active}
              detail="Actor, ID, and reason tracked"
            />
            <ChecklistItem
              title="Dead Letter Queue Operational"
              status={readiness?.dlq_operational}
              detail="Exponential backoff ready"
            />
            <ChecklistItem
              title="PostgreSQL Concurrency Engine"
              status={readiness?.database_ready}
              detail="Row-level locks active"
            />
            <ChecklistItem
              title="Redis & Background Worker"
              status={readiness?.redis_ready}
              detail="Cache & event pipeline ready"
            />
            <ChecklistItem
              title="In-App & WebSocket Telemetry"
              status={readiness?.notification_ready}
              detail="MY WORK & notifications live"
            />
            <ChecklistItem
              title="Rollback Procedure Verified"
              status={readiness?.rollback_ready}
              detail="Zero data loss on revert"
            />
          </div>
        </CardContent>
      </Card>

      {/* PILOT CONFIGURATION EDITOR & ACTIVE ASSIGNMENTS */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* PILOT CONFIGURATION FORM */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Lock className="h-4 w-4 text-muted-foreground" />
              Pilot Isolation Parameters
            </CardTitle>
            <CardDescription className="text-xs">
              Strict scoping ensures mutations cannot impact production or non-pilot teams.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-zinc-950">Target Assignment Group</label>
              <Input
                value={groupInput}
                onChange={(e) => setGroupInput(e.target.value)}
                placeholder="e.g. Analytics – MDM L3"
              />
              <p className="text-[11px] text-zinc-600">
                All other groups are filtered out with <code>PILOT_GROUP_FILTERED</code>.
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-zinc-950">Max Active Assignments</label>
              <Input
                type="number"
                min={1}
                max={20}
                value={maxActiveInput}
                onChange={(e) => setMaxActiveInput(parseInt(e.target.value) || 1)}
              />
              <p className="text-[11px] text-zinc-600">
                Assigning halts when capacity is reached (<code>PILOT_CAPACITY_REACHED</code>).
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-zinc-950">Approved Employee Roster</label>
              <Input
                value={rosterInput}
                onChange={(e) => setRosterInput(e.target.value)}
                placeholder="ravi@incidentflow.dev, kiran@incidentflow.dev"
              />
              <p className="text-[11px] text-zinc-600">
                Comma-separated emails or codes. Only these engineers can be assigned.
              </p>
            </div>

            <Button
              className="w-full mt-2"
              size="sm"
              onClick={() => updateConfigMutation.mutate()}
              disabled={updateConfigMutation.isPending}
            >
              Save Pilot Configuration
            </Button>
          </CardContent>
        </Card>

        {/* ACTIVE PILOT ASSIGNMENTS TABLE */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <Activity className="h-4 w-4 text-muted-foreground" />
                  Active Pilot Assignments
                </CardTitle>
                <CardDescription className="text-xs">
                  Real-time view of incidents currently under pilot automated assignment.
                </CardDescription>
              </div>
              <Badge variant="outline" className="text-xs">
                {Array.isArray(summary?.active_assignments) ? summary.active_assignments.length : 0} active
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[120px]">Incident</TableHead>
                  <TableHead>Short Description</TableHead>
                  <TableHead>Assigned To</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Sync Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(!Array.isArray(summary?.active_assignments) || summary.active_assignments.length === 0) ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center py-8 text-sm text-muted-foreground">
                      No active pilot assignments at this moment.
                    </TableCell>
                  </TableRow>
                ) : (
                  summary.active_assignments.map((asgn: any) => (
                    <TableRow key={asgn.id}>
                      <TableCell className="font-semibold font-mono text-xs">
                        <Link href={`/incidents/${asgn.incident_id || asgn.id}`} className="hover:underline text-blue-600">
                          {asgn.incident_number}
                        </Link>
                      </TableCell>
                      <TableCell className="text-xs truncate max-w-[200px]" title={asgn.short_description}>
                        {asgn.short_description}
                      </TableCell>
                      <TableCell className="text-xs font-medium">
                        {asgn.employee_name || asgn.assigned_to || 'Assigned'}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px]">
                          {asgn.assignment_type}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {asgn.servicenow_sync_status === 'SYNCED' && (
                          <Badge className="bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 text-[10px]">
                            SYNCED
                          </Badge>
                        )}
                        {asgn.servicenow_sync_status === 'SYNC_FAILED' && (
                          <Badge className="bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300 text-[10px]">
                            FAILED (DLQ)
                          </Badge>
                        )}
                        {asgn.servicenow_sync_status === 'PENDING' && (
                          <Badge variant="secondary" className="text-[10px]">
                            PENDING
                          </Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      {/* SAFETY CONFIRMATION MODAL FOR ACTIVATING LIVE */}
      <Dialog open={isLiveModalOpen} onOpenChange={setIsLiveModalOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-rose-600">
              <ShieldAlert className="h-5 w-5" />
              Controlled LIVE Pilot Activation
            </DialogTitle>
            <DialogDescription className="pt-2 text-sm text-foreground">
              You are about to activate automated LIVE assignment. Outbound assignment mutations will be dispatched to ServiceNow for the configured pilot group:
              <strong className="block mt-1 font-semibold text-rose-600">
                {groupInput || 'Analytics – MDM L3'}
              </strong>
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-200 space-y-1">
              <p className="font-semibold">Mandatory Safety Precautions:</p>
              <ul className="list-disc list-inside space-y-0.5">
                <li>Assignments will only mutate tickets matching the pilot group.</li>
                <li>Roster is strictly limited to approved pilot engineers.</li>
                <li>Fail-closed protection and emergency pause remain active 24/7.</li>
                <li>An immutable audit log will record your identity and request timestamp.</li>
              </ul>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium">
                To proceed, type <span className="font-mono font-bold text-rose-600">ENABLE LIVE ASSIGNMENT</span>:
              </label>
              <Input
                value={confirmationPhrase}
                onChange={(e) => setConfirmationPhrase(e.target.value)}
                placeholder="ENABLE LIVE ASSIGNMENT"
                className="font-mono text-sm"
              />
            </div>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setIsLiveModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={confirmationPhrase.trim() !== 'ENABLE LIVE ASSIGNMENT' || isActivating}
              onClick={handleActivateLive}
              className="bg-rose-600 hover:bg-rose-700"
            >
              {isActivating ? 'Activating...' : 'Confirm & Enable LIVE Assignment'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ChecklistItem({ title, status, detail }: { title: string; status?: boolean; detail: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-zinc-200 bg-white p-2.5">
      <div className="flex items-center gap-2">
        {status ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
        ) : (
          <XCircle className="h-4 w-4 text-rose-500 shrink-0" />
        )}
        <span className="font-semibold text-xs text-zinc-950">{title}</span>
      </div>
      <span className="text-[11px] font-medium text-zinc-700 truncate max-w-[130px]">{detail}</span>
    </div>
  );
}
