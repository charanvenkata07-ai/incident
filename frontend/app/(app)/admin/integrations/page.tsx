'use client';

import * as React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import {
  Activity, CheckCircle2, AlertTriangle, XCircle, RefreshCw,
  Server, Shield, Radio, ArrowRight, Eye, ShieldAlert, Zap,
  Play, Pause, Lock, ShieldCheck
} from 'lucide-react';
import Link from 'next/link';

interface IntegrationStatus {
  connection_status: string;
  connection_code: string;
  environment: string;
  current_mode: string;
  servicenow_hostname: string;
  last_successful_connection: string | null;
  last_connection_attempt: string | null;
  latency_ms: number | null;
  api_health: string;
  webhook_health: string;
  webhook_endpoint: string;
  last_webhook_received: string | null;
  last_incident_number: string | null;
  events_today: number;
  duplicate_events: number;
  failed_events: number;
  successful_syncs: number;
  pending_retries: number;
  failed_syncs: number;
  dead_letter_events: number;
  config_checklist: {
    servicenow_url: { configured: boolean; verified: boolean; status: string };
    authentication: { configured: boolean; verified: boolean; status: string };
    webhook_secret: { configured: boolean; verified: boolean; status: string };
    app_base_url: { configured: boolean; verified: boolean; status: string };
    assignment_group: { configured: boolean; verified: boolean; status: string };
    readonly_connection: { configured: boolean; verified: boolean; status: string };
    real_staging_e2e: { configured: boolean; verified: boolean; status: string };
    smtp_configured: { configured: boolean; verified: boolean; status: string };
  };
}

interface DiagnosticsData {
  incident_table_read: string;
  assignment_group_read: string;
  user_read: string;
  required_fields_read: string;
  overall_status: string;
  reason?: string;
}

export default function AdminIntegrationsPage() {
  const queryClient = useQueryClient();
  const [isTestModalOpen, setIsTestModalOpen] = React.useState(false);
  const [testResult, setTestResult] = React.useState<any>(null);
  const [isTesting, setIsTesting] = React.useState(false);

  // Live Activation Safety Modal state
  const [isLiveModalOpen, setIsLiveModalOpen] = React.useState(false);
  const [typedConfirmation, setTypedConfirmation] = React.useState('');
  const [isActivatingLive, setIsActivatingLive] = React.useState(false);

  // Diagnostics state
  const [diagnosticsData, setDiagnosticsData] = React.useState<DiagnosticsData | null>(null);
  const [isRunningDiagnostics, setIsRunningDiagnostics] = React.useState(false);

  // DLQ view state
  const [isDlqModalOpen, setIsDlqModalOpen] = React.useState(false);
  const [dlqItems, setDlqItems] = React.useState<any[]>([]);

  // 1. Fetch integration status
  const { data: status, isLoading, refetch } = useQuery<IntegrationStatus>({
    queryKey: ['servicenow-integration-status'],
    queryFn: () => apiClient.get<IntegrationStatus>('/api/admin/integrations/servicenow/status'),
    refetchInterval: 15000,
  });

  // 2. Test Connection
  const handleTestConnection = async () => {
    setIsTesting(true);
    setIsTestModalOpen(true);
    setTestResult(null);
    try {
      const res = await apiClient.post<any>('/api/admin/integrations/servicenow/test-connection');
      setTestResult(res);
      if (res.status === 'connected') {
        toast.success(`Connected to ${res.target_hostname} (${res.latency_ms}ms)`);
      } else if (res.status === 'auth_failed') {
        toast.error('Authentication Failed: Check credentials in .env');
      } else if (res.status === 'unconfigured') {
        toast.warning('Not Configured: Set SERVICENOW_URL in .env');
      } else {
        toast.error(`Connection Failed: ${res.error || res.message || 'Unavailable'}`);
      }
      refetch();
    } catch (err: any) {
      setTestResult({
        status: 'error',
        result: 'REQUEST_FAILED',
        error: err?.message || 'Failed to call connection test API'
      });
      toast.error('Connection request failed');
    } finally {
      setIsTesting(false);
    }
  };

  // 3. Run Diagnostics
  const handleRunDiagnostics = async () => {
    setIsRunningDiagnostics(true);
    try {
      const data = await apiClient.get<DiagnosticsData>('/api/admin/integrations/servicenow/diagnostics');
      setDiagnosticsData(data);
      if (data.overall_status === 'PASS') {
        toast.success('All ServiceNow permissions verified (Read-Only)');
      } else {
        toast.warning('Some permissions are missing or unconfigured');
      }
    } catch (err: any) {
      toast.error(err?.message || 'Diagnostics failed');
    } finally {
      setIsRunningDiagnostics(false);
    }
  };

  // 4. Retry Sync Failures
  const handleRetryAllFailures = async () => {
    try {
      toast.info('Triggering sync retry cycle...');
      const res = await apiClient.post<any>('/api/admin/integrations/servicenow/sync');
      toast.success(res.message || 'Sync retry cycle triggered');
      refetch();
    } catch (err: any) {
      toast.error(err?.message || 'Failed to trigger sync');
    }
  };

  // 5. Open DLQ Modal
  const handleOpenDlq = async () => {
    setIsDlqModalOpen(true);
    try {
      const items = await apiClient.get<any[]>('/api/admin/integrations/failures?status_filter=DEAD_LETTER');
      setDlqItems(Array.isArray(items) ? items : []);
    } catch {
      setDlqItems([]);
    }
  };

  // 6. Retry single failure
  const handleRetrySingle = async (failureId: string) => {
    try {
      await apiClient.post(`/api/admin/integrations/failures/${failureId}/retry`);
      toast.success('Failure re-queued for retry');
      handleOpenDlq();
      refetch();
    } catch (err: any) {
      toast.error(err?.message || 'Retry failed');
    }
  };

  // 7. LIVE Mode Switch with Typed Confirmation Phrase
  const handleActivateLive = async () => {
    if (typedConfirmation !== 'ENABLE LIVE ASSIGNMENT') {
      toast.error("Confirmation phrase does not match 'ENABLE LIVE ASSIGNMENT'");
      return;
    }
    setIsActivatingLive(true);
    try {
      await apiClient.post('/api/admin/automation/mode', {
        mode: 'LIVE',
        confirmed: true,
        confirmation_phrase: typedConfirmation
      });
      toast.success('System switched to LIVE Assignment Mode');
      setIsLiveModalOpen(false);
      setTypedConfirmation('');
      refetch();
    } catch (err: any) {
      toast.error(err?.message || 'Failed to switch to LIVE mode');
    } finally {
      setIsActivatingLive(false);
    }
  };

  const handleSwitchMode = async (targetMode: string) => {
    if (targetMode === 'LIVE') {
      setTypedConfirmation('');
      setIsLiveModalOpen(true);
      return;
    }
    try {
      await apiClient.post('/api/admin/automation/mode', {
        mode: targetMode,
        confirmed: true
      });
      toast.success(`Automation mode switched to ${targetMode}`);
      refetch();
    } catch (err: any) {
      toast.error(err?.message || 'Failed to update automation mode');
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 max-w-7xl mx-auto pb-12">
        <Skeleton className="h-10 w-72" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Skeleton className="h-44" />
          <Skeleton className="h-44" />
          <Skeleton className="h-44" />
        </div>
      </div>
    );
  }

  const isShadow = status?.current_mode === 'SHADOW';
  const isLive = status?.current_mode === 'LIVE';
  const isDryRun = status?.current_mode === 'DRY_RUN';

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16 px-1 sm:px-0">
      {/* 1. Permanent Safety Banner */}
      <div className={`p-4 rounded-lg border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 ${
        isLive
          ? 'bg-rose-50 dark:bg-rose-950/30 border-rose-500 text-rose-900 dark:text-rose-100'
          : 'bg-amber-50/80 dark:bg-amber-950/20 border-amber-500/50 text-amber-900 dark:text-amber-100'
      }`}>
        <div className="flex items-center gap-3">
          {isLive ? (
            <ShieldAlert className="h-6 w-6 text-rose-600 dark:text-rose-400 shrink-0" />
          ) : (
            <ShieldCheck className="h-6 w-6 text-amber-600 dark:text-amber-400 shrink-0" />
          )}
          <div>
            <div className="font-semibold text-sm sm:text-base flex items-center gap-2">
              <span>{status?.environment || 'STAGING'} ENVIRONMENT</span>
              <Badge variant={isLive ? 'destructive' : 'outline'} className="text-[11px] uppercase tracking-wider">
                {status?.current_mode || 'SHADOW'} MODE
              </Badge>
            </div>
            <p className="text-xs opacity-90 mt-0.5">
              {isLive
                ? 'CAUTION: LIVE mode enabled. Automated assignments will mutate ServiceNow assigned_to.'
                : 'Zero-Mutation Enforced: ServiceNow assigned_to and work_notes will never be updated in this mode.'}
            </p>
          </div>
        </div>

        {/* Quick Mode Controls */}
        <div className="flex items-center gap-2 w-full sm:w-auto">
          {!isShadow && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSwitchMode('SHADOW')}
              className="text-xs h-8 flex-1 sm:flex-initial"
            >
              Revert to Shadow
            </Button>
          )}
          {!isLive ? (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => handleSwitchMode('LIVE')}
              className="text-xs h-8 flex-1 sm:flex-initial gap-1"
            >
              <Lock className="h-3 w-3" /> Go Live
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSwitchMode('PAUSED')}
              className="text-xs h-8 flex-1 sm:flex-initial gap-1"
            >
              <Pause className="h-3 w-3" /> Pause Auto
            </Button>
          )}
        </div>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Integration Control Center</h1>
          <p className="text-sm text-muted-foreground">
            ServiceNow Table API diagnostics, Webhook health, Sync DLQ & E2E verification
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} className="h-9 text-xs">
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Refresh
          </Button>
          <Button size="sm" onClick={handleTestConnection} disabled={isTesting} className="h-9 text-xs gap-1.5">
            <Radio className="h-3.5 w-3.5" /> {isTesting ? 'Testing...' : 'Test Connection'}
          </Button>
        </div>
      </div>

      {/* 2. Top Metric Cards (Mobile-friendly Stack) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Connection Status Card */}
        <Card className="shadow-sm">
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-xs font-semibold uppercase tracking-wider">Connection Status</CardDescription>
            <CardTitle className="text-lg flex items-center gap-2">
              {status?.connection_code === 'CONNECTED' ? (
                <>
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-emerald-600 dark:text-emerald-400">Connected</span>
                </>
              ) : status?.connection_code === 'NOT_CONFIGURED' ? (
                <>
                  <span className="h-2.5 w-2.5 rounded-full bg-zinc-400" />
                  <span className="text-muted-foreground">Not Configured</span>
                </>
              ) : status?.connection_code === 'NOT_VERIFIED' ? (
                <>
                  <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
                  <span className="text-amber-600 dark:text-amber-400">Not Verified</span>
                </>
              ) : status?.connection_code === 'AUTH_FAILED' ? (
                <>
                  <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
                  <span className="text-rose-600 dark:text-rose-400">Auth Failed</span>
                </>
              ) : (
                <>
                  <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
                  <span className="text-rose-600 dark:text-rose-400">Unavailable</span>
                </>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-1 text-xs text-muted-foreground space-y-1">
            <div className="truncate font-mono text-[11px]">Host: {status?.servicenow_hostname || 'None'}</div>
            <div>Latency: {status?.latency_ms ? `${status.latency_ms} ms` : '—'}</div>
          </CardContent>
        </Card>

        {/* Webhook Health Card */}
        <Card className="shadow-sm">
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-xs font-semibold uppercase tracking-wider">Webhook Ingestion</CardDescription>
            <CardTitle className="text-lg flex items-center justify-between">
              <span>{status?.events_today ?? 0}</span>
              <Badge variant="outline" className="text-[10px]">Today</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-1 text-xs text-muted-foreground space-y-1">
            <div>Duplicates: {status?.duplicate_events ?? 0}</div>
            <div>Failed/Rejected: {status?.failed_events ?? 0}</div>
          </CardContent>
        </Card>

        {/* Sync / Two-Way Health Card */}
        <Card className="shadow-sm">
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-xs font-semibold uppercase tracking-wider">Sync & Recovery</CardDescription>
            <CardTitle className="text-lg flex items-center justify-between">
              <span className="text-emerald-600 dark:text-emerald-400">{status?.successful_syncs ?? 0}</span>
              <span className="text-xs font-normal text-muted-foreground">success</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-1 text-xs text-muted-foreground space-y-1">
            <div>Pending Retries: {status?.pending_retries ?? 0}</div>
            <div>DLQ Events: {status?.dead_letter_events ?? 0}</div>
          </CardContent>
        </Card>

        {/* Mode & Environment Card */}
        <Card className="shadow-sm">
          <CardHeader className="p-4 pb-2">
            <CardDescription className="text-xs font-semibold uppercase tracking-wider">Mode & Safeguards</CardDescription>
            <CardTitle className="text-lg flex items-center gap-2">
              <Shield className="h-4 w-4 text-blue-500" />
              <span>{status?.current_mode}</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-1 text-xs text-muted-foreground space-y-1">
            <div>Live Mutations: {isLive ? 'ENABLED' : 'DISABLED (Protected)'}</div>
            <div>Email Provider: MOCK</div>
          </CardContent>
        </Card>
      </div>

      {/* 3. Main Sections: Configuration Checklist & Service Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Operations & Diagnostics */}
        <div className="lg:col-span-2 space-y-6">
          {/* Webhook Operations Section */}
          <Card className="shadow-sm">
            <CardHeader className="p-4 sm:p-6 border-b">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-base sm:text-lg font-semibold flex items-center gap-2">
                    <Radio className="h-5 w-5 text-indigo-500" />
                    Webhook Operations & Stream
                  </CardTitle>
                  <CardDescription className="text-xs mt-0.5">
                    Real-time incident ingestion from ServiceNow Business Rules
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Link href="/admin/integrations/servicenow/events">
                    <Button variant="outline" size="sm" className="h-8 text-xs gap-1">
                      <Eye className="h-3 w-3" /> View Events
                    </Button>
                  </Link>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-4 sm:p-6 space-y-3">
              <div className="bg-muted/40 p-3 rounded-md font-mono text-xs break-all">
                <span className="text-muted-foreground">Receiver Endpoint: </span>
                <span className="text-foreground font-semibold">{status?.webhook_endpoint}</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="p-3 border rounded-md">
                  <span className="text-muted-foreground block mb-0.5">Last Ingested Ticket:</span>
                  <span className="font-semibold text-sm">{status?.last_incident_number || 'None received yet'}</span>
                </div>
                <div className="p-3 border rounded-md">
                  <span className="text-muted-foreground block mb-0.5">Last Ingestion Time:</span>
                  <span className="font-semibold text-sm">
                    {status?.last_webhook_received ? new Date(status.last_webhook_received).toLocaleTimeString() : 'N/A'}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Sync Health & Dead Letter Queue */}
          <Card className="shadow-sm">
            <CardHeader className="p-4 sm:p-6 border-b">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-base sm:text-lg font-semibold flex items-center gap-2">
                    <Activity className="h-5 w-5 text-emerald-500" />
                    Sync Health & DLQ Recovery
                  </CardTitle>
                  <CardDescription className="text-xs mt-0.5">
                    Manage sync failures, retry queues, and Dead Letter Queue records
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={handleOpenDlq} className="h-8 text-xs gap-1">
                    <Eye className="h-3 w-3" /> View DLQ ({status?.dead_letter_events ?? 0})
                  </Button>
                  <Button size="sm" variant="secondary" onClick={handleRetryAllFailures} className="h-8 text-xs gap-1">
                    <RefreshCw className="h-3 w-3" /> Retry Failed
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-4 sm:p-6">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                <div className="p-3 bg-muted/40 rounded-lg">
                  <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">{status?.successful_syncs ?? 0}</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">Successful Syncs</div>
                </div>
                <div className="p-3 bg-muted/40 rounded-lg">
                  <div className="text-xl font-bold text-amber-600 dark:text-amber-400">{status?.pending_retries ?? 0}</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">Pending Retries</div>
                </div>
                <div className="p-3 bg-muted/40 rounded-lg">
                  <div className="text-xl font-bold text-rose-600 dark:text-rose-400">{status?.failed_syncs ?? 0}</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">Failed Syncs</div>
                </div>
                <div className="p-3 bg-muted/40 rounded-lg">
                  <div className="text-xl font-bold text-zinc-700 dark:text-zinc-300">{status?.dead_letter_events ?? 0}</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">Dead Letter Queue</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Read-Only Permission Diagnostics */}
          <Card className="shadow-sm">
            <CardHeader className="p-4 sm:p-6 border-b">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-base sm:text-lg font-semibold flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-blue-500" />
                    Read-Only Permission Diagnostics
                  </CardTitle>
                  <CardDescription className="text-xs mt-0.5">
                    Validates Table API read grants without creating or mutating ServiceNow records
                  </CardDescription>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleRunDiagnostics}
                  disabled={isRunningDiagnostics}
                  className="h-8 text-xs"
                >
                  {isRunningDiagnostics ? 'Running...' : 'Run Diagnostics'}
                </Button>
              </div>
            </CardHeader>
            <CardContent className="p-4 sm:p-6 space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="flex items-center justify-between p-3 border rounded-md">
                  <span>Incident Table read (sysparm_limit=1)</span>
                  <Badge variant={diagnosticsData?.incident_table_read === 'PASS' ? 'default' : 'secondary'}>
                    {diagnosticsData?.incident_table_read || 'NOT TESTED'}
                  </Badge>
                </div>
                <div className="flex items-center justify-between p-3 border rounded-md">
                  <span>Assignment Group read (sys_user_group)</span>
                  <Badge variant={diagnosticsData?.assignment_group_read === 'PASS' ? 'default' : 'secondary'}>
                    {diagnosticsData?.assignment_group_read || 'NOT TESTED'}
                  </Badge>
                </div>
                <div className="flex items-center justify-between p-3 border rounded-md">
                  <span>User Table read (sys_user)</span>
                  <Badge variant={diagnosticsData?.user_read === 'PASS' ? 'default' : 'secondary'}>
                    {diagnosticsData?.user_read || 'NOT TESTED'}
                  </Badge>
                </div>
                <div className="flex items-center justify-between p-3 border rounded-md">
                  <span>Required Incident Fields read</span>
                  <Badge variant={diagnosticsData?.required_fields_read === 'PASS' ? 'default' : 'secondary'}>
                    {diagnosticsData?.required_fields_read || 'NOT TESTED'}
                  </Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right 1 Col: Visual Readiness Checklist */}
        <div className="space-y-6">
          <Card className="shadow-sm">
            <CardHeader className="p-4 sm:p-6 border-b">
              <CardTitle className="text-base sm:text-lg font-semibold">Configuration Checklist</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Strict distinction between Configured vs. Verified
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 sm:p-6 space-y-3 text-xs">
              {status?.config_checklist && (
                <>
                  <div className="flex items-center justify-between pb-2 border-b">
                    <div>
                      <div className="font-semibold">ServiceNow URL</div>
                      <div className="text-muted-foreground text-[11px]">Instance endpoint set in .env</div>
                    </div>
                    <Badge variant={status.config_checklist.servicenow_url.configured ? 'outline' : 'secondary'}>
                      {status.config_checklist.servicenow_url.configured ? 'CONFIGURED' : 'NOT SET'}
                    </Badge>
                  </div>

                  <div className="flex items-center justify-between pb-2 border-b">
                    <div>
                      <div className="font-semibold">Authentication</div>
                      <div className="text-muted-foreground text-[11px]">Basic / OAuth credentials set</div>
                    </div>
                    <Badge variant={status.config_checklist.authentication.configured ? 'outline' : 'secondary'}>
                      {status.config_checklist.authentication.configured ? 'CONFIGURED' : 'BLOCKED'}
                    </Badge>
                  </div>

                  <div className="flex items-center justify-between pb-2 border-b">
                    <div>
                      <div className="font-semibold">Webhook Secret</div>
                      <div className="text-muted-foreground text-[11px]">Shared secret for incoming calls</div>
                    </div>
                    <Badge variant={status.config_checklist.webhook_secret.configured ? 'outline' : 'secondary'}>
                      {status.config_checklist.webhook_secret.configured ? 'CONFIGURED' : 'BLOCKED'}
                    </Badge>
                  </div>

                  <div className="flex items-center justify-between pb-2 border-b">
                    <div>
                      <div className="font-semibold">APP_BASE_URL</div>
                      <div className="text-muted-foreground text-[11px]">Dynamic links for worker alerts</div>
                    </div>
                    <Badge variant="outline">READY</Badge>
                  </div>

                  <div className="flex items-center justify-between pb-2 border-b">
                    <div>
                      <div className="font-semibold">Real Connection Verified</div>
                      <div className="text-muted-foreground text-[11px]">Actual external 200 response</div>
                    </div>
                    <Badge variant={status.config_checklist.readonly_connection.verified ? 'default' : 'secondary'}>
                      {status.config_checklist.readonly_connection.verified ? 'VERIFIED' : 'NOT VERIFIED'}
                    </Badge>
                  </div>

                  <div className="flex items-center justify-between pb-2 border-b">
                    <div>
                      <div className="font-semibold">Real Staging E2E</div>
                      <div className="text-muted-foreground text-[11px]">Verified real incident payload</div>
                    </div>
                    <Badge variant={status.config_checklist.real_staging_e2e.verified ? 'default' : 'secondary'}>
                      {status.config_checklist.real_staging_e2e.verified ? 'VERIFIED' : 'BLOCKED'}
                    </Badge>
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-semibold">SMTP State</div>
                      <div className="text-muted-foreground text-[11px]">EMAIL_PROVIDER=MOCK enforced</div>
                    </div>
                    <Badge variant="outline">MOCK SAFE</Badge>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Connection Test Modal */}
      <Dialog open={isTestModalOpen} onOpenChange={setIsTestModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Outbound Connection Test</DialogTitle>
            <DialogDescription className="text-xs">
              Direct read-only request to ServiceNow Table API endpoint.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            {isTesting ? (
              <div className="flex flex-col items-center justify-center p-6 space-y-2">
                <RefreshCw className="h-8 w-8 animate-spin text-primary" />
                <span className="font-medium text-sm">Contacting ServiceNow Staging...</span>
              </div>
            ) : testResult ? (
              <div className="space-y-3">
                <div className={`p-4 rounded-lg border ${
                  testResult.status === 'connected'
                    ? 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-500 text-emerald-900 dark:text-emerald-100'
                    : 'bg-rose-50 dark:bg-rose-950/20 border-rose-500 text-rose-900 dark:text-rose-100'
                }`}>
                  <div className="font-semibold text-sm">
                    {testResult.status === 'connected' ? 'Connection Successful' : 'Connection Failed'}
                  </div>
                  <div className="text-xs mt-1">
                    Result: <span className="font-mono">{testResult.result || testResult.status}</span>
                  </div>
                </div>

                <div className="bg-muted/40 p-3 rounded font-mono text-[11px] space-y-1">
                  <div>Target Host: {testResult.target_hostname || 'N/A'}</div>
                  <div>HTTP Status: {testResult.status_code || 'N/A'}</div>
                  <div>Latency: {testResult.latency_ms ? `${testResult.latency_ms} ms` : 'N/A'}</div>
                  {testResult.error && <div className="text-rose-500">Error: {testResult.error}</div>}
                  {testResult.message && <div>Message: {testResult.message}</div>}
                </div>
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button size="sm" variant="outline" onClick={() => setIsTestModalOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* LIVE Mode Activation Safety Modal (Requires Typed Phrase) */}
      <Dialog open={isLiveModalOpen} onOpenChange={setIsLiveModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-rose-600 flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Confirm LIVE Assignment Activation
            </DialogTitle>
            <DialogDescription className="text-xs">
              Activating LIVE mode permits IncidentFlow to perform real writes and update assigned_to in ServiceNow.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2 text-xs">
            <div className="p-3 bg-rose-50 dark:bg-rose-950/30 border border-rose-500/50 rounded text-rose-900 dark:text-rose-100">
              <div className="font-semibold mb-1">Permanent Safeguard Requirement:</div>
              To prevent accidental production impact, please type the exact phrase below to authorize LIVE mode:
            </div>

            <div className="font-mono font-bold text-center text-sm py-1 bg-muted rounded select-all">
              ENABLE LIVE ASSIGNMENT
            </div>

            <Input
              placeholder="Type phrase exactly..."
              value={typedConfirmation}
              onChange={(e) => setTypedConfirmation(e.target.value)}
              className="text-xs font-mono"
            />
          </div>

          <DialogFooter className="gap-2">
            <Button size="sm" variant="outline" onClick={() => setIsLiveModalOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={handleActivateLive}
              disabled={typedConfirmation !== 'ENABLE LIVE ASSIGNMENT' || isActivatingLive}
            >
              {isActivatingLive ? 'Activating...' : 'Authorize LIVE Activation'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* DLQ Records Modal */}
      <Dialog open={isDlqModalOpen} onOpenChange={setIsDlqModalOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Dead Letter Queue (DLQ)</DialogTitle>
            <DialogDescription className="text-xs">
              Events that exceeded retry thresholds. You can inspect errors and re-queue manually.
            </DialogDescription>
          </DialogHeader>

          <div className="max-h-96 overflow-y-auto space-y-2 py-2 text-xs">
            {dlqItems.length === 0 ? (
              <div className="p-6 text-center text-muted-foreground">
                No events currently in the Dead Letter Queue.
              </div>
            ) : (
              dlqItems.map((item) => (
                <div key={item.id} className="p-3 border rounded-md flex items-center justify-between gap-3">
                  <div className="space-y-1 overflow-hidden">
                    <div className="font-semibold font-mono">{item.incident_number} — {item.operation}</div>
                    <div className="text-muted-foreground text-[11px] truncate">{item.error_message}</div>
                    <div className="text-[10px] text-muted-foreground">Retries: {item.retry_count}/{item.max_retries}</div>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => handleRetrySingle(item.id)} className="h-8 text-xs shrink-0">
                    Re-queue
                  </Button>
                </div>
              ))
            )}
          </div>

          <DialogFooter>
            <Button size="sm" variant="outline" onClick={() => setIsDlqModalOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
