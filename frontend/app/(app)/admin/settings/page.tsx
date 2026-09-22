'use client';

import * as React from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAdminSettings } from '@/hooks/use-admin';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import { ShieldCheck, AlertTriangle, RefreshCw } from 'lucide-react';
import { ContextualHelp } from '@/components/help/contextual-help';

interface SettingsData {
  auto_assignment_enabled: boolean;
  automation_mode: string;
  assignment_strategy: string;
  dry_run_mode: boolean;
  shadow_mode: boolean;
  servicenow_connected: boolean;
  environment: string;
}

const REQUIRED_PHRASE = 'ENABLE LIVE ASSIGNMENT';

export default function AdminSettingsPage() {
  const queryClient = useQueryClient();
  const { data: settings, isLoading, refetch } = useAdminSettings() as {
    data: SettingsData | undefined;
    isLoading: boolean;
    refetch: () => void;
  };
  const [isConfirmLiveOpen, setIsConfirmLiveOpen] = React.useState(false);
  const [confirmationPhrase, setConfirmationPhrase] = React.useState('');
  const [isUpdating, setIsUpdating] = React.useState(false);

  // Sync mode changes via WebSocket
  React.useEffect(() => {
    const handleUpdate = () => {
      refetch();
      queryClient.invalidateQueries({ queryKey: ['admin-settings'] });
      queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
    };
    const { wsClient } = require('@/lib/websocket');
    wsClient.on('AUTOMATION_MODE_CHANGED', handleUpdate);
    wsClient.on('AUTOMATION_STATUS_CHANGED', handleUpdate);
    wsClient.on('SYSTEM_SETTING_UPDATED', handleUpdate);
    return () => {
      wsClient.off('AUTOMATION_MODE_CHANGED', handleUpdate);
      wsClient.off('AUTOMATION_STATUS_CHANGED', handleUpdate);
      wsClient.off('SYSTEM_SETTING_UPDATED', handleUpdate);
    };
  }, [refetch, queryClient]);

  const changeMode = async (targetMode: string, confirmed = false) => {
    // LIVE requires explicit confirmation dialog with typed phrase
    if (targetMode === 'LIVE' && !confirmed) {
      setConfirmationPhrase('');
      setIsConfirmLiveOpen(true);
      return;
    }
    setIsUpdating(true);
    try {
      await apiClient.post('/api/admin/automation/mode', {
        mode: targetMode,
        confirmed: true,
        confirmation_phrase: targetMode === 'LIVE' ? confirmationPhrase : '',
      });
      toast.success(`Automation mode switched to ${targetMode}`);
      setIsConfirmLiveOpen(false);
      setConfirmationPhrase('');
      refetch();
      queryClient.invalidateQueries({ queryKey: ['admin-settings'] });
      queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
    } catch (err: any) {
      toast.error(err?.message || 'Failed to update automation mode');
    } finally {
      setIsUpdating(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4 max-w-4xl mx-auto">
        <Skeleton className="h-8 w-48 mb-6" />
        <Card><CardContent className="h-32" /></Card>
      </div>
    );
  }

  const currentMode = settings?.automation_mode || 'DRY_RUN';

  return (
    <div className="space-y-6 max-w-4xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b pb-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">System Controls &amp; Staging Safety</h1>
          <p className="text-sm text-muted-foreground">Manage assignment mode, go-live safety checks &amp; strategy configuration</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()} className="h-9 text-xs">
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      {/* Mode Control Card */}
      <Card className="shadow-sm">
        <CardHeader className="p-4 sm:p-6 border-b">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base sm:text-lg font-semibold flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-blue-500" />
              Automation Lifecycle Mode
            </CardTitle>
            <ContextualHelp featureKey="shadow_mode" label="Mode rules" iconOnly={false} />
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Safely test incident routing without risking customer-facing changes in ServiceNow
          </p>
        </CardHeader>
        <CardContent className="p-4 sm:p-6 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* DRY RUN */}
            <div
              onClick={() => !isUpdating && changeMode('DRY_RUN')}
              className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                currentMode === 'DRY_RUN'
                  ? 'border-blue-500 bg-blue-50/50 dark:bg-blue-950/20'
                  : 'border-border hover:bg-muted/40'
              } ${isUpdating ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <div className="font-semibold text-sm flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
                DRY RUN
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Calculates and logs decisions. Zero ServiceNow writes.
              </p>
            </div>

            {/* SHADOW */}
            <div
              onClick={() => !isUpdating && changeMode('SHADOW')}
              className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                currentMode === 'SHADOW'
                  ? 'border-amber-500 bg-amber-50/50 dark:bg-amber-950/20'
                  : 'border-border hover:bg-muted/40'
              } ${isUpdating ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <div className="font-semibold text-sm flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                SHADOW
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Evaluates alongside humans for side-by-side verification.
              </p>
            </div>

            {/* LIVE */}
            <div
              onClick={() => !isUpdating && changeMode('LIVE')}
              className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                currentMode === 'LIVE'
                  ? 'border-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/20'
                  : 'border-border hover:bg-muted/40'
              } ${isUpdating ? 'opacity-50 pointer-events-none' : ''}`}
            >
              <div className="font-semibold text-sm flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                LIVE
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Full autonomous dispatch &amp; bidirectional ServiceNow sync.
              </p>
            </div>
          </div>

          <div className="p-3 bg-muted/40 rounded-lg text-xs flex items-center justify-between">
            <span className="text-muted-foreground">Active Automation State:</span>
            <span className="font-mono font-bold">{currentMode}</span>
          </div>
        </CardContent>
      </Card>

      {/* Engine Configuration */}
      <Card className="shadow-sm">
        <CardHeader className="p-4 sm:p-6 border-b">
          <CardTitle className="text-base sm:text-lg font-semibold">Engine Configuration</CardTitle>
        </CardHeader>
        <CardContent className="p-4 sm:p-6 space-y-4 text-sm">
          <div className="flex justify-between items-center py-2 border-b">
            <div>
              <p className="font-medium">Assignment Strategy</p>
              <p className="text-xs text-muted-foreground">Evaluates skills first, then least workload across active shifts</p>
            </div>
            <div className="font-mono font-semibold text-xs bg-muted px-2.5 py-1 rounded">
              {settings?.assignment_strategy || 'SKILL_PLUS_WORKLOAD'}
            </div>
          </div>

          <div className="flex justify-between items-center py-2 border-b">
            <div>
              <p className="font-medium">ServiceNow Mode</p>
              <p className="text-xs text-muted-foreground">Isolated staging mock adapter active</p>
            </div>
            <span className="text-xs font-semibold text-emerald-600">● MOCK ADAPTER</span>
          </div>

          <div className="flex justify-between items-center py-2">
            <div>
              <p className="font-medium">Circuit Breaker Max Retries</p>
              <p className="text-xs text-muted-foreground">Attempts exponential retry before dead-lettering</p>
            </div>
            <span className="font-mono font-bold text-xs">5 Retries</span>
          </div>
        </CardContent>
      </Card>

      {/* Go-Live Safety Confirmation Dialog */}
      <Dialog
        open={isConfirmLiveOpen}
        onOpenChange={(open) => {
          setIsConfirmLiveOpen(open);
          if (!open) setConfirmationPhrase('');
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-rose-600">
              <AlertTriangle className="h-5 w-5" />
              Confirm Switch to LIVE Mode
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2 text-sm">
            <p className="text-muted-foreground">
              You are about to enable <strong>LIVE autonomous routing</strong>.
            </p>
            <ul className="text-xs space-y-1.5 bg-muted/50 p-3 rounded list-disc list-inside">
              <li>Incidents will immediately be assigned to engineers in real time.</li>
              <li>ServiceNow assignments will be updated automatically via REST.</li>
              <li>Engineers will receive instant notifications upon dispatch.</li>
            </ul>
            <div className="space-y-2">
              <p className="text-xs font-semibold text-foreground">
                Type exactly to confirm:{' '}
                <code className="bg-muted px-1.5 py-0.5 rounded text-rose-600 font-mono">
                  {REQUIRED_PHRASE}
                </code>
              </p>
              <Input
                value={confirmationPhrase}
                onChange={(e) => setConfirmationPhrase(e.target.value)}
                placeholder={REQUIRED_PHRASE}
                className="font-mono text-xs"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && confirmationPhrase === REQUIRED_PHRASE) {
                    changeMode('LIVE', true);
                  }
                }}
              />
              {confirmationPhrase.length > 0 && confirmationPhrase !== REQUIRED_PHRASE && (
                <p className="text-xs text-rose-500">Phrase does not match. Check capitalisation and spacing.</p>
              )}
            </div>
          </div>
          <DialogFooter className="pt-2">
            <Button
              variant="outline"
              onClick={() => { setIsConfirmLiveOpen(false); setConfirmationPhrase(''); }}
            >
              Cancel
            </Button>
            <Button
              className="bg-rose-600 hover:bg-rose-700 text-white"
              onClick={() => changeMode('LIVE', true)}
              disabled={isUpdating || confirmationPhrase !== REQUIRED_PHRASE}
            >
              {isUpdating ? 'Activating...' : 'Yes, Activate LIVE'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
