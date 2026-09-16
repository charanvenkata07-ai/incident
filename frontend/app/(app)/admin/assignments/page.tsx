'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/status-badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import { AlertCircle, UserCheck, RefreshCw, Layers } from 'lucide-react';

export default function AdminAssignmentsPage() {
  const [unassigned, setUnassigned] = React.useState<any[]>([]);
  const [employees, setEmployees] = React.useState<any[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [selectedIncident, setSelectedIncident] = React.useState<any | null>(null);
  const [selectedEmpId, setSelectedEmpId] = React.useState<string>('');
  const [isAssignOpen, setIsAssignOpen] = React.useState(false);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const loadData = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const [uncRes, empRes] = await Promise.all([
        apiClient.get<any[]>('/api/admin/incidents/unassigned'),
        apiClient.get<any[]>('/api/admin/employees'),
      ]);
      if (Array.isArray(uncRes)) setUnassigned(uncRes);
      if (Array.isArray(empRes)) setEmployees(empRes);
    } catch {
      toast.error('Failed to load queue data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

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

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Unassigned Incident Queue</h1>
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
              No unassigned incidents in the fallback queue. The assignment engine is running normally.
            </p>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {unassigned.map((inc) => (
            <Card key={inc.id} className="border-l-4 border-l-rose-500 shadow-sm p-4 sm:p-5">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-base">{inc.incident_number}</span>
                    <StatusBadge status={inc.priority} type="priority" />
                    <span className="text-xs bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300 font-medium px-2 py-0.5 rounded">
                      Unassigned
                    </span>
                  </div>
                  <h4 className="font-medium text-sm text-foreground">{inc.short_description}</h4>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground pt-1">
                    <AlertCircle className="h-3.5 w-3.5 text-rose-500 shrink-0" />
                    <span>{inc.reason}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-2 sm:pt-0 shrink-0">
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
    </div>
  );
}
