'use client';

import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { wsClient } from '@/lib/websocket';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  Activity, Server, Database, Radio, Globe, Shield, RefreshCw,
  CheckCircle2, AlertTriangle, XCircle, Zap, Mail, ArrowUpRight, Copy, Check
} from 'lucide-react';
import Link from 'next/link';

interface SystemDiagnostics {
  backend_status: string;
  database_status: string;
  redis_status: string;
  websocket_status: string;
  active_websocket_connections: number;
  cors_origins: string[];
  environment: string;
  automation_mode: string;
  live_pilot_enabled: boolean;
  servicenow_configured: boolean;
  email_provider: string;
}

export default function AdminDiagnosticsPage() {
  const [latency, setLatency] = React.useState<number | null>(null);
  const [copiedOrigin, setCopiedOrigin] = React.useState<string | null>(null);

  const { data, isLoading, isFetching, refetch } = useQuery<SystemDiagnostics>({
    queryKey: ['admin-diagnostics'],
    queryFn: async () => {
      const start = performance.now();
      const res = await apiClient.get<SystemDiagnostics>('/api/admin/diagnostics');
      const end = performance.now();
      setLatency(Math.round(end - start));
      return res;
    },
    refetchInterval: 15_000,
  });

  const handleCopyOrigin = (url: string) => {
    navigator.clipboard.writeText(url);
    setCopiedOrigin(url);
    setTimeout(() => setCopiedOrigin(null), 2000);
    toast.success('Origin URL copied to clipboard');
  };

  const getStatusBadge = (status?: string) => {
    if (!status) return null;
    const isOk = status === 'HEALTHY' || status === 'CONNECTED' || status === 'ACTIVE';
    return (
      <Badge
        variant={isOk ? 'default' : 'destructive'}
        className={isOk ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20' : ''}
      >
        {isOk ? <CheckCircle2 className="w-3 h-3 mr-1" /> : <AlertTriangle className="w-3 h-3 mr-1" />}
        {status}
      </Badge>
    );
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-black/[0.06] dark:border-white/[0.06] pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-500/10 text-brand-blue dark:text-brand-electric-blue">
              <Activity className="h-5 w-5" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-[#071A33] dark:text-white">
              System Diagnostics
            </h1>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time infrastructure health, database status, connection pools, and network origins
          </p>
        </div>

        <div className="flex items-center gap-3">
          {latency !== null && (
            <div className="text-xs font-mono px-3 py-1.5 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700">
              API Ping: <span className="font-semibold text-emerald-600 dark:text-emerald-400">{latency}ms</span>
            </div>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            className="rounded-xl active:scale-[0.98] transition-transform"
          >
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <Skeleton key={i} className="h-36 rounded-2xl" />
          ))}
        </div>
      ) : data ? (
        <>
          {/* Top Status Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Backend Server */}
            <Card className="rounded-2xl border-black/[0.08] dark:border-white/[0.08] bg-white/80 dark:bg-[#071426]/80 backdrop-blur-md shadow-sm">
              <CardHeader className="p-4 pb-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">FastAPI Backend</span>
                  <Server className="h-4 w-4 text-blue-500" />
                </div>
              </CardHeader>
              <CardContent className="p-4 pt-1 space-y-2">
                <div className="text-xl font-bold tracking-tight text-[#071A33] dark:text-white">
                  {data.backend_status}
                </div>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Env: {data.environment}</span>
                  {getStatusBadge(data.backend_status)}
                </div>
              </CardContent>
            </Card>

            {/* Database */}
            <Card className="rounded-2xl border-black/[0.08] dark:border-white/[0.08] bg-white/80 dark:bg-[#071426]/80 backdrop-blur-md shadow-sm">
              <CardHeader className="p-4 pb-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Primary Database</span>
                  <Database className="h-4 w-4 text-purple-500" />
                </div>
              </CardHeader>
              <CardContent className="p-4 pt-1 space-y-2">
                <div className="text-xl font-bold tracking-tight text-[#071A33] dark:text-white">
                  {data.database_status}
                </div>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>SQLite Pool</span>
                  {getStatusBadge(data.database_status)}
                </div>
              </CardContent>
            </Card>

            {/* Redis */}
            <Card className="rounded-2xl border-black/[0.08] dark:border-white/[0.08] bg-white/80 dark:bg-[#071426]/80 backdrop-blur-md shadow-sm">
              <CardHeader className="p-4 pb-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Redis Cache / PubSub</span>
                  <Zap className="h-4 w-4 text-amber-500" />
                </div>
              </CardHeader>
              <CardContent className="p-4 pt-1 space-y-2">
                <div className="text-xl font-bold tracking-tight text-[#071A33] dark:text-white">
                  {data.redis_status}
                </div>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>In-memory broker</span>
                  {getStatusBadge(data.redis_status)}
                </div>
              </CardContent>
            </Card>

            {/* WebSockets */}
            <Card className="rounded-2xl border-black/[0.08] dark:border-white/[0.08] bg-white/80 dark:bg-[#071426]/80 backdrop-blur-md shadow-sm">
              <CardHeader className="p-4 pb-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">WebSocket Engine</span>
                  <Radio className="h-4 w-4 text-emerald-500" />
                </div>
              </CardHeader>
              <CardContent className="p-4 pt-1 space-y-2">
                <div className="text-xl font-bold tracking-tight text-[#071A33] dark:text-white">
                  {data.websocket_status}
                </div>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{data.active_websocket_connections} active client(s)</span>
                  {getStatusBadge(data.websocket_status)}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Network & CORS Section */}
          <Card className="rounded-2xl border-black/[0.08] dark:border-white/[0.08] bg-white/80 dark:bg-[#071426]/80 backdrop-blur-md shadow-sm">
            <CardHeader className="p-5 pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <Globe className="h-4 w-4 text-blue-500" />
                    CORS Allowed Origins & Network Interfaces
                  </CardTitle>
                  <CardDescription className="text-xs mt-0.5">
                    Authorized browser origins permitted to exchange HTTP requests and WebSocket frames with the backend.
                  </CardDescription>
                </div>
                <Badge variant="outline" className="text-xs font-mono">
                  {data.cors_origins.length} Origins
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="p-5 pt-2">
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
                {data.cors_origins.map(origin => (
                  <div
                    key={origin}
                    className="flex items-center justify-between px-3 py-2 rounded-xl bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200/80 dark:border-zinc-700/60 text-xs font-mono"
                  >
                    <span className="truncate pr-2 text-zinc-800 dark:text-zinc-200">{origin}</span>
                    <button
                      onClick={() => handleCopyOrigin(origin)}
                      className="p-1 rounded hover:bg-zinc-200 dark:hover:bg-zinc-700 text-muted-foreground transition-colors shrink-0"
                      title="Copy Origin"
                    >
                      {copiedOrigin === origin ? (
                        <Check className="h-3.5 w-3.5 text-emerald-500" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Operational Modes & Integrations */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="rounded-2xl border-black/[0.08] dark:border-white/[0.08] bg-white/80 dark:bg-[#071426]/80 backdrop-blur-md shadow-sm">
              <CardHeader className="p-5 pb-3">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Shield className="h-4 w-4 text-indigo-500" />
                  Dispatch & Automation Policy
                </CardTitle>
                <CardDescription className="text-xs mt-0.5">
                  Automated routing rules and live pilot constraints
                </CardDescription>
              </CardHeader>
              <CardContent className="p-5 pt-2 space-y-3">
                <div className="flex items-center justify-between p-2.5 rounded-xl bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200/80 dark:border-zinc-700/60 text-xs">
                  <div>
                    <span className="font-semibold text-zinc-900 dark:text-zinc-100 block">Automation Engine Mode</span>
                    <span className="text-muted-foreground text-[11px]">Enforces deterministic employee allocation</span>
                  </div>
                  <Badge variant="secondary" className="font-bold font-mono text-[10px]">
                    {data.automation_mode}
                  </Badge>
                </div>

                <div className="flex items-center justify-between p-2.5 rounded-xl bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200/80 dark:border-zinc-700/60 text-xs">
                  <div>
                    <span className="font-semibold text-zinc-900 dark:text-zinc-100 block">Live Pilot Status</span>
                    <span className="text-muted-foreground text-[11px]">Internal enterprise pilot telemetry</span>
                  </div>
                  <Badge variant={data.live_pilot_enabled ? 'default' : 'outline'} className="font-bold text-[10px]">
                    {data.live_pilot_enabled ? 'ENABLED' : 'DISABLED'}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-2xl border-black/[0.08] dark:border-white/[0.08] bg-white/80 dark:bg-[#071426]/80 backdrop-blur-md shadow-sm">
              <CardHeader className="p-5 pb-3">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base font-semibold flex items-center gap-2">
                      <Mail className="h-4 w-4 text-cyan-500" />
                      External Connectors
                    </CardTitle>
                    <CardDescription className="text-xs mt-0.5">
                      ServiceNow enterprise sync & notification transports
                    </CardDescription>
                  </div>
                  <Link
                    href="/admin/integrations"
                    className="text-xs font-semibold text-brand-blue dark:text-brand-electric-blue hover:underline flex items-center gap-1"
                  >
                    Manage <ArrowUpRight className="h-3 w-3" />
                  </Link>
                </div>
              </CardHeader>
              <CardContent className="p-5 pt-2 space-y-3">
                <div className="flex items-center justify-between p-2.5 rounded-xl bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200/80 dark:border-zinc-700/60 text-xs">
                  <div>
                    <span className="font-semibold text-zinc-900 dark:text-zinc-100 block">ServiceNow Instance Sync</span>
                    <span className="text-muted-foreground text-[11px]">Table API, assignment groups, incident fields</span>
                  </div>
                  <Badge variant={data.servicenow_configured ? 'default' : 'secondary'} className="font-bold text-[10px]">
                    {data.servicenow_configured ? 'CONNECTED' : 'LOCAL MOCK / STAGING'}
                  </Badge>
                </div>

                <div className="flex items-center justify-between p-2.5 rounded-xl bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200/80 dark:border-zinc-700/60 text-xs">
                  <div>
                    <span className="font-semibold text-zinc-900 dark:text-zinc-100 block">Email Transport Service</span>
                    <span className="text-muted-foreground text-[11px]">Transactional notification delivery</span>
                  </div>
                  <Badge variant="outline" className="font-bold font-mono text-[10px]">
                    {data.email_provider}
                  </Badge>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      ) : (
        <div className="text-center py-16 text-muted-foreground">
          <AlertTriangle className="mx-auto h-8 w-8 mb-2 text-rose-500" />
          <p className="font-semibold">Unable to fetch system diagnostics.</p>
          <Button variant="outline" size="sm" onClick={() => refetch()} className="mt-3">
            Retry Connection
          </Button>
        </div>
      )}
    </div>
  );
}
