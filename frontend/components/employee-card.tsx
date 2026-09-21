'use client';

import * as React from 'react';
import { Card, CardContent } from './ui/card';
import { StatusBadge } from './status-badge';
import type { Employee } from '@/types';
import { Badge } from './ui/badge';

export function EmployeeCard({ employee }: { employee: Employee }) {
  if (!employee) return null;
  const skills = Array.isArray(employee.skills) ? employee.skills : [];
  const activeCount = typeof employee.active_incident_count === 'number' ? employee.active_incident_count : 0;

  return (
    <Card>
      <CardContent className="p-4 flex flex-col space-y-3">
        <div className="flex items-center justify-between">
          <div className="font-medium text-sm">{employee.full_name || 'Team Member'}</div>
          {employee.availability_status && (
            <StatusBadge status={employee.availability_status} type="availability" />
          )}
        </div>
        <div className="text-xs text-muted-foreground">{employee.team_name || 'No Team'}</div>
        <div className="flex flex-wrap gap-1 mt-2">
          {skills.slice(0, 3).map((skill) => (
            <Badge key={skill.id} variant="secondary" className="text-[10px] px-1.5 py-0">
              {skill.name}
            </Badge>
          ))}
          {skills.length > 3 && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
              +{skills.length - 3}
            </Badge>
          )}
        </div>
        <div className="text-xs text-muted-foreground mt-2">
          Active Incidents: <span className="font-semibold text-foreground">{activeCount}</span>
        </div>
      </CardContent>
    </Card>
  );
}
