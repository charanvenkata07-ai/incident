'use client';

import * as React from 'react';
import { Card, CardContent } from './ui/card';
import { StatusBadge } from './status-badge';
import type { Employee } from '@/types';
import { Badge } from './ui/badge';

export function EmployeeCard({ employee }: { employee: Employee }) {
  return (
    <Card>
      <CardContent className="p-4 flex flex-col space-y-3">
        <div className="flex items-center justify-between">
          <div className="font-medium text-sm">{employee.full_name}</div>
          <StatusBadge status={employee.availability_status} type="availability" />
        </div>
        <div className="text-xs text-muted-foreground">{employee.team_name || 'No Team'}</div>
        <div className="flex flex-wrap gap-1 mt-2">
          {employee.skills?.slice(0, 3).map((skill) => (
            <Badge key={skill.id} variant="secondary" className="text-[10px] px-1.5 py-0">
              {skill.name}
            </Badge>
          ))}
          {(employee.skills?.length || 0) > 3 && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
              +{employee.skills!.length - 3}
            </Badge>
          )}
        </div>
        <div className="text-xs text-muted-foreground mt-2">
          Active Incidents: <span className="font-semibold text-foreground">{employee.active_incident_count}</span>
        </div>
      </CardContent>
    </Card>
  );
}
