'use client';

import * as React from 'react';
import Link from 'next/link';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { wsClient } from '@/lib/websocket';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Users2, MessageSquare, Star, Clock, AlertCircle, RefreshCw,
  Mail, Phone, Globe, Shield, Sparkles, CheckCircle2, ChevronRight
} from 'lucide-react';

interface TeamMember {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  avatar_url: string | null;
  role: string;
  is_group_leader: boolean;
  employee_code: string | null;
  is_present: boolean;
  availability_status: string;
  current_shift_name: string | null;
  current_shift_hours: string | null;
  active_assignments: number;
  skills: string[];
}

interface TeamData {
  id: string;
  name: string;
  description: string | null;
  work_domain: string | null;
  servicenow_group_id: string | null;
  group_leader: TeamMember | null;
  members: TeamMember[];
  member_count: number;
  online_count: number;
  available_count: number;
}

export default function EmployeeTeamPage() {
  const queryClient = useQueryClient();
  const [selectedMember, setSelectedMember] = React.useState<TeamMember | null>(null);

  const { data: team, isLoading, isError, error, refetch } = useQuery<TeamData>({
    queryKey: ['my-team-detail'],
    queryFn: () => apiClient.get<TeamData>('/api/me/team'),
    refetchInterval: 30000,
  });

  // Subscribe to real-time events for team presence and group leader changes
  React.useEffect(() => {
    const handleUpdate = () => {
      queryClient.invalidateQueries({ queryKey: ['my-team-detail'] });
    };

    wsClient.on('GROUP_LEADER_CHANGED', handleUpdate);
    wsClient.on('TEAM_MEMBER_UPDATED', handleUpdate);
    wsClient.on('PROFILE_UPDATED', handleUpdate);
    wsClient.on('CHAT_PRESENCE_CHANGED', handleUpdate);

    return () => {
      wsClient.off('GROUP_LEADER_CHANGED', handleUpdate);
      wsClient.off('TEAM_MEMBER_UPDATED', handleUpdate);
      wsClient.off('PROFILE_UPDATED', handleUpdate);
      wsClient.off('CHAT_PRESENCE_CHANGED', handleUpdate);
    };
  }, [queryClient]);

  if (isLoading) {
    return (
      <div className="space-y-6 max-w-6xl mx-auto p-4 md:p-8 animate-pulse">
        <div className="flex justify-between items-center">
          <Skeleton className="h-10 w-64 rounded-xl" />
          <Skeleton className="h-10 w-36 rounded-xl" />
        </div>
        <Skeleton className="h-32 w-full rounded-2xl" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton className="h-24 rounded-2xl" />
          <Skeleton className="h-24 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (isError || !team) {
    return (
      <div className="max-w-xl mx-auto pt-16 text-center px-4">
        <div className="mx-auto h-14 w-14 rounded-2xl bg-red-50 text-red-600 flex items-center justify-center mb-4">
          <AlertCircle className="h-7 w-7" />
        </div>
        <h2 className="text-xl font-bold text-zinc-900 dark:text-zinc-100">Unable to load Team Workspace</h2>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1 mb-6">
          {(error as Error)?.message || 'The operational team could not be retrieved.'}
        </p>
        <Button onClick={() => refetch()} className="rounded-xl px-6 bg-[#087CFF] hover:bg-[#149BFF] text-white">
          <RefreshCw className="h-4 w-4 mr-2" />
          Retry
        </Button>
      </div>
    );
  }

  const presenceDot = (status: string, isPresent: boolean) => {
    if (!isPresent) return 'bg-zinc-400';
    if (status === 'AVAILABLE') return 'bg-emerald-500';
    if (status === 'BUSY') return 'bg-amber-500';
    if (status === 'BREAK') return 'bg-yellow-500';
    return 'bg-zinc-400';
  };

  const statusBadgeColor = (status: string) => {
    switch (status) {
      case 'AVAILABLE':
        return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800';
      case 'BUSY':
        return 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 border-amber-200 dark:border-amber-800';
      case 'BREAK':
        return 'bg-yellow-50 text-yellow-700 dark:bg-yellow-950/40 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800';
      default:
        return 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-400 border-zinc-200 dark:border-zinc-700';
    }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto p-4 md:p-8">
      {/* ── TOP HEADER ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-black/[0.08] dark:border-white/[0.08] pb-5">
        <div>
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-2xl bg-blue-50 dark:bg-blue-950/40 text-[#087CFF] dark:text-[#149BFF] flex items-center justify-center font-bold">
              <Users2 className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-2xl font-bold tracking-tight text-[#071A33] dark:text-white">
                  {team.name}
                </h1>
                <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                  ACTIVE
                </span>
              </div>
              <p className="text-xs text-[#667085] dark:text-zinc-400 mt-0.5">
                {team.work_domain || team.description || 'Enterprise Operational Group'}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <Button asChild className="rounded-xl px-5 h-11 bg-[#087CFF] hover:bg-[#149BFF] text-white font-semibold shadow-md shadow-blue-500/20 active:scale-[0.98] transition-all">
            <Link href="/employee/team-chat" className="flex items-center space-x-2">
              <MessageSquare className="h-4 w-4" />
              <span>💬 Team Chat</span>
            </Link>
          </Button>
        </div>
      </div>

      {/* ── METRICS SUMMARY BAR ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-4 rounded-2xl bg-white/80 dark:bg-[#071426]/80 border border-black/[0.06] dark:border-white/[0.08] shadow-sm">
          <span className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">Total Members</span>
          <p className="text-2xl font-bold text-[#071A33] dark:text-white mt-1">{team.member_count}</p>
        </div>
        <div className="p-4 rounded-2xl bg-white/80 dark:bg-[#071426]/80 border border-black/[0.06] dark:border-white/[0.08] shadow-sm">
          <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">🟢 Present Online</span>
          <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">{team.online_count}</p>
        </div>
        <div className="p-4 rounded-2xl bg-white/80 dark:bg-[#071426]/80 border border-black/[0.06] dark:border-white/[0.08] shadow-sm">
          <span className="text-xs font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wider">⚡ Available</span>
          <p className="text-2xl font-bold text-blue-600 dark:text-blue-400 mt-1">{team.available_count}</p>
        </div>
        <div className="p-4 rounded-2xl bg-white/80 dark:bg-[#071426]/80 border border-black/[0.06] dark:border-white/[0.08] shadow-sm">
          <span className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">Active Group</span>
          <p className="text-sm font-bold text-[#071A33] dark:text-white mt-2 truncate">{team.name}</p>
        </div>
      </div>

      {/* ── GROUP LEADER HERO CARD ── */}
      {team.group_leader && (
        <Card className="rounded-2xl border-amber-300/40 dark:border-amber-500/20 bg-gradient-to-r from-amber-50/60 via-white to-amber-50/40 dark:from-amber-950/20 dark:via-[#071426] dark:to-amber-950/10 shadow-sm overflow-hidden">
          <CardContent className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center space-x-4">
              <div className="relative">
                <Avatar className="h-14 w-14 ring-2 ring-amber-400/80 shadow-md">
                  {team.group_leader.avatar_url && (
                    <AvatarImage src={apiClient.getMediaUrl(team.group_leader.avatar_url)} alt={team.group_leader.full_name} />
                  )}
                  <AvatarFallback className="bg-amber-100 text-amber-900 font-bold text-lg">
                    {team.group_leader.full_name.charAt(0)}
                  </AvatarFallback>
                </Avatar>
                <span className={`absolute bottom-0 right-0 h-3.5 w-3.5 rounded-full ring-2 ring-white dark:ring-[#071426] ${presenceDot(team.group_leader.availability_status, team.group_leader.is_present)}`} />
              </div>

              <div>
                <div className="flex items-center space-x-2">
                  <h3 className="font-bold text-base text-zinc-900 dark:text-white">
                    {team.group_leader.full_name}
                  </h3>
                  <span className="flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
                    <Star className="h-3 w-3 fill-amber-500 text-amber-500 mr-0.5" />
                    GROUP LEADER
                  </span>
                </div>
                <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-0.5">
                  {team.group_leader.email} • {team.group_leader.employee_code || 'ID: Leader'}
                </p>
                {team.group_leader.current_shift_hours && (
                  <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-1 flex items-center">
                    <Clock className="h-3 w-3 mr-1 text-zinc-400" />
                    Shift: {team.group_leader.current_shift_hours}
                  </p>
                )}
              </div>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setSelectedMember(team.group_leader)}
              className="rounded-xl border-amber-200 dark:border-amber-800/60 hover:bg-amber-100/50 text-amber-900 dark:text-amber-300 self-start sm:self-center font-medium"
            >
              View Leader Profile
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ── TEAM ROSTER ── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-lg font-bold text-[#071A33] dark:text-white">
            Team Members ({team.members.length})
          </h2>
          <span className="text-xs text-zinc-500">Tap a member to inspect profile</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {team.members.map((member) => (
            <div
              key={member.id}
              onClick={() => setSelectedMember(member)}
              className="flex items-center justify-between p-3.5 rounded-2xl bg-white/90 dark:bg-[#071426]/90 border border-black/[0.06] dark:border-white/[0.08] hover:border-[#087CFF]/40 dark:hover:border-[#149BFF]/40 hover:shadow-md transition-all cursor-pointer group active:scale-[0.99]"
            >
              <div className="flex items-center space-x-3 min-w-0">
                <div className="relative shrink-0">
                  <Avatar className="h-11 w-11">
                    {member.avatar_url && (
                      <AvatarImage src={apiClient.getMediaUrl(member.avatar_url)} alt={member.full_name} />
                    )}
                    <AvatarFallback className="bg-blue-50 text-[#087CFF] dark:bg-blue-950 dark:text-[#149BFF] font-semibold text-sm">
                      {member.full_name.charAt(0)}
                    </AvatarFallback>
                  </Avatar>
                  <span className={`absolute bottom-0 right-0 h-3 w-3 rounded-full ring-2 ring-white dark:ring-[#071426] ${presenceDot(member.availability_status, member.is_present)}`} />
                </div>

                <div className="min-w-0">
                  <div className="flex items-center space-x-1.5 truncate">
                    <span className="font-semibold text-sm text-zinc-900 dark:text-zinc-100 group-hover:text-[#087CFF] dark:group-hover:text-[#149BFF] transition-colors truncate">
                      {member.full_name}
                    </span>
                    {member.is_group_leader && (
                      <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-300">
                        ⭐ LEADER
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 truncate">
                    {member.email}
                  </p>
                  {member.current_shift_hours && (
                    <p className="text-[10px] text-zinc-600 dark:text-zinc-400 mt-0.5">
                      Shift: {member.current_shift_hours}
                    </p>
                  )}
                </div>
              </div>

              <div className="flex items-center space-x-2 shrink-0 ml-2">
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusBadgeColor(member.availability_status)}`}>
                  {member.availability_status}
                </span>
                <ChevronRight className="h-4 w-4 text-zinc-400 group-hover:text-zinc-600 dark:group-hover:text-zinc-200 transition-colors" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── MEMBER PROFILE INSPECTION MODAL ── */}
      <Dialog open={!!selectedMember} onOpenChange={(open) => !open && setSelectedMember(null)}>
        <DialogContent className="max-w-md rounded-3xl p-6 border-black/[0.08] dark:border-white/[0.08] shadow-2xl">
          {selectedMember && (
            <div className="space-y-5">
              <DialogHeader className="text-left pb-2 border-b border-zinc-100 dark:border-zinc-800">
                <div className="flex items-center space-x-3">
                  <div className="relative">
                    <Avatar className="h-16 w-16 shadow-md">
                      {selectedMember.avatar_url && (
                        <AvatarImage src={apiClient.getMediaUrl(selectedMember.avatar_url)} alt={selectedMember.full_name} />
                      )}
                      <AvatarFallback className="bg-blue-100 text-[#087CFF] font-bold text-xl">
                        {selectedMember.full_name.charAt(0)}
                      </AvatarFallback>
                    </Avatar>
                    <span className={`absolute bottom-0 right-0 h-4 w-4 rounded-full ring-2 ring-white dark:ring-[#071426] ${presenceDot(selectedMember.availability_status, selectedMember.is_present)}`} />
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <DialogTitle className="text-xl font-bold text-zinc-950 dark:text-white">
                        {selectedMember.full_name}
                      </DialogTitle>
                      {selectedMember.is_group_leader && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-300">
                          ⭐ LEADER
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-zinc-500 mt-0.5">{selectedMember.role} • {team.name}</p>
                    <span className={`inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusBadgeColor(selectedMember.availability_status)}`}>
                      {selectedMember.is_present ? `🟢 Present (${selectedMember.availability_status})` : '⚪ Offline'}
                    </span>
                  </div>
                </div>
              </DialogHeader>

              <div className="space-y-3 text-sm">
                <div className="p-3 rounded-xl bg-zinc-50 dark:bg-zinc-900/60 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-zinc-500">Employee Code:</span>
                    <span className="font-semibold text-zinc-900 dark:text-zinc-100">{selectedMember.employee_code || 'EMP-AUTO'}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-zinc-500">Email:</span>
                    <span className="font-semibold text-zinc-900 dark:text-zinc-100">{selectedMember.email}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-zinc-500">Current Shift:</span>
                    <span className="font-semibold text-zinc-900 dark:text-zinc-100">{selectedMember.current_shift_hours || 'Standard Shift'}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-zinc-500">Active Incidents:</span>
                    <span className="font-semibold text-zinc-900 dark:text-zinc-100">{selectedMember.active_assignments} tickets</span>
                  </div>
                </div>

                {selectedMember.skills && selectedMember.skills.length > 0 && (
                  <div>
                    <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider block mb-1.5">Verified Skills</span>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedMember.skills.map((skill, i) => (
                        <span key={i} className="px-2.5 py-0.5 rounded-lg text-xs font-medium bg-blue-50 text-[#087CFF] dark:bg-blue-950/60 dark:text-[#149BFF]">
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="pt-2 flex justify-end">
                <Button onClick={() => setSelectedMember(null)} variant="outline" className="rounded-xl px-4">
                  Close
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
