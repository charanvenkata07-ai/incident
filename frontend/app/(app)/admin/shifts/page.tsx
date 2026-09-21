'use client';

import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { RefreshCw, Clock, Users, Moon, Calendar, ShieldCheck, Info } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { ContextualHelp } from '@/components/help/contextual-help';

interface ShiftEmployee {
  employee_id: string;
  full_name: string;
  email: string;
  team: string | null;
  availability_status: string;
  is_present: boolean;
  active_assignments: number;
}

interface ShiftData {
  shift_id: string;
  name: string;
  start_time: string;
  end_time: string;
  timezone: string;
  is_overnight: boolean;
  is_current: boolean;
  date: string;
  employees: ShiftEmployee[];
  coverage: { total_assigned: number; present: number; available: number; offline: number };
}

interface TodayShifts {
  date: string;
  timezone: string;
  local_time: string;
  shifts: ShiftData[];
  total_shifts: number;
}

function useShifts() {
  return useQuery<TodayShifts>({
    queryKey: ['shifts-today'],
    queryFn: () => apiClient.get('/api/admin/shifts/today'),
    refetchInterval: 60_000,
  });
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    AVAILABLE: 'bg-green-500',
    BUSY: 'bg-yellow-500',
    BREAK: 'bg-orange-500',
    OFFLINE: 'bg-zinc-400',
  };
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[status] ?? 'bg-zinc-400'}`} />;
}

export default function AdminShiftsPage() {
  const { data, isLoading, refetch } = useShifts();

  const shifts = data?.shifts ?? [];
  const currentShiftIndex = shifts.findIndex(s => s.is_current);
  const nextShiftId = currentShiftIndex !== -1 && shifts.length > 1
    ? shifts[(currentShiftIndex + 1) % shifts.length].shift_id
    : null;

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      {/* Header */}
      <div className="flex items-center justify-between border-b pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">Shifts &amp; Rosters</h1>
            <ContextualHelp featureKey="shifts" label="Shift rules" iconOnly={false} />
          </div>
          {data && (
            <p className="text-sm text-muted-foreground mt-0.5">
              {data.date} &bull; Timezone: <strong className="font-mono">{data.timezone}</strong> &bull; Local time: <strong className="font-mono">{data.local_time}</strong>
            </p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()} className="text-xs">
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      {/* Mandatory Shift Coverage Rule Banner */}
      <div className="rounded-xl border border-indigo-200 dark:border-indigo-900 bg-indigo-50/50 dark:bg-indigo-950/20 p-4 text-xs space-y-1.5">
        <div className="flex items-center gap-2 font-semibold text-indigo-950 dark:text-indigo-200">
          <ShieldCheck className="h-4 w-4 text-indigo-600" />
          Mandatory Operational Shift Invariant
        </div>
        <p className="text-indigo-800 dark:text-indigo-300 leading-relaxed text-[11px]">
          IncidentFlow enforces <strong>Current Shift as the primary hard filter</strong> for assignment. Next-shift engineers are strictly excluded from immediate assignment even if logged in early. If no scheduled engineers on the active shift are present, a <code>COVERAGE_EXCEPTION</code> is generated and the incident remains safely unassigned until shift change.
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2].map(i => <Skeleton key={i} className="h-48 w-full" />)}
        </div>
      ) : !data || shifts.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">
          <Clock className="mx-auto h-10 w-10 mb-3 opacity-40" />
          <p>No shifts configured for today.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {shifts.map(shift => {
            const isNext = shift.shift_id === nextShiftId;
            return (
              <Card
                key={shift.shift_id}
                className={`shadow-sm transition-all ${
                  shift.is_current
                    ? 'border-emerald-500 ring-1 ring-emerald-500/30'
                    : isNext
                    ? 'border-sky-300 dark:border-sky-800'
                    : ''
                }`}
              >
                <CardHeader className="p-4 pb-3 border-b">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {shift.is_overnight ? <Moon className="h-4 w-4 text-indigo-500" /> : <Clock className="h-4 w-4 text-blue-500" />}
                      <CardTitle className="text-base font-semibold">{shift.name}</CardTitle>
                      {shift.is_current && (
                        <Badge className="bg-emerald-600 hover:bg-emerald-600 text-white text-[10px] font-bold">
                          ● Active Now (Current Shift)
                        </Badge>
                      )}
                      {isNext && (
                        <Badge variant="outline" className="border-sky-400 text-sky-700 dark:text-sky-300 text-[10px] font-semibold">
                          Next Shift
                        </Badge>
                      )}
                      {shift.is_overnight && (
                        <span className="text-xs text-indigo-600 bg-indigo-50 dark:bg-indigo-950/30 px-2 py-0.5 rounded-full border border-indigo-200">
                          Overnight
                        </span>
                      )}
                    </div>
                    <div className="text-sm font-mono text-muted-foreground">
                      {shift.start_time} → {shift.end_time} <span className="text-xs">({shift.timezone})</span>
                    </div>
                  </div>
                </CardHeader>
              <CardContent className="p-4">
                {/* Coverage summary */}
                <div className="grid grid-cols-4 gap-2 mb-4 text-center">
                  {[
                    { label: 'Assigned', val: shift.coverage.total_assigned, color: 'text-blue-600' },
                    { label: 'Present', val: shift.coverage.present, color: 'text-green-600' },
                    { label: 'Available', val: shift.coverage.available, color: 'text-emerald-600' },
                    { label: 'Offline', val: shift.coverage.offline, color: 'text-zinc-500' },
                  ].map(s => (
                    <div key={s.label} className="p-2 bg-muted/40 rounded">
                      <p className={`text-lg font-bold ${s.color}`}>{s.val}</p>
                      <p className="text-xs text-muted-foreground">{s.label}</p>
                    </div>
                  ))}
                </div>

                {/* Employee list */}
                {shift.employees.length === 0 ? (
                  <p className="text-sm text-muted-foreground italic">No employees assigned to this shift today.</p>
                ) : (
                  <div className="space-y-1">
                    {shift.employees.map(emp => (
                      <div key={emp.employee_id} className="flex items-center justify-between p-2 rounded hover:bg-muted/40 text-sm">
                        <div className="flex items-center gap-2">
                          <StatusDot status={emp.availability_status} />
                          <div>
                            <span className="font-medium">{emp.full_name}</span>
                            {emp.team && <span className="ml-2 text-xs text-muted-foreground">({emp.team})</span>}
                          </div>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-muted-foreground">
                          <span className={emp.is_present ? 'text-green-600' : 'text-zinc-400'}>
                            {emp.is_present ? 'Present' : 'Absent'}
                          </span>
                          <span className="font-mono">{emp.availability_status}</span>
                          {emp.active_assignments > 0 && (
                            <span className="text-amber-600 font-medium">{emp.active_assignments} active</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
          })}
        </div>
      )}
    </div>
  );
}
