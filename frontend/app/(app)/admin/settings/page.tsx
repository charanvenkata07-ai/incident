'use client';

import * as React from 'react';
import { useAdminSettings } from '@/hooks/use-admin';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

interface SettingsData {
  auto_assignment_enabled: boolean;
  assignment_strategy: string;
  dry_run_mode: boolean;
  shadow_mode: boolean;
  servicenow_connected: boolean;
}

export default function AdminSettingsPage() {
  const { data: settings, isLoading } = useAdminSettings() as { data: SettingsData | undefined; isLoading: boolean };

  if (isLoading) return <div className="space-y-4"><Skeleton className="h-8 w-48 mb-6"/><Card><CardContent className="h-32" /></Card></div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
      
      <Card>
        <CardHeader><CardTitle>Automation Settings</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex justify-between items-center py-2 border-b">
            <div>
              <p className="font-medium">Auto Assignment</p>
              <p className="text-sm text-muted-foreground">Automatically assign new incidents.</p>
            </div>
            <div>{settings?.auto_assignment_enabled ? 'Enabled' : 'Paused'}</div>
          </div>
          <div className="flex justify-between items-center py-2 border-b">
            <div>
              <p className="font-medium">Assignment Strategy</p>
            </div>
            <div className="font-mono text-sm">{settings?.assignment_strategy || 'ROUND_ROBIN'}</div>
          </div>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader><CardTitle>System Health</CardTitle></CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Health checks and component status will appear here.</div>
        </CardContent>
      </Card>
    </div>
  );
}
