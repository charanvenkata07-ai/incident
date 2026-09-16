'use client';

import * as React from 'react';
import { useAdminEmployees } from '@/hooks/use-admin';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { StatusBadge } from '@/components/status-badge';
import { Skeleton } from '@/components/ui/skeleton';

export default function AdminEmployeesPage() {
  const { data: employees, isLoading } = useAdminEmployees();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Employees</h1>
      
      {isLoading ? <Skeleton className="h-64 w-full" /> : (
        <div className="rounded-md border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Team</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Active Incidents</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Array.isArray(employees) && employees.map((emp: any) => (
                <TableRow key={emp.id}>
                  <TableCell className="font-medium">{emp.full_name}</TableCell>
                  <TableCell>{emp.team_name || '-'}</TableCell>
                  <TableCell><StatusBadge status={emp.availability_status} type="availability" /></TableCell>
                  <TableCell>{emp.active_incident_count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
