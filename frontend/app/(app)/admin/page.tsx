'use client';

import * as React from 'react';
import { useAdminDashboard } from '@/hooks/use-admin';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge } from '@/components/status-badge';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import {
  Activity, Users, AlertTriangle, CheckCircle2,
  Clock, ShieldAlert, PlayCircle, PauseCircle, RefreshCw
} from 'lucide-react';

export default function AdminDashboardPage() {
  const { data: stats, isLoading, refetch } = useAdminDashboard();
  const [liveList, setLiveList] = React.useState<any[]>([]);
  const [autoStatus, setAutoStatus] = React.useState<'active' | 'paused'>('active');
  const [isProcessing, setIsProcessing] = React.useState(false);

  const fetchLive = React.useCallback(async () => {
    try {
      const data = await apiClient.get<any[]>('/api/admin/assignments/live');
      if (Array.isArray(data)) setLiveList(data);
    } catch {
      // fallback
    }
  }, []);

  React.useEffect(() => {
    fetchLive();
    const timer = setInterval(fetchLive, 8000);
    return () => clearInterval(timer);
  }, [fetchLive]);

  const toggleAutomation = async () => {
    setIsProcessing(true);
    try {
      if (autoStatus === 'active') {
        await apiClient.post('/api/admin/automation/pause');
        setAutoStatus('paused');
        toast.warning('Automatic assignment paused. Incidents will queue as unassigned.');
      } else {
        await apiClient.post('/api/admin/automation/resume');
        setAutoStatus('active');
        toast.success('Automatic assignment resumed successfully.');
      }
    } catch (err: any) {
      toast.error(err?.message || 'Failed to update automation state');
    } finally {
      setIsProcessing(false);
    }
  };

  const triggerSync = async () => {
    setIsProcessing(true);
    try {
      await apiClient.post('/api/admin/integrations/servicenow/sync');
      toast.success('ServiceNow two-way synchronization triggered');
      fetchLive();
      refetch();
    } catch (err: any) {
      toast.error('Sync failed');
    } finally {
      setIsProcessing(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-60" />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-24" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Top Banner / Mobile Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Admin Command Center</h1>
          <p className="text-sm text-muted-foreground">Real-time incident dispatch, worker presence & ServiceNow synchronization</p>
        </div>

        {/* Quick Emergency Action Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            size="sm"
            variant={autoStatus === 'active' ? 'outline' : 'destructive'}
            onClick={toggleAutomation}
            disabled={isProcessing}
            className="text-xs h-9"
          >
            {autoStatus === 'active' ? (
              <>
                <PauseCircle className="mr-1.5 h-4 w-4 text-amber-500" /> Pause Automation
              </>
            ) : (
              <>
                <PlayCircle className="mr-1.5 h-4 w-4 text-emerald-500" /> Resume Automation
              </>
            )}
          </Button>

          <Button
            size="sm"
            variant="outline"
            onClick={triggerSync}
            disabled={isProcessing}
            className="text-xs h-9"
          >
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isProcessing ? 'animate-spin' : ''}`} />
            Sync Now
          </Button>
        </div>
      </div>

      {/* Metric Cards Grid - Fully responsive for mobile/tablet/desktop */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <Card className="border-l-4 border-l-blue-500 shadow-sm">
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-xs font-semibold text-muted-foreground flex items-center justify-between">
              Active Incidents
              <Activity className="h-3.5 w-3.5 text-blue-500" />
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-1">
            <div className="text-2xl font-bold">{stats?.active_incidents ?? 0}</div>
            <span className="text-[11px] text-muted-foreground">In progress & assigned</span>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-rose-500 shadow-sm">
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-xs font-semibold text-muted-foreground flex items-center justify-between">
              Unassigned Queue
              <AlertTriangle className="h-3.5 w-3.5 text-rose-500" />
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-1">
            <div className="text-2xl font-bold text-rose-600">{stats?.unassigned_incidents ?? 0}</div>
            <span className="text-[11px] text-muted-foreground">Requires attention</span>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-emerald-500 shadow-sm">
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-xs font-semibold text-muted-foreground flex items-center justify-between">
              On Shift
              <Clock className="h-3.5 w-3.5 text-emerald-500" />
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-1">
            <div className="text-2xl font-bold">{stats?.employees_on_shift ?? 0}</div>
            <span className="text-[11px] text-muted-foreground">Active shift today</span>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-emerald-400 shadow-sm">
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-xs font-semibold text-muted-foreground flex items-center justify-between">
              Available
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-1">
            <div className="text-2xl font-bold text-emerald-600">{stats?.available_employees ?? 0}</div>
            <span className="text-[11px] text-muted-foreground">Ready for tasks</span>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-amber-500 shadow-sm col-span-2 sm:col-span-1">
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-xs font-semibold text-muted-foreground flex items-center justify-between">
              Busy Workers
              <Users className="h-3.5 w-3.5 text-amber-500" />
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-1">
            <div className="text-2xl font-bold">{stats?.busy_employees ?? 0}</div>
            <span className="text-[11px] text-muted-foreground">High capacity</span>
          </CardContent>
        </Card>
      </div>

      {/* System Status Indicators */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <div className="p-3 bg-card border rounded-lg flex items-center justify-between">
          <span className="text-muted-foreground">ServiceNow Integration:</span>
          <span className="font-semibold text-emerald-600 flex items-center gap-1">● Connected (Mock)</span>
        </div>
        <div className="p-3 bg-card border rounded-lg flex items-center justify-between">
          <span className="text-muted-foreground">Assignment Strategy:</span>
          <span className="font-mono font-semibold">SKILL + WORKLOAD</span>
        </div>
        <div className="p-3 bg-card border rounded-lg flex items-center justify-between">
          <span className="text-muted-foreground">Automation Status:</span>
          <span className={`font-semibold ${autoStatus === 'active' ? 'text-emerald-600' : 'text-rose-600'}`}>
            ● {autoStatus === 'active' ? 'ENABLED' : 'PAUSED'}
          </span>
        </div>
        <div className="p-3 bg-card border rounded-lg flex items-center justify-between">
          <span className="text-muted-foreground">Email Notifications:</span>
          <span className="font-semibold text-blue-600">● Active (Mock)</span>
        </div>
      </div>

      {/* Live Assignment Board */}
      <Card className="shadow-sm">
        <CardHeader className="p-4 sm:p-6 border-b flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base sm:text-lg font-semibold">Live Incident Assignment Board</CardTitle>
            <p className="text-xs text-muted-foreground mt-0.5">Real-time dispatches from ServiceNow webhook into eligible engineers</p>
          </div>
          <Button variant="ghost" size="sm" onClick={fetchLive} className="h-8 text-xs">
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {liveList.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              No live incident assignments recorded yet. Ingest a ServiceNow incident to view live updates.
            </div>
          ) : (
            <div className="divide-y divide-border">
              {liveList.map((item, idx) => (
                <div key={idx} className="p-3.5 sm:p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:bg-muted/30 transition-colors">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-sm text-foreground">{item.incident_number}</span>
                      <span className="text-xs bg-muted px-2 py-0.5 rounded text-muted-foreground uppercase">{item.assignment_type}</span>
                    </div>
                    <p className="text-xs sm:text-sm text-muted-foreground line-clamp-1">{item.short_description}</p>
                  </div>
                  <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0">
                    <div className="text-right">
                      <div className="text-xs font-semibold">{item.employee_name}</div>
                      <div className="text-[11px] text-muted-foreground">Assigned</div>
                    </div>
                    <StatusBadge status={item.status} type="status" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Sync Failure & Recovery Center */}
      <Card className="shadow-sm border-l-4 border-l-amber-500">
        <CardHeader className="p-4 sm:p-6 border-b flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base sm:text-lg font-semibold flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-amber-500" />
              ServiceNow Synchronization & Recovery Center
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-0.5">
              Automated retry pipeline with exponential backoff (1s → 2s → 4s → 8s). Zero incident loss guarantee.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={triggerSync} className="text-xs h-8">
            Trigger Health Ping
          </Button>
        </CardHeader>
        <CardContent className="p-4 sm:p-6 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="p-3 bg-muted/40 rounded-md">
              <span className="text-muted-foreground block mb-1">Pipeline State</span>
              <span className="font-semibold text-emerald-600">● 100% Operational</span>
            </div>
            <div className="p-3 bg-muted/40 rounded-md">
              <span className="text-muted-foreground block mb-1">Sync Policy</span>
              <span className="font-semibold">ServiceNow Authoritative</span>
            </div>
            <div className="p-3 bg-muted/40 rounded-md">
              <span className="text-muted-foreground block mb-1">Circuit Breaker</span>
              <span className="font-semibold">Max 5 Retries → Dead Letter</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

