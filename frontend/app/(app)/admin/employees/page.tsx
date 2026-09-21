'use client';

import * as React from 'react';
import { useAdminEmployees } from '@/hooks/use-admin';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { StatusBadge } from '@/components/status-badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import { UserPlus, Search, ShieldCheck, Mail, RefreshCw, Smartphone } from 'lucide-react';
import { usePageSearch } from '@/hooks/use-page-search';
import { HighlightMatch } from '@/components/search/highlight-match';

export default function AdminEmployeesPage() {
  const { data: employees, isLoading, refetch } = useAdminEmployees();
  const [searchTerm, setSearchTerm] = React.useState('');
  const [isCreateOpen, setIsCreateOpen] = React.useState(false);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  // Form states
  const [fullName, setFullName] = React.useState('');
  const [email, setEmail] = React.useState('');
  const [teamName, setTeamName] = React.useState('MDM L3');
  const [role, setRole] = React.useState('EMPLOYEE');

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !fullName) {
      toast.error('Name and email are required');
      return;
    }
    setIsSubmitting(true);
    try {
      await apiClient.post('/api/admin/employees', {
        full_name: fullName,
        email: email,
        team_name: teamName,
        role: role,
        employee_code: `EMP${Math.floor(100 + Math.random() * 900)}`
      });
      toast.success(`Employee ${fullName} created successfully`);
      setIsCreateOpen(false);
      setFullName('');
      setEmail('');
      refetch();
    } catch (err: any) {
      toast.error(err?.message || 'Failed to create employee');
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleAvailability = async (emp: any) => {
    const nextStatus = emp.availability_status === 'AVAILABLE' ? 'BUSY' : 'AVAILABLE';
    try {
      await apiClient.patch(`/api/admin/employees/${emp.id}`, {
        availability_status: nextStatus
      });
      toast.success(`Updated ${emp.full_name} to ${nextStatus}`);
      refetch();
    } catch {
      toast.error('Failed to update status');
    }
  };

  const filtered = React.useMemo(() => {
    if (!Array.isArray(employees)) return [];
    return employees.filter(e =>
      (e?.full_name && e.full_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (e?.email && e.email.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (e?.team_name && e.team_name.toLowerCase().includes(searchTerm.toLowerCase()))
    );
  }, [employees, searchTerm]);

  const { searchQuery, setSearchQuery } = usePageSearch({
    pageName: 'Employees',
    placeholder: 'Filter employees on this page...',
    itemCount: Array.isArray(employees) ? employees.length : 0,
    filteredCount: filtered.length,
    onSearch: (q) => setSearchTerm(q),
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Employee Directory & Workload</h1>
          <p className="text-sm text-muted-foreground">Manage on-shift engineers, notification recipients & shift presence</p>
        </div>

        <div className="flex items-center gap-2">
          <Button onClick={() => setIsCreateOpen(true)} size="sm" className="gap-1.5 text-xs h-9">
            <UserPlus className="h-4 w-4" /> Add Employee
          </Button>
          <Button variant="outline" size="sm" onClick={() => refetch()} className="h-9 text-xs">
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Search Input */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Filter by name, email, or team..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="pl-9 h-9 text-sm"
        />
      </div>

      {/* Mobile-Friendly Cards for Screens < 768px, Table for Desktop */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
        </div>
      ) : (
        <>
          {/* Mobile Card List View */}
          <div className="grid grid-cols-1 gap-3 md:hidden">
            {filtered.map((emp) => (
              <Card key={emp.id} className="p-4 shadow-sm border space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="font-semibold text-sm">{emp.full_name}</h4>
                    <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                      <Mail className="h-3 w-3" /> {emp.email}
                    </p>
                  </div>
                  <StatusBadge status={emp.availability_status} type="availability" />
                </div>
                <div className="flex items-center justify-between text-xs pt-2 border-t">
                  <div>
                    <span className="text-muted-foreground">Team: </span>
                    <span className="font-medium">{emp.team_name || 'Assignment Pending'}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Incidents: </span>
                    <span className="font-semibold">{emp.active_incident_count} active</span>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => toggleAvailability(emp)}
                  className="w-full text-xs h-8"
                >
                  Set as {emp.availability_status === 'AVAILABLE' ? 'Busy' : 'Available'}
                </Button>
              </Card>
            ))}
          </div>

          {/* Desktop Table View */}
          <div className="hidden md:block rounded-md border bg-card shadow-sm overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Employee & Email</TableHead>
                  <TableHead>Team</TableHead>
                  <TableHead>Current Status</TableHead>
                  <TableHead>Active Load</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((emp) => (
                  <TableRow key={emp.id} className="hover:bg-muted/30">
                    <TableCell>
                      <div className="font-medium text-sm">
                        <HighlightMatch text={emp.full_name} query={searchTerm} />
                      </div>
                      <div className="text-xs text-muted-foreground">
                        <HighlightMatch text={emp.email} query={searchTerm} />
                      </div>
                    </TableCell>
                    <TableCell className="text-sm font-medium">
                      <HighlightMatch text={emp.team_name || '-'} query={searchTerm} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={emp.availability_status} type="availability" />
                    </TableCell>
                    <TableCell className="text-sm font-semibold">
                      {emp.active_incident_count} {emp.active_incident_count === 1 ? 'task' : 'tasks'}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleAvailability(emp)}
                        className="text-xs h-8"
                      >
                        Toggle Status
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}

      {/* Add Employee Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add New Employee</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4 pt-2">
            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-1">Full Name</label>
              <Input
                placeholder="e.g. Venkata Charan"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-1">Notification Email</label>
              <Input
                type="email"
                placeholder="e.g. charanvenkata07@gmail.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <p className="text-[11px] text-muted-foreground mt-1">
                Will receive incident assignments when scheduled and available.
              </p>
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground block mb-1">Team / Assignment Group</label>
              <Input
                placeholder="e.g. MDM L3, Analytics, Network"
                value={teamName}
                onChange={(e) => setTeamName(e.target.value)}
              />
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" onClick={() => setIsCreateOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? 'Saving...' : 'Save Employee'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
