'use client';

import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { RefreshCw, TrendingUp, Users, Bell, Activity, Clock, AlertTriangle } from 'lucide-react';

type Period = 'today' | '7d' | '30d';

interface Analytics {
  period: string;
  generated_at: string;
  timezone: string;
  incidents: { total: number; new: number; assigned: number; active: number; completed: number; unassigned: number };
  timing: { avg_assignment_minutes: number | null; avg_completion_minutes: number | null };
  group_workload: { team_id: string; team_name: string; active_assignments: number }[];
  employee_workload: { employee_id: string; name: string; active_assignments: number }[];
  notifications: { total: number; unread: number; by_type: Record<string, number> };
  shift_coverage: { active_shift: string | null; on_shift: number; present: number; available: number };
}

function useAnalytics(period: Period) {
  return useQuery<Analytics>({
    queryKey: ['analytics', period],
    queryFn: () => apiClient.get(`/api/admin/analytics?period=${period}`),
    refetchInterval: 30_000,
  });
}

function StatCard({ label, value, sub, icon: Icon, color = 'text-foreground' }: {
  label: string; value: number | string; sub?: string; icon: any; color?: string;
}) {
  return (
    <Card className="shadow-sm">
      <CardContent className="p-4 flex items-center gap-3">
        <div className={`p-2 rounded-lg bg-muted`}>
          <Icon className={`h-4 w-4 ${color}`} />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className={`text-xl font-bold ${color}`}>{value}</p>
          {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

export default function AdminAnalyticsPage() {
  const [period, setPeriod] = React.useState<Period>('7d');
  const { data, isLoading, refetch } = useAnalytics(period);

  const periodLabels: Record<Period, string> = { today: 'Today', '7d': 'Last 7 Days', '30d': 'Last 30 Days' };

  const fmtMinutes = (m: number | null) => {
    if (m === null || m === undefined) return '—';
    if (m < 60) return `${Math.round(m)}m`;
    return `${(m / 60).toFixed(1)}h`;
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
          <p className="text-sm text-muted-foreground">Real database metrics · {data?.timezone ?? 'Asia/Kolkata'}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border overflow-hidden">
            {(['today', '7d', '30d'] as Period[]).map(p => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  period === p ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
                }`}
              >
                {periodLabels[p]}
              </button>
            ))}
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()} className="text-xs">
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}
        </div>
      ) : data ? (
        <>
          {/* Incident counts */}
          <div>
            <h2 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">Incidents — {periodLabels[period]}</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <StatCard label="Total" value={data.incidents.total} icon={Activity} />
              <StatCard label="New" value={data.incidents.new} icon={TrendingUp} color="text-blue-600" />
              <StatCard label="Assigned" value={data.incidents.assigned} icon={Users} color="text-amber-600" />
              <StatCard label="Active" value={data.incidents.active} icon={Activity} color="text-green-600" />
              <StatCard label="Completed" value={data.incidents.completed} icon={Activity} color="text-emerald-600" />
              <StatCard label="Assignment Pending" value={data.incidents.unassigned} icon={AlertTriangle} color="text-rose-600" />
            </div>
          </div>

          {/* Timing */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <StatCard
              label="Avg Assignment Time"
              value={fmtMinutes(data.timing.avg_assignment_minutes)}
              sub="incident created → first assignment"
              icon={Clock}
              color="text-blue-600"
            />
            <StatCard
              label="Avg Completion Time"
              value={fmtMinutes(data.timing.avg_completion_minutes)}
              sub="assignment → completion (where available)"
              icon={Clock}
              color="text-emerald-600"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Group workload */}
            <Card className="shadow-sm">
              <CardHeader className="p-4 border-b">
                <CardTitle className="text-sm font-semibold">Group Workload (Active Assignments)</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {data.group_workload.length === 0 ? (
                  <p className="p-4 text-sm text-muted-foreground">No groups</p>
                ) : (
                  <div className="divide-y">
                    {data.group_workload.map(g => (
                      <div key={g.team_id} className="flex items-center justify-between px-4 py-2.5 text-sm">
                        <span>{g.team_name}</span>
                        <div className="flex items-center gap-2">
                          <div className="h-2 bg-blue-500 rounded" style={{ width: `${Math.min(g.active_assignments * 8, 80)}px` }} />
                          <span className="font-semibold tabular-nums w-6 text-right">{g.active_assignments}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Employee workload */}
            <Card className="shadow-sm">
              <CardHeader className="p-4 border-b">
                <CardTitle className="text-sm font-semibold">Employee Workload (Top 10)</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {data.employee_workload.length === 0 ? (
                  <p className="p-4 text-sm text-muted-foreground">No active assignments</p>
                ) : (
                  <div className="divide-y">
                    {data.employee_workload.map(e => (
                      <div key={e.employee_id} className="flex items-center justify-between px-4 py-2.5 text-sm">
                        <span>{e.name}</span>
                        <div className="flex items-center gap-2">
                          <div className="h-2 bg-amber-500 rounded" style={{ width: `${Math.min(e.active_assignments * 12, 80)}px` }} />
                          <span className="font-semibold tabular-nums w-6 text-right">{e.active_assignments}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Notifications */}
            <Card className="shadow-sm">
              <CardHeader className="p-4 border-b">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <Bell className="h-4 w-4" /> Notifications — {periodLabels[period]}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 space-y-2">
                <div className="flex justify-between text-sm py-1 border-b">
                  <span className="text-muted-foreground">Total</span>
                  <span className="font-semibold">{data.notifications.total}</span>
                </div>
                <div className="flex justify-between text-sm py-1 border-b">
                  <span className="text-muted-foreground">Unread</span>
                  <span className="font-semibold text-amber-600">{data.notifications.unread}</span>
                </div>
                {Object.entries(data.notifications.by_type).map(([type, count]) => (
                  <div key={type} className="flex justify-between text-xs py-0.5">
                    <span className="text-muted-foreground font-mono">{type}</span>
                    <span>{count}</span>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* Shift coverage */}
            <Card className="shadow-sm">
              <CardHeader className="p-4 border-b">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <Users className="h-4 w-4" /> Current Shift Coverage
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 space-y-2">
                <p className="text-xs text-muted-foreground">
                  Active shift: <strong>{data.shift_coverage.active_shift ?? 'None'}</strong>
                </p>
                {[
                  { label: 'On Shift', val: data.shift_coverage.on_shift, color: 'text-blue-600' },
                  { label: 'Present', val: data.shift_coverage.present, color: 'text-green-600' },
                  { label: 'Available', val: data.shift_coverage.available, color: 'text-emerald-600' },
                ].map(r => (
                  <div key={r.label} className="flex justify-between text-sm py-1.5 border-b last:border-0">
                    <span className="text-muted-foreground">{r.label}</span>
                    <span className={`font-bold ${r.color}`}>{r.val}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          <p className="text-xs text-muted-foreground text-right">
            Generated: {new Date(data.generated_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST
          </p>
        </>
      ) : (
        <p className="text-muted-foreground text-sm">No data available.</p>
      )}
    </div>
  );
}
