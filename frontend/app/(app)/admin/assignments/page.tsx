'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/status-badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import { AlertCircle, UserCheck, RefreshCw, Layers, Send, Users, Shield, Clock, ArrowRight, Search } from 'lucide-react';
import { usePageSearch } from '@/hooks/use-page-search';
import { HighlightMatch } from '@/components/search/highlight-match';

export default function AdminAssignmentsPage() {
  const [unassigned, setUnassigned] = React.useState<any[]>([]);
  const [employees, setEmployees] = React.useState<any[]>([]);
  const [teams, setTeams] = React.useState<any[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [selectedIncident, setSelectedIncident] = React.useState<any | null>(null);
  const [selectedEmpId, setSelectedEmpId] = React.useState<string>('');
  const [isAssignOpen, setIsAssignOpen] = React.useState(false);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const [isSendOpen, setIsSendOpen] = React.useState(false);
  const [sendTargetEmpId, setSendTargetEmpId] = React.useState<string>('');
  const [sendMessage, setSendMessage] = React.useState<string>('');
  const [isSending, setIsSending] = React.useState(false);

  // Send to Group & Smart Assignment Preview state
  const [isSendToGroupOpen, setIsSendToGroupOpen] = React.useState(false);
  const [targetTeamId, setTargetTeamId] = React.useState<string>('');
  const [groupCustomMessage, setGroupCustomMessage] = React.useState<string>('');
  const [previewData, setPreviewData] = React.useState<any | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = React.useState(false);
  const [isSendingToGroup, setIsSendingToGroup] = React.useState(false);

  const [localSearch, setLocalSearch] = React.useState('');

  const filteredUnassigned = React.useMemo(() => {
    const q = localSearch.trim().toLowerCase();
    if (!q) return unassigned;
    return unassigned.filter((inc) => {
      return (
        inc.incident_number?.toLowerCase().includes(q) ||
        inc.short_description?.toLowerCase().includes(q) ||
        inc.priority?.toLowerCase().includes(q) ||
        inc.assignment_group?.toLowerCase().includes(q) ||
        inc.state?.toLowerCase().includes(q) ||
        inc.reason?.toLowerCase().includes(q)
      );
    });
  }, [unassigned, localSearch]);

  const { searchQuery, setSearchQuery } = usePageSearch({
    pageName: 'Assignments Queue',
    placeholder: 'Filter Assignment Pending incidents on this page...',
    itemCount: unassigned.length,
    filteredCount: filteredUnassigned.length,
    onSearch: (q) => setLocalSearch(q),
  });

  const loadData = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const [uncRes, empRes, teamRes] = await Promise.all([
        apiClient.get<any[]>('/api/admin/incidents/unassigned'),
        apiClient.get<any[]>('/api/admin/employees'),
        apiClient.get<any[]>('/api/admin/teams'),
      ]);
      if (Array.isArray(uncRes)) setUnassigned(uncRes);
      if (Array.isArray(empRes)) setEmployees(empRes);
      if (Array.isArray(teamRes)) setTeams(teamRes);
    } catch {
      toast.error('Failed to load queue data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  const fetchPreview = async (incidentId: string, teamId: string) => {
    if (!teamId || !incidentId) return;
    setIsPreviewLoading(true);
    try {
      const prev = await apiClient.post<any>(`/api/admin/incidents/${incidentId}/send-to-group/preview`, {
        team_id: teamId,
      });
      setPreviewData(prev);
    } catch (err: any) {
      toast.error(err?.message || 'Failed to evaluate group preview');
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleOpenSendToGroup = (inc: any) => {
    setSelectedIncident(inc);
    setGroupCustomMessage('');
    setPreviewData(null);
    let defaultTeamId = '';
    if (inc.assignment_group && teams.length > 0) {
      const match = teams.find(
        (t: any) =>
          t.name.toLowerCase() === inc.assignment_group.toLowerCase() ||
          t.servicenow_group_id === inc.assignment_group ||
          t.name.toLowerCase().includes(inc.assignment_group.toLowerCase())
      );
      if (match) defaultTeamId = match.id;
    }
    if (!defaultTeamId && teams.length > 0) {
      defaultTeamId = teams[0].id;
    }
    setTargetTeamId(defaultTeamId);
    setIsSendToGroupOpen(true);
    if (defaultTeamId) {
      fetchPreview(inc.id, defaultTeamId);
    }
  };

  const handleSendToGroup = async () => {
    if (!selectedIncident || !targetTeamId) {
      toast.error('Please select a target team');
      return;
    }
    setIsSendingToGroup(true);
    try {
      const res = await apiClient.post<any>(`/api/admin/incidents/${selectedIncident.id}/send-to-group`, {
        team_id: targetTeamId,
        message: groupCustomMessage || undefined,
      });
      if (res.state === 'QUEUED_FOR_NEXT_SHIFT') {
        toast.success(`Incident ${selectedIncident.incident_number} queued for next shift (${res.scheduled_shift_name || 'Upcoming'}) assigned to ${res.assigned_to || 'Next Engineer'}`);
      } else if (res.assigned_to) {
        toast.success(`Incident ${selectedIncident.incident_number} automatically assigned to ${res.assigned_to}`);
      } else {
        toast.info(`Incident sent to group. Status: ${res.state}`);
      }
      setIsSendToGroupOpen(false);
      setSelectedIncident(null);
      setPreviewData(null);
      loadData();
    } catch (err: any) {
      toast.error(err?.message || 'Failed to send incident to group');
    } finally {
      setIsSendingToGroup(false);
    }
  };

  const handleManualAssign = async () => {
    if (!selectedIncident || !selectedEmpId) {
      toast.error('Please select an employee');
      return;
    }
    setIsSubmitting(true);
    try {
      await apiClient.post(`/api/admin/incidents/${selectedIncident.id}/assign`, {
        employee_id: selectedEmpId,
        reason: 'Manual assign override from Admin Unassigned Queue',
      });
      toast.success(`Assigned ${selectedIncident.incident_number} successfully`);
      setIsAssignOpen(false);
      setSelectedIncident(null);
      setSelectedEmpId('');
      loadData();
    } catch (err: any) {
      toast.error(err?.message || 'Assignment failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSendNotice = async () => {
    if (!selectedIncident || !sendTargetEmpId) {
      toast.error('Please select a recipient');
      return;
    }
    setIsSending(true);
    try {
      await apiClient.post(`/api/admin/incidents/${selectedIncident.id}/send`, {
        employee_ids: [sendTargetEmpId],
        message: sendMessage || undefined,
        confirmed: true,
      });
      toast.success(`Notice for ${selectedIncident.incident_number} broadcasted successfully`);
      setIsSendOpen(false);
      setSelectedIncident(null);
      setSendTargetEmpId('');
      setSendMessage('');
    } catch (err: any) {
      toast.error(err?.message || 'Dispatch failed');
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Assignment Pending Queue</h1>
          <p className="text-sm text-muted-foreground">
            Zero-incident-loss fallback: incidents waiting for available employees or manual override
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadData} className="text-xs h-9">
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Refresh Queue
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : unassigned.length === 0 ? (
        <Card className="p-8 text-center border-dashed">
          <div className="flex flex-col items-center justify-center space-y-2">
            <div className="p-3 bg-emerald-50 dark:bg-emerald-950/30 rounded-full text-emerald-600">
              <UserCheck className="h-6 w-6" />
            </div>
            <h3 className="font-semibold text-lg">All Incidents Are Assigned</h3>
            <p className="text-sm text-muted-foreground max-w-sm">
              No incidents waiting in the Assignment Pending queue. The assignment engine is running normally.
            </p>
          </div>
        </Card>
      ) : filteredUnassigned.length === 0 ? (
        <Card className="p-8 text-center border-dashed">
          <div className="flex flex-col items-center justify-center space-y-2">
            <div className="p-3 bg-zinc-100 dark:bg-zinc-800 rounded-full text-zinc-500">
              <Search className="h-6 w-6" />
            </div>
            <h3 className="font-semibold text-lg">No Matching Incidents</h3>
            <p className="text-sm text-muted-foreground max-w-sm">
              No incidents match &ldquo;{localSearch}&rdquo; on this page.
            </p>
            <Button variant="outline" size="sm" onClick={() => setSearchQuery('')} className="mt-2">
              Clear Filter
            </Button>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filteredUnassigned.map((inc) => (
            <Card key={inc.id} className="border-l-4 border-l-rose-500 shadow-sm p-4 sm:p-5">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-base">
                      <HighlightMatch text={inc.incident_number} query={localSearch} />
                    </span>
                    <StatusBadge status={inc.priority} type="priority" />
                    <span className="text-xs bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 font-medium px-2 py-0.5 rounded">
                      Assignment Pending
                    </span>
                  </div>
                  <h4 className="font-medium text-sm text-foreground">
                    <HighlightMatch text={inc.short_description} query={localSearch} />
                  </h4>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground pt-1">
                    <AlertCircle className="h-3.5 w-3.5 text-rose-500 shrink-0" />
                    <span>{inc.reason}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-2 sm:pt-0 shrink-0 flex-wrap">
                  <Button
                    size="sm"
                    className="w-full sm:w-auto text-xs h-9 bg-indigo-600 hover:bg-indigo-700 text-white font-medium shadow-sm"
                    onClick={() => handleOpenSendToGroup(inc)}
                  >
                    <Layers className="mr-1.5 h-3.5 w-3.5" />
                    Send to Group
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full sm:w-auto text-xs h-9"
                    onClick={() => {
                      setSelectedIncident(inc);
                      setIsSendOpen(true);
                    }}
                  >
                    Send Notice
                  </Button>
                  <Button
                    size="sm"
                    className="w-full sm:w-auto text-xs h-9 bg-zinc-900 text-white dark:bg-zinc-50 dark:text-zinc-900"
                    onClick={() => {
                      setSelectedIncident(inc);
                      setIsAssignOpen(true);
                    }}
                  >
                    Manual Assign
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Send Incident Notice Dialog (SEND != ASSIGN) */}
      <Dialog open={isSendOpen} onOpenChange={setIsSendOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Send Notice: {selectedIncident?.incident_number}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="p-3 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-900 rounded-md text-xs text-blue-800 dark:text-blue-300">
              <strong>Notice:</strong> Broadcasts an alert to workers without altering ticket assignment or triggering assignment engines.
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-1.5">
                Target Employee
              </label>
              <select
                className="w-full h-10 border rounded-md px-3 text-sm bg-background"
                value={sendTargetEmpId}
                onChange={(e) => setSendTargetEmpId(e.target.value)}
              >
                <option value="">-- Select Recipient --</option>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.full_name} ({emp.email || 'No email'})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-1.5">
                Custom Broadcast Message
              </label>
              <textarea
                className="w-full h-20 border rounded-md p-2.5 text-xs bg-background"
                placeholder="Notice: High priority incident arrived. Please review."
                value={sendMessage}
                onChange={(e) => setSendMessage(e.target.value)}
              />
            </div>

            <DialogFooter className="pt-2">
              <Button variant="outline" onClick={() => setIsSendOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleSendNotice}
                disabled={isSending || !sendTargetEmpId}
                className="bg-blue-600 hover:bg-blue-700 text-white"
              >
                {isSending ? 'Sending...' : 'Confirm & Dispatch Notice'}
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* Manual Assignment Dialog */}
      <Dialog open={isAssignOpen} onOpenChange={setIsAssignOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Assign {selectedIncident?.incident_number}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <p className="text-xs text-muted-foreground">
              Select an employee to manually override automated routing:
            </p>

            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-1.5">
                Eligible Employees
              </label>
              <select
                className="w-full h-10 border rounded-md px-3 text-sm bg-background"
                value={selectedEmpId}
                onChange={(e) => setSelectedEmpId(e.target.value)}
              >
                <option value="">-- Choose Employee --</option>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.full_name} ({emp.availability_status}) - {emp.active_incident_count} active
                  </option>
                ))}
              </select>
            </div>

            <DialogFooter className="pt-2">
              <Button variant="outline" onClick={() => setIsAssignOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleManualAssign} disabled={isSubmitting || !selectedEmpId}>
                {isSubmitting ? 'Assigning...' : 'Confirm Assignment'}
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      {/* Send Incident to Group Dialog (Admin Selects Group -> IncidentFlow Evaluates & Assigns) */}
      <Dialog open={isSendToGroupOpen} onOpenChange={setIsSendToGroupOpen}>
        <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Layers className="h-5 w-5 text-indigo-600" />
              Send Incident to Group: {selectedIncident?.incident_number}
            </DialogTitle>
            <DialogDescription className="text-xs">
              Admin selects the target group. IncidentFlow deterministically evaluates active shift presence, workload priority, and next-shift fallback to assign the ticket.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 pt-2">
            {/* Target Group Selector */}
            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-1.5">
                Target Team / Group
              </label>
              <select
                className="w-full h-10 border rounded-md px-3 text-sm bg-background font-medium"
                value={targetTeamId}
                onChange={(e) => {
                  const newTeamId = e.target.value;
                  setTargetTeamId(newTeamId);
                  if (selectedIncident) fetchPreview(selectedIncident.id, newTeamId);
                }}
              >
                <option value="">-- Select Target Group --</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.work_domain || 'General Operations'})
                  </option>
                ))}
              </select>
            </div>

            {/* Smart Evaluation Preview Box */}
            {isPreviewLoading ? (
              <div className="p-4 border rounded-lg space-y-2 bg-muted/30 animate-pulse">
                <div className="h-4 bg-muted rounded w-1/2"></div>
                <div className="h-3 bg-muted rounded w-3/4"></div>
                <div className="h-12 bg-muted rounded w-full"></div>
              </div>
            ) : previewData ? (
              <div className="space-y-3 p-3.5 border rounded-lg bg-zinc-50 dark:bg-zinc-900/50">
                {/* Shift & Presence Stats */}
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="p-2.5 rounded bg-white dark:bg-zinc-800 border">
                    <span className="text-muted-foreground block font-medium">Active Shift</span>
                    <span className="font-semibold text-foreground flex items-center gap-1 mt-0.5">
                      <Clock className="h-3.5 w-3.5 text-indigo-500" />
                      {previewData.active_shift?.name || 'No Active Shift'}
                    </span>
                  </div>
                  <div className="p-2.5 rounded bg-white dark:bg-zinc-800 border">
                    <span className="text-muted-foreground block font-medium">Team Presence</span>
                    <span className="font-semibold text-foreground flex items-center gap-1 mt-0.5">
                      <Users className="h-3.5 w-3.5 text-emerald-500" />
                      {previewData.team_stats?.present_members ?? 0} Present / {previewData.team_stats?.total_members ?? 0} Members
                    </span>
                  </div>
                </div>

                {/* Candidate Decision Prediction Banner */}
                {previewData.predicted_decision === 'CURRENT_SHIFT_ZERO_WORK' && (
                  <div className="p-3 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-md text-xs">
                    <div className="flex items-center justify-between font-semibold text-emerald-800 dark:text-emerald-300 mb-1">
                      <span className="flex items-center gap-1">
                        <UserCheck className="h-4 w-4" />
                        Priority 1: Direct Assignment (0 Active Work)
                      </span>
                      <span className="text-[10px] bg-emerald-100 dark:bg-emerald-900 px-1.5 py-0.5 rounded uppercase">
                        Immediate
                      </span>
                    </div>
                    <p className="text-emerald-700 dark:text-emerald-400">
                      Predicted Assignee: <strong>{previewData.predicted_assignee?.name}</strong> ({previewData.predicted_assignee?.email}) — Currently carrying 0 active tickets.
                    </p>
                  </div>
                )}

                {previewData.predicted_decision === 'CURRENT_SHIFT_LEAST_WORKLOAD' && (
                  <div className="p-3 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 rounded-md text-xs">
                    <div className="flex items-center justify-between font-semibold text-blue-800 dark:text-blue-300 mb-1">
                      <span className="flex items-center gap-1">
                        <UserCheck className="h-4 w-4" />
                        Priority 2: Least Workload Assignment
                      </span>
                      <span className="text-[10px] bg-blue-100 dark:bg-blue-900 px-1.5 py-0.5 rounded uppercase">
                        Balanced
                      </span>
                    </div>
                    <p className="text-blue-700 dark:text-blue-400">
                      Predicted Assignee: <strong>{previewData.predicted_assignee?.name}</strong> ({previewData.predicted_assignee?.email}) — Carrying {previewData.predicted_assignee?.active_workload} active tickets (lowest among available).
                    </p>
                  </div>
                )}

                {previewData.predicted_decision === 'QUEUED_FOR_NEXT_SHIFT' && (
                  <div className="p-3 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-md text-xs">
                    <div className="flex items-center justify-between font-semibold text-amber-800 dark:text-amber-300 mb-1">
                      <span className="flex items-center gap-1">
                        <Clock className="h-4 w-4" />
                        Next Shift Fallback: Queued
                      </span>
                      <span className="text-[10px] bg-amber-100 dark:bg-amber-900 px-1.5 py-0.5 rounded uppercase">
                        Queued
                      </span>
                    </div>
                    <p className="text-amber-700 dark:text-amber-400">
                      No current-shift members available. Incident will be queued for <strong>{previewData.next_shift?.shift_name}</strong> starting {previewData.next_shift?.start_time || previewData.next_shift?.date}.
                    </p>
                    <p className="text-amber-700 dark:text-amber-400 mt-1">
                      Scheduled assignee: <strong>{previewData.predicted_assignee?.name}</strong>.
                    </p>
                  </div>
                )}

                {previewData.predicted_decision === 'UNASSIGNED_NO_ELIGIBLE_EMPLOYEES' && (
                  <div className="p-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-md text-xs">
                    <div className="flex items-center gap-1 font-semibold text-rose-800 dark:text-rose-300 mb-1">
                      <AlertCircle className="h-4 w-4" />
                      No Eligible Employees in Target Group
                    </div>
                    <p className="text-rose-700 dark:text-rose-400">
                      No active or scheduled candidates qualify. Incident will alert the group and remain in Assignment Pending status.
                    </p>
                  </div>
                )}

                {/* Candidate Workload Table */}
                {Array.isArray(previewData.eligible_candidates) && previewData.eligible_candidates.length > 0 && (
                  <div className="border rounded bg-white dark:bg-zinc-800 p-2 text-xs">
                    <span className="text-[11px] font-semibold text-muted-foreground block mb-1.5">
                      Evaluated Group Roster & Workloads ({previewData.eligible_candidates.length} evaluated)
                    </span>
                    <div className="max-h-32 overflow-y-auto space-y-1">
                      {previewData.eligible_candidates.map((cand: any, idx: number) => (
                        <div key={idx} className="flex items-center justify-between text-[11px] py-0.5 border-b border-zinc-100 dark:border-zinc-700 last:border-0">
                          <span className="font-medium text-foreground">{cand.name || cand.employee_name}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-muted-foreground">Workload: {cand.active_workload ?? cand.active_assignments ?? 0}</span>
                            {(cand.active_workload === 0 || cand.active_assignments === 0) ? (
                              <span className="text-[10px] bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 px-1 rounded font-semibold">Priority 1</span>
                            ) : (
                              <span className="text-[10px] bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300 px-1 rounded">Priority 2</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : null}

            {/* Custom Dispatch Message */}
            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-1.5">
                Optional Group Dispatch Notice / Note
              </label>
              <textarea
                className="w-full h-16 border rounded-md p-2.5 text-xs bg-background"
                placeholder="Notice: Assigned to your group via smart routing. Automatic evaluation running."
                value={groupCustomMessage}
                onChange={(e) => setGroupCustomMessage(e.target.value)}
              />
            </div>

            <DialogFooter className="pt-2">
              <Button variant="outline" onClick={() => setIsSendToGroupOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleSendToGroup}
                disabled={isSendingToGroup || !targetTeamId}
                className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium"
              >
                {isSendingToGroup ? 'Evaluating & Sending...' : 'Confirm & Send Incident to Group'}
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
