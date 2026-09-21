'use client';

import * as React from 'react';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import {
  Users, AlertTriangle, Send, Eye, RefreshCw,
  CheckCircle2, XCircle, Activity, Inbox,
  ExternalLink, AlertCircle, Copy, Check, Crown, Search,
  Clock, Calendar, ShieldCheck, ShieldAlert, Power, Info
} from 'lucide-react';
import { usePageSearch } from '@/hooks/use-page-search';
import { HighlightMatch } from '@/components/search/highlight-match';
import { ContextualHelp } from '@/components/help/contextual-help';

/* ── Types ──────────────────────────────────────────────────────────── */
interface Team {
  id: string;
  name: string;
  description: string | null;
  servicenow_group_id: string | null;
  is_active: boolean;
  status?: 'ACTIVE' | 'DRAFT' | string;
  member_count: number;
  is_valid_active?: boolean;
  current_shift?: string;
  next_shift?: string;
  timezone?: string;
  group_leader_id?: string | null;
  group_leader_name?: string | null;
  active_incidents: number;
  unassigned_incidents: number;
  pending_incidents?: number;
  rotation_position?: number;
  rotation_cycle?: number;
  current_workload: number;
  created_at?: string | null;
}

interface Member {
  employee_id: string;
  full_name: string;
  email: string;
  availability_status: string;
  is_present: boolean;
  on_shift: boolean;
  active_assignments: number;
}

interface MembersData {
  team_name: string;
  members: Member[];
  summary: { total: number; on_shift: number; present: number; available: number; busy: number; off_shift: number };
  active_shift: string | null;
}

interface EligibleMember {
  employee_id: string;
  user_id: string;
  full_name: string;
  email: string;
  employee_code: string;
  is_group_leader: boolean;
  availability_status: string;
  is_present: boolean;
}

interface GroupLeaderData {
  team_id: string;
  team_name: string;
  current_leader: EligibleMember | null;
  eligible_members: EligibleMember[];
}

interface TeamShiftCoverageData {
  team_id: string;
  team_name: string;
  status: 'ACTIVE' | 'DRAFT';
  is_active: boolean;
  timezone: string;
  current_time: string;
  active_employees_count: number;
  current_shift: {
    id: string | null;
    name: string | null;
    start_time: string | null;
    end_time: string | null;
    scheduled_count: number;
    scheduled_employees: Array<{
      employee_id: string;
      full_name: string;
      email: string;
      is_present: boolean;
      availability_status: string;
      is_group_leader: boolean;
      active_workload: number;
    }>;
  };
  next_shift: {
    id: string | null;
    name: string | null;
    start_time: string | null;
    end_time: string | null;
    scheduled_date: string | null;
    scheduled_count: number;
  };
  summary: {
    total_members: number;
    present: number;
    available: number;
    busy: number;
    offline: number;
  };
  validation: {
    is_valid_active: boolean;
    violations: string[];
  };
}

interface ValidationData {
  team_id: string;
  team_name: string;
  is_valid: boolean;
  violations: string[];
  summary: {
    active_employee_count: number;
    group_leader_count: number;
    scheduled_employee_count: number;
    has_valid_schedule: boolean;
  };
}

/* ── Hooks ──────────────────────────────────────────────────────────── */
function useTeams() {
  return useQuery<{ teams: Team[]; total: number }>({
    queryKey: ['admin-teams'],
    queryFn: () => apiClient.get('/api/admin/teams'),
    refetchInterval: 30_000,
  });
}

function useTeamMembers(teamId: string | null) {
  return useQuery<MembersData>({
    queryKey: ['team-members', teamId],
    queryFn: () => apiClient.get(`/api/admin/teams/${teamId}/members`),
    enabled: !!teamId,
  });
}

function useTeamLeader(teamId: string | null) {
  return useQuery<GroupLeaderData>({
    queryKey: ['team-leader', teamId],
    queryFn: () => apiClient.get(`/api/admin/teams/${teamId}/group-leader`),
    enabled: !!teamId,
  });
}

function useTeamShiftCoverage(teamId: string | null) {
  return useQuery<TeamShiftCoverageData>({
    queryKey: ['team-shift-coverage', teamId],
    queryFn: () => apiClient.get(`/api/admin/teams/${teamId}/shift-coverage`),
    enabled: !!teamId,
  });
}

function useTeamValidation(teamId: string | null) {
  return useQuery<ValidationData>({
    queryKey: ['team-validation', teamId],
    queryFn: () => apiClient.get(`/api/admin/teams/${teamId}/validation`),
    enabled: !!teamId,
  });
}

/* ── Status Badge ───────────────────────────────────────────────────── */
function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    AVAILABLE: 'bg-green-500',
    BUSY: 'bg-yellow-500',
    BREAK: 'bg-orange-500',
    OFFLINE: 'bg-zinc-400',
  };
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[status] ?? 'bg-zinc-400'}`} />;
}

/* ── Main Page ──────────────────────────────────────────────────────── */
export default function AdminGroupsPage() {
  const qc = useQueryClient();
  const { data, isLoading, refetch } = useTeams();
  const teams = data?.teams ?? [];

  const [localSearch, setLocalSearch] = React.useState('');
  const filteredTeams = React.useMemo(() => {
    const q = localSearch.trim().toLowerCase();
    if (!q) return teams;
    return teams.filter(t =>
      t.name?.toLowerCase().includes(q) ||
      t.description?.toLowerCase().includes(q) ||
      t.group_leader_name?.toLowerCase().includes(q)
    );
  }, [teams, localSearch]);

  const handleSearch = React.useCallback((q: string) => {
    setLocalSearch(q);
  }, []);

  const { searchQuery, setSearchQuery } = usePageSearch({
    pageName: 'Groups & Teams',
    placeholder: 'Filter groups on this page...',
    itemCount: teams.length,
    filteredCount: filteredTeams.length,
    onSearch: handleSearch,
  });

  const router = useRouter();
  const [membersTeamId, setMembersTeamId] = React.useState<string | null>(null);
  const [noticeTeam, setNoticeTeam] = React.useState<Team | null>(null);
  const [noticeTitle, setNoticeTitle] = React.useState('');
  const [noticeMessage, setNoticeMessage] = React.useState('');
  const [noticePriority, setNoticePriority] = React.useState('P2');
  const [autoAssign, setAutoAssign] = React.useState(true);
  const [isSending, setIsSending] = React.useState(false);
  const [assignmentResult, setAssignmentResult] = React.useState<any | null>(null);
  const [copiedId, setCopiedId] = React.useState(false);

  // Shift Coverage & Validation Modal States
  const [coverageModalTeamId, setCoverageModalTeamId] = React.useState<string | null>(null);
  const [validationModalTeam, setValidationModalTeam] = React.useState<Team | null>(null);
  const [activationError, setActivationError] = React.useState<{ teamName: string; violations: string[] } | null>(null);
  const [isActionLoading, setIsActionLoading] = React.useState<string | null>(null);

  // Group Leader State
  const [leaderTeam, setLeaderTeam] = React.useState<Team | null>(null);
  const [selectedLeaderEmpId, setSelectedLeaderEmpId] = React.useState<string>('');
  const [leaderReason, setLeaderReason] = React.useState<string>('');
  const [isSubmittingLeader, setIsSubmittingLeader] = React.useState<boolean>(false);

  const { data: membersData, isLoading: membersLoading } = useTeamMembers(membersTeamId);
  const { data: leaderData, isLoading: leaderLoading } = useTeamLeader(leaderTeam?.id ?? null);
  const { data: coverageData, isLoading: coverageLoading } = useTeamShiftCoverage(coverageModalTeamId);
  const { data: validationData, isLoading: validationLoading } = useTeamValidation(validationModalTeam?.id ?? null);

  const handleToggleActivation = async (team: Team) => {
    setIsActionLoading(team.id);
    try {
      if (team.is_active) {
        await apiClient.post(`/api/admin/teams/${team.id}/deactivate`, {});
        toast.success(`Team "${team.name}" moved to DRAFT mode`);
      } else {
        await apiClient.post(`/api/admin/teams/${team.id}/activate`, {});
        toast.success(`Team "${team.name}" successfully activated (10/10 active members verified)`);
      }
      qc.invalidateQueries({ queryKey: ['admin-teams'] });
    } catch (err: any) {
      const violations = err?.response?.data?.detail?.violations || err?.detail?.violations;
      if (violations && Array.isArray(violations)) {
        setActivationError({
          teamName: team.name,
          violations,
        });
      } else {
        const msg = err?.response?.data?.detail?.message || err?.detail?.message || err?.message || 'Action blocked by policy';
        toast.error(msg);
      }
    } finally {
      setIsActionLoading(null);
    }
  };

  React.useEffect(() => {
    if (leaderData?.current_leader?.employee_id) {
      setSelectedLeaderEmpId(leaderData.current_leader.employee_id);
    } else if (leaderData?.eligible_members?.length) {
      setSelectedLeaderEmpId(leaderData.eligible_members[0].employee_id);
    }
  }, [leaderData]);

  const handleAssignLeader = async () => {
    if (!leaderTeam || !selectedLeaderEmpId) {
      toast.error('Please select an employee to assign as Group Leader');
      return;
    }
    setIsSubmittingLeader(true);
    try {
      const res = await apiClient.post<any>(`/api/admin/teams/${leaderTeam.id}/group-leader`, {
        employee_id: selectedLeaderEmpId,
        reason: leaderReason.trim() || undefined,
      });
      toast.success(res?.message || 'Group Leader successfully updated');
      setLeaderTeam(null);
      setLeaderReason('');
      qc.invalidateQueries({ queryKey: ['admin-teams'] });
      qc.invalidateQueries({ queryKey: ['team-members'] });
      qc.invalidateQueries({ queryKey: ['team-leader', leaderTeam.id] });
    } catch (err: any) {
      toast.error(err?.message || 'Failed to update Group Leader');
    } finally {
      setIsSubmittingLeader(false);
    }
  };

  const sendNotice = async () => {
    if (!noticeTeam || !noticeTitle.trim() || !noticeMessage.trim()) {
      toast.error('Title and message are required');
      return;
    }
    setIsSending(true);
    try {
      const result = await apiClient.post<any>(`/api/admin/teams/${noticeTeam.id}/notice`, {
        title: noticeTitle.trim(),
        message: noticeMessage.trim(),
        priority: noticePriority || 'P3',
        auto_assign: autoAssign,
      });

      setNoticeTeam(null);
      setNoticeTitle('');
      setNoticeMessage('');
      setNoticePriority('P2');

      setAssignmentResult(result);

      if (result.assignment_status === 'ASSIGNED') {
        toast.success(`Assigned to: ${result.assigned_employee_name}`);
      } else {
        toast.warning(`Notice sent. Status: ${result.assignment_status}`);
      }

      qc.invalidateQueries({ queryKey: ['admin-teams'] });
    } catch (err: any) {
      toast.error(err?.message || 'Failed to send notice');
    } finally {
      setIsSending(false);
    }
  };

  const copyIncidentId = (idText?: string) => {
    if (!idText) return;
    navigator.clipboard.writeText(idText);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
    toast.success('Incident ID copied to clipboard');
  };

  if (isLoading) {
    return (
      <div className="space-y-4 max-w-6xl mx-auto">
        <Skeleton className="h-8 w-48 mb-6" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-48 w-full" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Header */}
      <div className="flex items-center justify-between border-b pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">Groups</h1>
            <ContextualHelp featureKey="teams" label="Team rules" iconOnly={false} />
          </div>
          <p className="text-sm text-muted-foreground">Manage assignment groups, members, and send group notices</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()} className="text-xs">
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      {teams.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">
          <Users className="mx-auto h-10 w-10 mb-3 opacity-40" />
          <p>No groups configured yet.</p>
        </div>
      ) : filteredTeams.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">
          <Search className="mx-auto h-10 w-10 mb-3 opacity-40" />
          <p>No groups match &ldquo;{localSearch}&rdquo; on this page.</p>
          <Button variant="outline" size="sm" onClick={() => setSearchQuery('')} className="mt-3">
            Clear Filter
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTeams.map(team => (
            <Card
              key={team.id}
              className={`shadow-sm transition-all border ${
                !team.is_active
                  ? 'border-amber-300/60 dark:border-amber-900/40 bg-amber-500/[0.02]'
                  : 'border-border'
              }`}
            >
              <CardHeader className="p-4 pb-2.5 border-b">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 pr-1">
                    <CardTitle className="text-base font-semibold truncate">
                      <HighlightMatch text={team.name} query={localSearch} />
                    </CardTitle>
                    {team.description && (
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                        <HighlightMatch text={team.description} query={localSearch} />
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col sm:flex-row items-end sm:items-center gap-1.5 shrink-0">
                    {team.is_active ? (
                      <Badge className="bg-emerald-600 hover:bg-emerald-600 text-white text-[10px] font-bold px-2 py-0.5 tracking-wide shadow-xs">
                        ACTIVE
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="border-amber-500 text-amber-600 dark:text-amber-400 bg-amber-500/10 text-[10px] font-bold px-2 py-0.5 tracking-wide">
                        DRAFT
                      </Badge>
                    )}
                    {team.member_count === 10 ? (
                      <Badge className="bg-blue-50 dark:bg-blue-950/50 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800 text-[10px] font-mono flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3 text-blue-600 dark:text-blue-400" /> 10 / 10 Active
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="border-rose-300 dark:border-rose-800 text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/30 text-[10px] font-mono flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3 text-rose-500" /> {team.member_count} / 10 Active
                      </Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="p-4 space-y-3">
                {/* Current & Next Shift Schedule Strip */}
                <div className="rounded-lg bg-zinc-50 dark:bg-zinc-900/60 p-2.5 border border-zinc-200/70 dark:border-zinc-800/70 space-y-1.5 text-xs">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-[11px] text-muted-foreground flex items-center gap-1 font-medium shrink-0">
                      <Clock className="h-3.5 w-3.5 text-indigo-500 shrink-0" /> Current Shift:
                    </span>
                    <span className="font-semibold text-[11px] text-zinc-900 dark:text-zinc-100 truncate text-right">
                      {team.current_shift || 'No active shift'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-[11px] text-muted-foreground flex items-center gap-1 font-medium shrink-0">
                      <Calendar className="h-3.5 w-3.5 text-sky-500 shrink-0" /> Next Shift:
                    </span>
                    <span className="text-[11px] text-muted-foreground truncate text-right">
                      {team.next_shift || 'None'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-zinc-500 dark:text-zinc-400 pt-1 border-t border-zinc-200/50 dark:border-zinc-800/50">
                    <span>TZ: <strong className="font-mono text-zinc-700 dark:text-zinc-300">{team.timezone || 'Asia/Kolkata'}</strong></span>
                    <button
                      onClick={() => setCoverageModalTeamId(team.id)}
                      className="text-indigo-600 dark:text-indigo-400 hover:underline font-medium text-[10px] flex items-center gap-0.5"
                    >
                      Shift Roster &rarr;
                    </button>
                  </div>
                </div>

                {/* Stats grid */}
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="flex items-center gap-1.5">
                    <Users className="h-3.5 w-3.5 text-blue-500" />
                    <span className="font-semibold">{team.member_count}</span>
                    <span className="text-muted-foreground text-xs">members</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Activity className="h-3.5 w-3.5 text-amber-500" />
                    <span className="font-semibold">{team.current_workload}</span>
                    <span className="text-muted-foreground text-xs">workload</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5 text-rose-500" />
                    <span className="font-semibold">{team.active_incidents}</span>
                    <span className="text-muted-foreground text-xs">active inc.</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Inbox className="h-3.5 w-3.5 text-orange-400" />
                    <span className="font-semibold">{team.pending_incidents ?? team.unassigned_incidents}</span>
                    <span className="text-muted-foreground text-xs">pending</span>
                  </div>
                </div>

                {/* 10-Person Deterministic Rotation Tracker Badge */}
                <div className="flex items-center justify-between text-xs py-1 px-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800 text-indigo-900 dark:text-indigo-200 font-mono">
                  <span className="text-[11px] font-semibold text-indigo-700 dark:text-indigo-300">
                    Rotation: Pos {team.rotation_position ?? 1}/10
                  </span>
                  <span className="text-[11px] font-bold text-indigo-600 dark:text-indigo-400">
                    Cycle {team.rotation_cycle ?? 1}
                  </span>
                </div>

                {/* Group Leader Row */}
                <div className="flex items-center justify-between text-xs py-1.5 px-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-900 dark:text-amber-200">
                  <div className="flex items-center gap-1.5 font-medium min-w-0 pr-1">
                    <Crown className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                    <span className="text-[11px] text-muted-foreground shrink-0">Leader:</span>
                    <span className="font-semibold truncate">{team.group_leader_name || 'Assignment Pending'}</span>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-[11px] text-amber-700 dark:text-amber-300 hover:bg-amber-500/20 shrink-0"
                    onClick={() => setLeaderTeam(team)}
                  >
                    Change
                  </Button>
                </div>

                {/* Actions */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 pt-1">
                  <Button
                    asChild
                    size="sm"
                    className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-2"
                  >
                    <Link href={`/admin/groups/${team.id}/activity`}>
                      <Activity className="mr-1 h-3 w-3" /> Activity
                    </Link>
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs px-2"
                    onClick={() => setMembersTeamId(team.id)}
                  >
                    <Eye className="mr-1 h-3 w-3" /> Members
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs text-amber-600 border-amber-200 hover:bg-amber-50 dark:hover:bg-amber-950/20 px-2"
                    onClick={() => setLeaderTeam(team)}
                  >
                    <Crown className="mr-1 h-3 w-3 text-amber-500" /> Leader
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs text-blue-600 border-blue-200 hover:bg-blue-50 dark:hover:bg-blue-950/20 px-2"
                    onClick={() => setNoticeTeam(team)}
                    disabled={!team.is_active}
                  >
                    <Send className="mr-1 h-3 w-3" /> Notice
                  </Button>
                </div>

                {/* Secondary Bar: Activation Toggle & Validation Status */}
                <div className="flex items-center justify-between pt-1 border-t border-zinc-100 dark:border-zinc-800 text-xs">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-[11px] text-zinc-600 dark:text-zinc-400 hover:text-foreground"
                    onClick={() => setValidationModalTeam(team)}
                  >
                    <ShieldCheck className="h-3.5 w-3.5 mr-1 text-emerald-500" />
                    Validation Rules
                  </Button>
                  {team.is_active ? (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 px-2.5 text-[11px] text-amber-600 border-amber-200 hover:bg-amber-50 dark:hover:bg-amber-950/20"
                      onClick={() => handleToggleActivation(team)}
                      disabled={isActionLoading === team.id}
                    >
                      <Power className="h-3 w-3 mr-1" />
                      Deactivate
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      className="h-7 px-2.5 text-[11px] bg-emerald-600 hover:bg-emerald-700 text-white font-medium shadow-xs"
                      onClick={() => handleToggleActivation(team)}
                      disabled={isActionLoading === team.id}
                    >
                      <ShieldCheck className="h-3 w-3 mr-1" />
                      Activate Team
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Members Dialog */}
      <Dialog open={!!membersTeamId} onOpenChange={(o) => !o && setMembersTeamId(null)}>
        <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              {membersData?.team_name ?? 'Group Members'}
            </DialogTitle>
          </DialogHeader>

          {membersLoading ? (
            <div className="space-y-2 py-4">
              {[1,2,3].map(i => <Skeleton key={i} className="h-10 w-full" />)}
            </div>
          ) : membersData ? (
            <div className="space-y-4">
              {/* Summary */}
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 p-3 bg-muted/40 rounded-lg text-xs text-center">
                {[
                  { label: 'Total', val: membersData.summary.total },
                  { label: 'On Shift', val: membersData.summary.on_shift },
                  { label: 'Present', val: membersData.summary.present },
                  { label: 'Available', val: membersData.summary.available },
                  { label: 'Busy', val: membersData.summary.busy },
                  { label: 'Off Shift', val: membersData.summary.off_shift },
                ].map(s => (
                  <div key={s.label}>
                    <div className="font-bold text-base">{s.val}</div>
                    <div className="text-muted-foreground">{s.label}</div>
                  </div>
                ))}
              </div>
              {membersData.active_shift && (
                <p className="text-xs text-muted-foreground">Active shift: <strong>{membersData.active_shift}</strong></p>
              )}
              {/* Member list */}
              <div className="space-y-2">
                {membersData.members.map(m => (
                  <div key={m.employee_id} className="flex items-center justify-between p-2.5 rounded border text-sm">
                    <div className="flex items-center gap-2">
                      <StatusDot status={m.availability_status} />
                      <div>
                        <p className="font-medium">{m.full_name}</p>
                        <p className="text-xs text-muted-foreground">{m.email}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      {m.on_shift && <span className="text-green-600 font-medium">On shift</span>}
                      {!m.on_shift && <span className="text-zinc-400">Off shift</span>}
                      <span>{m.active_assignments} active</span>
                      <span className="font-mono">{m.availability_status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Group Leader Assignment Dialog */}
      <Dialog open={!!leaderTeam} onOpenChange={(o) => !o && setLeaderTeam(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-700 dark:text-amber-400">
              <Crown className="h-5 w-5 text-amber-500" /> Assign Group Leader
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2 text-xs">
            <div className="p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl space-y-1">
              <p className="font-semibold text-amber-950 dark:text-amber-300">
                Team: {leaderTeam?.name}
              </p>
              <p className="text-amber-800 dark:text-amber-400 text-[11px]">
                Each active team has exactly 1 Group Leader. The leader serves as operational point-of-contact and is authorized to directly message Administrators.
              </p>
            </div>

            {leaderLoading ? (
              <div className="space-y-2 py-4">
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-10 w-full" />)}
              </div>
            ) : leaderData ? (
              <div className="space-y-3">
                <div>
                  <label className="text-xs font-semibold mb-1.5 block">Select Team Member *</label>
                  {leaderData.eligible_members.length === 0 ? (
                    <p className="text-muted-foreground italic">No eligible members found in this team.</p>
                  ) : (
                    <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                      {leaderData.eligible_members.map(member => {
                        const isSelected = selectedLeaderEmpId === member.employee_id;
                        return (
                          <div
                            key={member.employee_id}
                            onClick={() => setSelectedLeaderEmpId(member.employee_id)}
                            className={`flex items-center justify-between p-2.5 rounded-xl border cursor-pointer transition-all ${
                              isSelected
                                ? 'border-amber-500 bg-amber-500/10 dark:bg-amber-500/20 ring-1 ring-amber-500'
                                : 'border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-850'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <StatusDot status={member.availability_status} />
                              <div className="truncate">
                                <p className="font-medium text-xs flex items-center gap-1.5">
                                  <span>{member.full_name}</span>
                                  {member.is_group_leader && (
                                    <Badge variant="outline" className="text-[9px] py-0 px-1 border-amber-500 text-amber-600 dark:text-amber-400">
                                      Current Leader
                                    </Badge>
                                  )}
                                </p>
                                <p className="text-[11px] text-muted-foreground truncate">{member.email}</p>
                              </div>
                            </div>
                            <div className="text-right shrink-0">
                              <span className="text-[10px] font-mono text-muted-foreground block">{member.employee_code}</span>
                              <span className={`text-[10px] font-medium ${member.is_present ? 'text-emerald-600' : 'text-zinc-400'}`}>
                                {member.is_present ? 'Present' : 'Offline'}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div>
                  <label className="text-xs font-medium mb-1 block">Reason / Audit Note (Optional)</label>
                  <Input
                    value={leaderReason}
                    onChange={e => setLeaderReason(e.target.value)}
                    placeholder="e.g. Shift rotation, primary operational lead"
                    className="text-xs"
                  />
                </div>
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setLeaderTeam(null)}>Cancel</Button>
            <Button
              className="bg-amber-600 hover:bg-amber-700 text-white"
              onClick={handleAssignLeader}
              disabled={isSubmittingLeader || !selectedLeaderEmpId}
            >
              <Crown className="mr-1.5 h-3.5 w-3.5" />
              {isSubmittingLeader ? 'Updating...' : 'Confirm Assignment'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Send Notice Dialog */}
      <Dialog open={!!noticeTeam} onOpenChange={(o) => !o && setNoticeTeam(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-blue-700 dark:text-blue-400">
              <Send className="h-4 w-4" /> Send Group Notice
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2 text-xs">
            <div className="p-3 bg-indigo-50 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-800 rounded-lg space-y-1">
              <p className="font-semibold text-indigo-900 dark:text-indigo-300">
                📢 Group Notice & Incident Allocation
              </p>
              <p className="text-indigo-700 dark:text-indigo-400 text-[11px]">
                Recipients: <strong>All members of {noticeTeam?.name}</strong> ({noticeTeam?.member_count} members).
                A unique incident ID (e.g. <span className="font-mono font-bold">INC-7K4M92XQ</span>) is generated automatically server-side.
              </p>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium mb-1 block">Notice Title / Incident Short Description *</label>
                <Input
                  value={noticeTitle}
                  onChange={e => setNoticeTitle(e.target.value)}
                  placeholder="e.g. Database connection pool exhaustion"
                  className="text-xs"
                />
              </div>
              <div>
                <label className="text-xs font-medium mb-1 block">Message / Work Instructions *</label>
                <textarea
                  value={noticeMessage}
                  onChange={e => setNoticeMessage(e.target.value)}
                  placeholder="e.g. Investigate connection pool exhaustion on replica cluster 3..."
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs min-h-[90px] resize-y focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium mb-1 block">Priority</label>
                  <select
                    value={noticePriority}
                    onChange={e => setNoticePriority(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
                  >
                    <option value="P1">P1 - Critical</option>
                    <option value="P2">P2 - High</option>
                    <option value="P3">P3 - Medium</option>
                    <option value="P4">P4 - Low</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium mb-1 block">Target Domain</label>
                  <Input value={noticeTeam?.name || ''} disabled className="text-xs bg-muted" />
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="autoAssignMainCheck"
                  checked={autoAssign}
                  onChange={e => setAutoAssign(e.target.checked)}
                  className="rounded border-input text-indigo-600 focus:ring-indigo-500 h-4 w-4"
                />
                <label htmlFor="autoAssignMainCheck" className="text-xs font-medium cursor-pointer">
                  Auto-assign work to eligible member on current shift
                </label>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setNoticeTeam(null)}>Cancel</Button>
            <Button
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
              onClick={sendNotice}
              disabled={isSending || !noticeTitle.trim() || !noticeMessage.trim()}
            >
              <Send className="mr-1.5 h-4 w-4" />
              {isSending ? 'Sending...' : `Send to ${noticeTeam?.name}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Assignment Result Display Modal */}
      <Dialog open={!!assignmentResult} onOpenChange={open => !open && setAssignmentResult(null)}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              {assignmentResult?.assignment_status === 'ASSIGNED' ? (
                <>
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                  <span>Assigned to: {assignmentResult.assigned_employee_name}</span>
                </>
              ) : (
                <>
                  <AlertCircle className="h-5 w-5 text-amber-500" />
                  <span>Assignment Status: Assignment Pending</span>
                </>
              )}
            </DialogTitle>
          </DialogHeader>

          {assignmentResult && (
            <div className="space-y-4 py-2 text-xs">
              {assignmentResult.assignment_status === 'ASSIGNED' ? (
                <div className="rounded-lg bg-emerald-50 dark:bg-emerald-950/40 p-3 border border-emerald-200 dark:border-emerald-900/50">
                  <div className="font-bold text-emerald-800 dark:text-emerald-200 text-sm">
                    Assigned to: {assignmentResult.assigned_employee_name}
                  </div>
                  <div className="text-emerald-700 dark:text-emerald-300 text-[11px] mt-0.5">
                    Engineer is verified on active shift, present, and available.
                  </div>
                </div>
              ) : (
                <div className="rounded-lg bg-amber-50 dark:bg-amber-950/40 p-3 border border-amber-200 dark:border-amber-900/50">
                  <div className="font-bold text-amber-800 dark:text-amber-200 text-sm">
                    Assignment Status: Assignment Pending
                  </div>
                  <div className="text-amber-700 dark:text-amber-300 text-[11px] mt-0.5">
                    Reason: <span className="font-semibold">{assignmentResult.pending_reason || assignmentResult.unassigned_reason || 'Assignment pending initialization.'}</span>
                  </div>
                </div>
              )}

              <div className="rounded-lg border bg-card p-4 space-y-2.5">
                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">1. Incident ID:</span>
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                      {assignmentResult.incident_number}
                    </span>
                    <button
                      onClick={() => copyIncidentId(assignmentResult.incident_number)}
                      className="p-1 hover:bg-muted rounded text-muted-foreground"
                      title="Copy Incident ID"
                    >
                      {copiedId ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">2. Short Description:</span>
                  <span className="font-semibold text-right max-w-[280px] truncate">
                    {assignmentResult.short_description}
                  </span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">3. Target Group:</span>
                  <span className="font-semibold">{assignmentResult.target_group}</span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">4. Notice Sent Time:</span>
                  <span className="font-mono text-muted-foreground">
                    {new Date(assignmentResult.notice_sent_time).toLocaleString()}
                  </span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">5. Assignment Status:</span>
                  <Badge
                    variant={assignmentResult.assignment_status === 'ASSIGNED' ? 'default' : 'secondary'}
                    className="text-[10px] uppercase font-bold"
                  >
                    {assignmentResult.assignment_status === 'ASSIGNED' ? 'ASSIGNED' : 'Assignment Pending'}
                  </Badge>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">6. Assigned Employee:</span>
                  <span className="font-bold">
                    {assignmentResult.assigned_employee_name || 'Assignment Pending'}
                  </span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">7. Employee ID:</span>
                  <span className="font-mono text-muted-foreground">
                    {assignmentResult.employee_id || 'N/A'}
                  </span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">8. Assignment Time:</span>
                  <span className="font-mono text-muted-foreground">
                    {assignmentResult.assignment_time ? new Date(assignmentResult.assignment_time).toLocaleString() : 'N/A'}
                  </span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">9. Employee Presence / Status:</span>
                  <span className="font-medium">
                    {assignmentResult.employee_presence || 'N/A'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground font-medium">10. Current Task & Status:</span>
                  <span className="font-medium text-right truncate max-w-[240px]">
                    {assignmentResult.current_task} ({assignmentResult.task_status})
                  </span>
                </div>
              </div>
            </div>
          )}

          <DialogFooter className="flex items-center justify-between sm:justify-between w-full">
            <Button variant="outline" size="sm" onClick={() => setAssignmentResult(null)}>
              Close
            </Button>
            {assignmentResult?.incident_number && (
              <Button
                size="sm"
                className="bg-indigo-600 hover:bg-indigo-700 text-white"
                onClick={() => {
                  setAssignmentResult(null);
                  router.push(`/incidents/${assignmentResult.incident_number}`);
                }}
              >
                <ExternalLink className="mr-1.5 h-3.5 w-3.5" /> View Assignment
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Validation Checklist Dialog */}
      <Dialog open={!!validationModalTeam} onOpenChange={(o) => !o && setValidationModalTeam(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
              Team Activation Verification
            </DialogTitle>
          </DialogHeader>

          {validationLoading ? (
            <div className="space-y-2 py-4">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : validationData ? (
            <div className="space-y-4 py-2 text-xs">
              <div className="flex items-center justify-between p-3 bg-muted/40 rounded-lg">
                <div>
                  <p className="font-semibold text-sm">{validationData.team_name}</p>
                  <p className="text-[11px] text-muted-foreground">Mandatory 10-person operational invariant</p>
                </div>
                <Badge
                  className={validationData.is_valid ? "bg-emerald-600 text-white font-bold" : "bg-amber-500 text-white font-bold"}
                >
                  {validationData.is_valid ? "POLICY READY" : "INCOMPLETE"}
                </Badge>
              </div>

              {/* Requirement Checklist */}
              <div className="space-y-2 border rounded-lg p-3">
                <div className="flex items-center justify-between text-xs pb-2 border-b">
                  <span className="flex items-center gap-1.5 font-medium">
                    {validationData.summary.active_employee_count === 10 ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 text-amber-500" />
                    )}
                    1. Exactly 10 Active Employees
                  </span>
                  <span className="font-mono font-semibold">
                    {validationData.summary.active_employee_count} / 10
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs py-2 border-b">
                  <span className="flex items-center gap-1.5 font-medium">
                    {validationData.summary.group_leader_count === 1 ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 text-amber-500" />
                    )}
                    2. Designated Group Leader
                  </span>
                  <span className="font-mono font-semibold">
                    {validationData.summary.group_leader_count} / 1
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs py-2 border-b">
                  <span className="flex items-center gap-1.5 font-medium">
                    {validationData.summary.scheduled_employee_count === 10 ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 text-amber-500" />
                    )}
                    3. 100% Shift Coverage
                  </span>
                  <span className="font-mono font-semibold">
                    {validationData.summary.scheduled_employee_count} / 10 Scheduled
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs pt-1">
                  <span className="flex items-center gap-1.5 font-medium">
                    {validationData.summary.has_valid_schedule ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 text-amber-500" />
                    )}
                    4. Active Schedule Configured
                  </span>
                  <span className="font-semibold text-muted-foreground">
                    {validationData.summary.has_valid_schedule ? 'Verified' : 'Missing'}
                  </span>
                </div>
              </div>

              {/* Violations section if any */}
              {validationData.violations.length > 0 && (
                <div className="rounded-lg bg-rose-50 dark:bg-rose-950/40 p-3 border border-rose-200 dark:border-rose-900/50 space-y-1.5">
                  <div className="flex items-center gap-1.5 font-semibold text-rose-800 dark:text-rose-200">
                    <ShieldAlert className="h-4 w-4 text-rose-600" />
                    Activation Blockers ({validationData.violations.length})
                  </div>
                  <ul className="list-disc list-inside space-y-1 text-rose-700 dark:text-rose-300 text-[11px]">
                    {validationData.violations.map((v, i) => (
                      <li key={i}>{v}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : null}

          <DialogFooter className="flex items-center justify-between w-full">
            <Button variant="outline" size="sm" onClick={() => setValidationModalTeam(null)}>
              Close
            </Button>
            {validationModalTeam && (
              validationModalTeam.is_active ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="text-amber-600 border-amber-300 hover:bg-amber-50"
                  onClick={() => {
                    const t = validationModalTeam;
                    setValidationModalTeam(null);
                    handleToggleActivation(t);
                  }}
                >
                  <Power className="mr-1.5 h-3.5 w-3.5" /> Deactivate to Draft
                </Button>
              ) : (
                <Button
                  size="sm"
                  className="bg-emerald-600 hover:bg-emerald-700 text-white"
                  onClick={() => {
                    const t = validationModalTeam;
                    setValidationModalTeam(null);
                    handleToggleActivation(t);
                  }}
                  disabled={!validationData?.is_valid}
                >
                  <ShieldCheck className="mr-1.5 h-3.5 w-3.5" /> Activate Team
                </Button>
              )
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Activation Error / Blocked Dialog */}
      <Dialog open={!!activationError} onOpenChange={(o) => !o && setActivationError(null)}>
        <DialogContent className="sm:max-w-md border-rose-300 dark:border-rose-900">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-rose-700 dark:text-rose-400">
              <ShieldAlert className="h-5 w-5 text-rose-600" />
              Team Activation Blocked
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2 text-xs">
            <p className="text-muted-foreground">
              Team <strong className="text-foreground">{activationError?.teamName}</strong> cannot be activated. IncidentFlow requires active teams to adhere strictly to operational invariants:
            </p>
            <div className="p-3 bg-rose-50 dark:bg-rose-950/40 rounded-lg border border-rose-200 dark:border-rose-900/60 space-y-1.5">
              <div className="font-semibold text-rose-900 dark:text-rose-200 text-xs">Violations:</div>
              <ul className="list-disc list-inside space-y-1 text-rose-800 dark:text-rose-300 text-[11px]">
                {activationError?.violations.map((v, i) => (
                  <li key={i}>{v}</li>
                ))}
              </ul>
            </div>
          </div>
          <DialogFooter>
            <Button size="sm" onClick={() => setActivationError(null)}>
              Understand Policy
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Team Shift Coverage & Roster Modal */}
      <Dialog open={!!coverageModalTeamId} onOpenChange={(o) => !o && setCoverageModalTeamId(null)}>
        <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-indigo-600" />
              {coverageData?.team_name ?? 'Team'} · Shift Coverage &amp; Realtime Roster
            </DialogTitle>
          </DialogHeader>

          {coverageLoading ? (
            <div className="space-y-3 py-4">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : coverageData ? (
            <div className="space-y-4 text-xs">
              {/* Shift info boxes */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="p-3 rounded-lg bg-indigo-50/70 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-900 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-indigo-900 dark:text-indigo-200 flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5 text-indigo-600" /> Current Shift
                    </span>
                    <Badge className="bg-indigo-600 text-white text-[10px]">Active Now</Badge>
                  </div>
                  <p className="text-sm font-bold text-indigo-950 dark:text-indigo-100">
                    {coverageData.current_shift.name || 'No Active Shift'}
                  </p>
                  <p className="text-[11px] text-indigo-700 dark:text-indigo-300 font-mono">
                    {coverageData.current_shift.start_time && coverageData.current_shift.end_time
                      ? `${coverageData.current_shift.start_time} - ${coverageData.current_shift.end_time}`
                      : 'N/A'}{' '}
                    ({coverageData.timezone})
                  </p>
                  <p className="text-[11px] text-muted-foreground pt-1">
                    Scheduled engineers: <strong>{coverageData.current_shift.scheduled_count}</strong>
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-sky-50/70 dark:bg-sky-950/30 border border-sky-200 dark:border-sky-900 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sky-900 dark:text-sky-200 flex items-center gap-1.5">
                      <Calendar className="h-3.5 w-3.5 text-sky-600" /> Next Shift
                    </span>
                    <Badge variant="outline" className="border-sky-400 text-sky-700 dark:text-sky-300 text-[10px]">Upcoming</Badge>
                  </div>
                  <p className="text-sm font-bold text-sky-950 dark:text-sky-100">
                    {coverageData.next_shift.name || 'None'}
                  </p>
                  <p className="text-[11px] text-sky-700 dark:text-sky-300 font-mono">
                    {coverageData.next_shift.start_time && coverageData.next_shift.end_time
                      ? `${coverageData.next_shift.start_time} - ${coverageData.next_shift.end_time}`
                      : 'N/A'}
                  </p>
                  <p className="text-[11px] text-muted-foreground pt-1">
                    Scheduled engineers: <strong>{coverageData.next_shift.scheduled_count}</strong>
                  </p>
                </div>
              </div>

              {/* Coverage Policy Alert */}
              <div className="p-3 rounded-lg bg-muted/40 border text-[11px] text-muted-foreground flex items-start gap-2">
                <Info className="h-4 w-4 text-indigo-500 shrink-0 mt-0.5" />
                <div>
                  <strong>Hard Coverage Rule:</strong> Auto-assignment selects exactly ONE verified present employee on the current active shift. Next-shift employees are never assigned early. If no current-shift employees are present, a <code>COVERAGE_EXCEPTION</code> is logged.
                </div>
              </div>

              {/* Roster of scheduled employees on current shift */}
              <div>
                <h4 className="font-semibold text-xs mb-2 flex items-center justify-between">
                  <span>Current Shift Scheduled Engineers ({coverageData.current_shift.scheduled_employees.length})</span>
                  <span className="text-[11px] text-muted-foreground font-normal">
                    {coverageData.summary.present} present &bull; {coverageData.summary.available} available
                  </span>
                </h4>

                {coverageData.current_shift.scheduled_employees.length === 0 ? (
                  <p className="text-muted-foreground italic py-3 text-center border rounded-lg">
                    No engineers scheduled on the current shift window.
                  </p>
                ) : (
                  <div className="space-y-1.5 max-h-60 overflow-y-auto">
                    {coverageData.current_shift.scheduled_employees.map(emp => (
                      <div
                        key={emp.employee_id}
                        className="flex items-center justify-between p-2.5 rounded-lg border text-xs"
                      >
                        <div className="flex items-center gap-2">
                          <StatusDot status={emp.availability_status} />
                          <div>
                            <div className="font-medium flex items-center gap-1.5">
                              <span>{emp.full_name}</span>
                              {emp.is_group_leader && (
                                <Badge variant="outline" className="text-[9px] py-0 px-1 border-amber-500 text-amber-600">
                                  <Crown className="h-2.5 w-2.5 mr-0.5 inline" /> Leader
                                </Badge>
                              )}
                            </div>
                            <p className="text-[11px] text-muted-foreground">{emp.email}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3 text-right">
                          <Badge
                            variant={emp.is_present ? "default" : "outline"}
                            className={emp.is_present ? "bg-emerald-600 text-[10px]" : "text-zinc-400 text-[10px]"}
                          >
                            {emp.is_present ? "Present" : "Offline"}
                          </Badge>
                          <span className="font-mono text-[11px]">{emp.availability_status}</span>
                          <span className="text-muted-foreground text-[11px]">{emp.active_workload} active</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setCoverageModalTeamId(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
