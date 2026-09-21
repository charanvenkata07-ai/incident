'use client';

import * as React from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Activity,
  Users,
  Clock,
  AlertTriangle,
  Shield,
  Send,
  MessageSquare,
  Search,
  RefreshCw,
  ExternalLink,
  ChevronRight,
  Filter,
  CheckCircle2,
  XCircle,
  AlertCircle,
  BarChart3,
  Calendar,
  Layers,
  Phone,
  Mail,
  UserCheck,
  UserX,
  PlayCircle,
  CheckSquare,
  Hash,
  Copy,
  Check
} from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import { wsClient } from '@/lib/websocket';
import { useAuth } from '@/hooks/use-auth';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';

// Types matching backend schemas
interface GroupActivityHeader {
  team_id: string;
  name: string;
  work_domain?: string;
  description?: string;
  servicenow_group_id?: string;
  is_active: boolean;
  active_shift_name?: string;
  shift_window?: string;
  health_status: 'HEALTHY' | 'DEGRADED' | 'ATTENTION';
  total_members: number;
  on_shift_count: number;
  present_count: number;
  available_count: number;
  busy_count: number;
  active_incidents_count: number;
  unassigned_incidents_count: number;
}

interface AssignedIncidentBrief {
  id: string;
  incident_number: string;
  short_description: string;
  priority: string;
  state: string;
  assigned_at?: string;
}

interface EmployeeActivityCard {
  employee_id: string;
  user_id: string;
  full_name: string;
  email: string;
  role: string;
  employee_code?: string;
  is_present: boolean;
  availability_status: string;
  on_shift: boolean;
  current_shift_name?: string;
  active_incident_count: number;
  active_incidents: AssignedIncidentBrief[];
  last_active_at?: string;
}

interface WorkBoardItem {
  id: string;
  incident_number: string;
  short_description: string;
  priority: string;
  state: string;
  assigned_to?: string;
  assigned_employee_id?: string;
  assigned_at?: string;
  created_at: string;
  elapsed_minutes: number;
}

interface WorkBoardColumns {
  unassigned: WorkBoardItem[];
  assigned: WorkBoardItem[];
  in_progress: WorkBoardItem[];
  blocked: WorkBoardItem[];
  completed_today: WorkBoardItem[];
}

interface GroupActivityOverview {
  header: GroupActivityHeader;
  members: EmployeeActivityCard[];
  work_board: WorkBoardColumns;
}

interface TimelineEvent {
  id: string;
  event_type: string;
  title: string;
  description: string;
  actor_name?: string;
  created_at: string;
  metadata?: any;
}

interface ConversationItem {
  id: string;
  type: string;
  name?: string;
  incident_number?: string;
  member_count: number;
  last_message?: {
    content: string;
    sender_name: string;
    created_at: string;
  };
}

interface ChatMessage {
  id: string;
  conversation_id: string;
  sender_id: string;
  sender_name: string;
  sender_role: string;
  message_type: string;
  content: string;
  created_at: string;
}

interface GroupAnalytics {
  period: string;
  total_incidents: number;
  resolved_count: number;
  unassigned_count: number;
  avg_assignment_minutes: number;
  avg_resolution_minutes: number;
  auto_assignment_rate_pct: number;
  workload_distribution: Array<{
    employee_id: string;
    employee_name: string;
    assigned_count: number;
    completed_count: number;
  }>;
}

interface NoticeAssignmentResult {
  incident_id?: string;
  incident_number?: string;
  short_description?: string;
  description?: string;
  priority?: string;
  impact?: string;
  urgency?: string;
  category?: string;
  subcategory?: string;
  target_group?: string;
  assignment_group?: string;
  configuration_item?: string;
  caller?: string;
  location?: string;
  opened_at?: string;
  notice_sent_time: string;
  assignment_status: 'ASSIGNED' | 'UNASSIGNED' | 'Assignment Pending' | string;
  assigned_employee_name?: string;
  assigned_employee_code?: string;
  rotation_position?: number;
  rotation_cycle?: number;
  employee_id?: string;
  assignment_time?: string;
  employee_presence?: string;
  current_task?: string;
  task_status?: string;
  unassigned_reason?: string;
  pending_reason?: string;
  notice_success_count?: number;
  notice_failed_count?: number;
  notice_body?: string;
  timeline_events?: string[];
}

export default function GroupActivityPage() {
  const params = useParams();
  const router = useRouter();
  const teamId = params?.teamId as string;
  const { user } = useAuth();

  // Active tab state
  const [activeTab, setActiveTab] = React.useState('overview');

  // Core Overview Data
  const [overview, setOverview] = React.useState<GroupActivityOverview | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isRefreshing, setIsRefreshing] = React.useState(false);

  // Timeline Data
  const [timeline, setTimeline] = React.useState<TimelineEvent[]>([]);
  const [timelineFilter, setTimelineFilter] = React.useState<string>('ALL');
  const [isTimelineLoading, setIsTimelineLoading] = React.useState(false);

  // Chat Data
  const [conversations, setConversations] = React.useState<ConversationItem[]>([]);
  const [selectedConvId, setSelectedConvId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [newMessageText, setNewMessageText] = React.useState('');
  const [isSendingMessage, setIsSendingMessage] = React.useState(false);
  const [chatSearchQuery, setChatSearchQuery] = React.useState('');
  const [searchResults, setSearchResults] = React.useState<ChatMessage[] | null>(null);
  const [isSearchingChat, setIsSearchingChat] = React.useState(false);

  // Analytics Data
  const [analytics, setAnalytics] = React.useState<GroupAnalytics | null>(null);
  const [analyticsPeriod, setAnalyticsPeriod] = React.useState('7d');
  const [isAnalyticsLoading, setIsAnalyticsLoading] = React.useState(false);

  // Employee Details Drawer
  const [selectedEmployeeId, setSelectedEmployeeId] = React.useState<string | null>(null);
  const [employeeDrawerData, setEmployeeDrawerData] = React.useState<any | null>(null);
  const [isDrawerLoading, setIsDrawerLoading] = React.useState(false);

  // Send Notice Dialog
  const [isNoticeOpen, setIsNoticeOpen] = React.useState(false);
  const [noticeTitle, setNoticeTitle] = React.useState('');
  const [noticeMessage, setNoticeMessage] = React.useState('');
  const [noticePriority, setNoticePriority] = React.useState('P2');
  const [noticeImpact, setNoticeImpact] = React.useState('High');
  const [noticeUrgency, setNoticeUrgency] = React.useState('High');
  const [noticeCategory, setNoticeCategory] = React.useState('');
  const [noticeSubcategory, setNoticeSubcategory] = React.useState('');
  const [noticeCi, setNoticeCi] = React.useState('');
  const [noticeCaller, setNoticeCaller] = React.useState('Operations Center');
  const [noticeLocation, setNoticeLocation] = React.useState('');
  const [noticeWorkInstructions, setNoticeWorkInstructions] = React.useState('');
  const [autoAssign, setAutoAssign] = React.useState(true);
  const [isSendingNotice, setIsSendingNotice] = React.useState(false);
  const [showAdvancedNoticeFields, setShowAdvancedNoticeFields] = React.useState(false);

  // Assignment Result Display Modal
  const [assignmentResult, setAssignmentResult] = React.useState<NoticeAssignmentResult | null>(null);
  const [copiedId, setCopiedId] = React.useState(false);
  const [copiedNotice, setCopiedNotice] = React.useState(false);

  // Load Overview Data
  const loadOverview = React.useCallback(async (silent = false) => {
    if (!teamId) return;
    if (!silent) setIsLoading(true);
    else setIsRefreshing(true);
    try {
      const data = await apiClient.get<GroupActivityOverview>(`/api/admin/teams/${teamId}/activity`);
      setOverview(data);
    } catch (err: any) {
      toast.error(err?.message || 'Failed to load group activity overview');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [teamId]);

  // Load Timeline
  const loadTimeline = React.useCallback(async () => {
    if (!teamId) return;
    setIsTimelineLoading(true);
    try {
      const q = timelineFilter !== 'ALL' ? `?event_type=${timelineFilter}` : '';
      const data = await apiClient.get<TimelineEvent[]>(`/api/admin/teams/${teamId}/activity/timeline${q}`);
      setTimeline(data);
    } catch (err: any) {
      toast.error('Failed to load activity timeline');
    } finally {
      setIsTimelineLoading(false);
    }
  }, [teamId, timelineFilter]);

  // Load Conversations
  const loadConversations = React.useCallback(async () => {
    if (!teamId) return;
    try {
      const data = await apiClient.get<ConversationItem[]>(`/api/admin/teams/${teamId}/conversations`);
      setConversations(data);
      if (data.length > 0 && !selectedConvId) {
        setSelectedConvId(data[0].id);
      }
    } catch (err: any) {
      // ignore
    }
  }, [teamId, selectedConvId]);

  // Load Messages for selected conversation
  const loadMessages = React.useCallback(async (convId: string) => {
    try {
      const msgs = await apiClient.get<ChatMessage[]>(`/api/chat/conversations/${convId}/messages`);
      setMessages(msgs);
      // Audit view
      await apiClient.post(`/api/admin/chat/conversations/${convId}/audit-view`, {});
    } catch (err: any) {
      // ignore
    }
  }, []);

  // Load Analytics
  const loadAnalytics = React.useCallback(async (period: string) => {
    if (!teamId) return;
    setIsAnalyticsLoading(true);
    try {
      const data = await apiClient.get<GroupAnalytics>(`/api/admin/teams/${teamId}/analytics?period=${period}`);
      setAnalytics(data);
    } catch (err: any) {
      toast.error('Failed to load group analytics');
    } finally {
      setIsAnalyticsLoading(false);
    }
  }, [teamId]);

  // Initial load
  React.useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  // Secondary tab data triggers
  React.useEffect(() => {
    if (activeTab === 'timeline') {
      loadTimeline();
    } else if (activeTab === 'chat') {
      loadConversations();
    } else if (activeTab === 'analytics') {
      loadAnalytics(analyticsPeriod);
    }
  }, [activeTab, loadTimeline, loadConversations, loadAnalytics, analyticsPeriod]);

  // Load messages when conversation selected
  React.useEffect(() => {
    if (selectedConvId && activeTab === 'chat') {
      loadMessages(selectedConvId);
    }
  }, [selectedConvId, activeTab, loadMessages]);

  // Load employee drawer data when employee selected
  React.useEffect(() => {
    if (selectedEmployeeId) {
      setIsDrawerLoading(true);
      apiClient
        .get(`/api/admin/employees/${selectedEmployeeId}/activity`)
        .then(res => setEmployeeDrawerData(res))
        .catch(() => toast.error('Failed to load employee details'))
        .finally(() => setIsDrawerLoading(false));
    } else {
      setEmployeeDrawerData(null);
    }
  }, [selectedEmployeeId]);

  // WebSocket Live Subscription for Real-time Activity
  React.useEffect(() => {
    const handleActivityEvent = (data: any) => {
      // Silent refresh overview to reflect realtime updates
      loadOverview(true);
      if (activeTab === 'timeline') loadTimeline();
      if (activeTab === 'analytics') loadAnalytics(analyticsPeriod);

      // If notice assignment result broadcast received, update modal if open
      if (data?.action === 'NOTICE_ASSIGNMENT_RESULT') {
        toast.info(`Group Event: ${data.incident_number} — ${data.assignment_status}`);
      }
    };

    const handleChatMessage = (msg: any) => {
      if (msg.conversation_id === selectedConvId) {
        setMessages(prev => {
          if (prev.some(m => m.id === msg.id)) return prev;
          return [...prev, msg];
        });
      }
      loadConversations();
    };

    wsClient.on('GROUP_ACTIVITY_EVENT', handleActivityEvent);
    wsClient.on('CHAT_MESSAGE_CREATED', handleChatMessage);

    return () => {
      wsClient.off('GROUP_ACTIVITY_EVENT', handleActivityEvent);
      wsClient.off('CHAT_MESSAGE_CREATED', handleChatMessage);
    };
  }, [loadOverview, loadTimeline, loadAnalytics, activeTab, analyticsPeriod, selectedConvId, loadConversations]);

  // Chat message send handler
  const handleSendMessage = async () => {
    if (!selectedConvId || !newMessageText.trim()) return;
    setIsSendingMessage(true);
    try {
      const sent = await apiClient.post<ChatMessage>(`/api/chat/conversations/${selectedConvId}/messages`, {
        content: newMessageText.trim(),
        message_type: 'TEXT',
      });
      setMessages(prev => [...prev, sent]);
      setNewMessageText('');
      loadConversations();
    } catch (err: any) {
      toast.error(err?.message || 'Failed to send message');
    } finally {
      setIsSendingMessage(false);
    }
  };

  // Chat Search Handler
  const handleChatSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatSearchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    setIsSearchingChat(true);
    try {
      const results = await apiClient.get<ChatMessage[]>(
        `/api/admin/teams/${teamId}/chat/search?q=${encodeURIComponent(chatSearchQuery.trim())}`
      );
      setSearchResults(results);
    } catch (err: any) {
      toast.error('Search failed');
    } finally {
      setIsSearchingChat(false);
    }
  };

  // Direct chat initiation
  const handleStartDirectChat = async (targetUserId: string) => {
    try {
      const conv = await apiClient.post<any>('/api/chat/conversations/direct', {
        other_user_id: targetUserId,
      });
      setActiveTab('chat');
      setSelectedConvId(conv.id);
      loadConversations();
    } catch (err: any) {
      toast.error(err?.message || 'Failed to start direct chat');
    }
  };

  // Send Notice & Auto-Assign Handler
  const handleSendNotice = async () => {
    if (!noticeTitle.trim() || !noticeMessage.trim()) {
      toast.error('Title and message are required');
      return;
    }
    setIsSendingNotice(true);
    try {
      const res = await apiClient.post<NoticeAssignmentResult>(`/api/admin/teams/${teamId}/notice`, {
        title: noticeTitle.trim(),
        message: noticeMessage.trim(),
        priority: noticePriority,
        impact: noticeImpact,
        urgency: noticeUrgency,
        category: noticeCategory.trim() || (overview?.header?.work_domain || overview?.header?.name.split(' ')[0] || 'General'),
        subcategory: noticeSubcategory.trim() || undefined,
        configuration_item: noticeCi.trim() || (overview?.header ? `${overview.header.name} Production System` : undefined),
        caller: noticeCaller.trim() || undefined,
        location: noticeLocation.trim() || undefined,
        work_instructions: noticeWorkInstructions.trim() || noticeMessage.trim(),
        auto_assign: autoAssign,
      });

      // Close notice input dialog
      setIsNoticeOpen(false);
      setNoticeTitle('');
      setNoticeMessage('');
      setNoticeWorkInstructions('');

      // Open Assignment Result Modal immediately
      setAssignmentResult(res);

      if (res.assignment_status === 'ASSIGNED') {
        toast.success(`Assigned to: ${res.assigned_employee_name}`);
      } else {
        toast.warning(`Incident created (${res.incident_number}): Assignment Pending`);
      }

      // Refresh overview and board
      loadOverview(true);
      if (activeTab === 'timeline') loadTimeline();
    } catch (err: any) {
      toast.error(err?.message || 'Failed to send notice and execute assignment');
    } finally {
      setIsSendingNotice(false);
    }
  };

  // Copy incident ID helper
  const copyIncidentId = (idText?: string) => {
    if (!idText) return;
    navigator.clipboard.writeText(idText);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
    toast.success('Incident ID copied to clipboard');
  };

  // Format Elapsed Time
  const formatElapsed = (minutes: number) => {
    if (minutes < 60) return `${minutes}m`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}h ${m}m`;
  };

  // SLA Color helper
  const getSlaBadgeClass = (priority: string, elapsedMinutes: number) => {
    let limitMinutes = 240; // 4h default
    if (priority === 'P1') limitMinutes = 30;
    else if (priority === 'P2') limitMinutes = 60;
    else if (priority === 'P3') limitMinutes = 180;

    const ratio = elapsedMinutes / limitMinutes;
    if (ratio >= 1) return 'bg-red-500/10 text-red-600 border-red-200 dark:border-red-900/50';
    if (ratio >= 0.75) return 'bg-amber-500/10 text-amber-600 border-amber-200 dark:border-amber-900/50';
    return 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300';
  };

  if (isLoading || !overview) {
    return (
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        <div className="flex items-center gap-4">
          <Skeleton className="h-8 w-8 rounded-full" />
          <div className="space-y-2">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-96" />
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  const { header, members, work_board } = overview;

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* 1. Header & Navigation */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b pb-5">
        <div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
            <Link href="/admin/groups" className="hover:underline flex items-center gap-1">
              <ArrowLeft className="h-3 w-3" /> Groups
            </Link>
            <span>/</span>
            <span>{header.name}</span>
            <span>/</span>
            <span className="text-foreground font-medium">Activity Workspace</span>
          </div>

          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">{header.name}</h1>
            <Badge
              variant="outline"
              className={
                header.health_status === 'HEALTHY'
                  ? 'bg-emerald-500/10 text-emerald-600 border-emerald-300 dark:border-emerald-800'
                  : header.health_status === 'DEGRADED'
                  ? 'bg-amber-500/10 text-amber-600 border-amber-300 dark:border-amber-800'
                  : 'bg-rose-500/10 text-rose-600 border-rose-300 dark:border-rose-800'
              }
            >
              <Activity className="mr-1 h-3 w-3" />
              {header.health_status}
            </Badge>

            {header.work_domain && (
              <Badge variant="secondary" className="text-xs">
                Domain: {header.work_domain}
              </Badge>
            )}
          </div>

          <p className="text-sm text-muted-foreground mt-1">
            {header.description || 'Enterprise Operational Group Workspace'} &bull; ServiceNow ID: {header.servicenow_group_id || 'N/A'}
          </p>
        </div>

        {/* Header Action Buttons */}
        <div className="flex items-center gap-2.5">
          <Button
            variant="outline"
            size="sm"
            onClick={() => loadOverview(true)}
            disabled={isRefreshing}
            className="text-xs"
          >
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </Button>

          <Button
            size="sm"
            onClick={() => setIsNoticeOpen(true)}
            className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium"
          >
            <Send className="mr-1.5 h-3.5 w-3.5" />
            Send Notice / Assign
          </Button>
        </div>
      </div>

      {/* 2. Shift Coverage & Live Metric Pills Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <Card className="bg-muted/40 border-muted">
          <CardContent className="p-3">
            <div className="text-[11px] font-medium text-muted-foreground uppercase flex items-center gap-1">
              <Clock className="h-3 w-3 text-indigo-500" /> Active Shift
            </div>
            <div className="text-sm font-semibold truncate mt-1">
              {header.active_shift_name || 'No Shift'}
            </div>
            <div className="text-[10px] text-muted-foreground truncate">
              {header.shift_window || 'Coverage standard'}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-muted/40 border-muted">
          <CardContent className="p-3">
            <div className="text-[11px] font-medium text-muted-foreground uppercase flex items-center gap-1">
              <Users className="h-3 w-3 text-slate-500" /> Members
            </div>
            <div className="text-lg font-bold mt-0.5">{header.total_members}</div>
            <div className="text-[10px] text-muted-foreground">{header.on_shift_count} on shift today</div>
          </CardContent>
        </Card>

        <Card className="bg-muted/40 border-muted">
          <CardContent className="p-3">
            <div className="text-[11px] font-medium text-muted-foreground uppercase flex items-center gap-1">
              <UserCheck className="h-3 w-3 text-emerald-500" /> Present
            </div>
            <div className="text-lg font-bold text-emerald-600 dark:text-emerald-400 mt-0.5">
              {header.present_count}
            </div>
            <div className="text-[10px] text-muted-foreground">Checked in now</div>
          </CardContent>
        </Card>

        <Card className="bg-muted/40 border-muted">
          <CardContent className="p-3">
            <div className="text-[11px] font-medium text-muted-foreground uppercase flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3 text-blue-500" /> Available
            </div>
            <div className="text-lg font-bold text-blue-600 dark:text-blue-400 mt-0.5">
              {header.available_count}
            </div>
            <div className="text-[10px] text-muted-foreground">Ready for intake</div>
          </CardContent>
        </Card>

        <Card className="bg-muted/40 border-muted">
          <CardContent className="p-3">
            <div className="text-[11px] font-medium text-muted-foreground uppercase flex items-center gap-1">
              <PlayCircle className="h-3 w-3 text-amber-500" /> Busy
            </div>
            <div className="text-lg font-bold text-amber-600 dark:text-amber-400 mt-0.5">
              {header.busy_count}
            </div>
            <div className="text-[10px] text-muted-foreground">Actively engaged</div>
          </CardContent>
        </Card>

        <Card className="bg-muted/40 border-muted">
          <CardContent className="p-3">
            <div className="text-[11px] font-medium text-muted-foreground uppercase flex items-center gap-1">
              <Layers className="h-3 w-3 text-purple-500" /> Active Work
            </div>
            <div className="text-lg font-bold text-purple-600 dark:text-purple-400 mt-0.5">
              {header.active_incidents_count}
            </div>
            <div className="text-[10px] text-muted-foreground">Group assignments</div>
          </CardContent>
        </Card>

        <Card className={`border ${header.unassigned_incidents_count > 0 ? 'bg-amber-500/10 border-amber-300 dark:border-amber-900' : 'bg-muted/40 border-muted'}`}>
          <CardContent className="p-3">
            <div className="text-[11px] font-medium text-muted-foreground uppercase flex items-center gap-1">
              <AlertTriangle className={`h-3 w-3 ${header.unassigned_incidents_count > 0 ? 'text-amber-500' : 'text-slate-400'}`} />
              Assignment Pending
            </div>
            <div className={`text-lg font-bold mt-0.5 ${header.unassigned_incidents_count > 0 ? 'text-amber-600 dark:text-amber-400' : ''}`}>
              {header.unassigned_incidents_count}
            </div>
            <div className="text-[10px] text-muted-foreground">Awaiting assignment</div>
          </CardContent>
        </Card>
      </div>

      {/* 3. Main Operational Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="bg-muted/60 p-1 border">
          <TabsTrigger value="overview" className="text-xs flex items-center gap-1.5">
            <Users className="h-3.5 w-3.5" /> Overview & Roster ({members.length})
          </TabsTrigger>
          <TabsTrigger value="workboard" className="text-xs flex items-center gap-1.5">
            <Layers className="h-3.5 w-3.5" /> Work Board ({header.active_incidents_count})
          </TabsTrigger>
          <TabsTrigger value="timeline" className="text-xs flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5" /> Live Timeline
          </TabsTrigger>
          <TabsTrigger value="chat" className="text-xs flex items-center gap-1.5">
            <MessageSquare className="h-3.5 w-3.5" /> Collaboration & Chat
          </TabsTrigger>
          <TabsTrigger value="analytics" className="text-xs flex items-center gap-1.5">
            <BarChart3 className="h-3.5 w-3.5" /> Group Analytics
          </TabsTrigger>
        </TabsList>

        {/* =====================================================================
            TAB 1: OVERVIEW & ROSTER
            ===================================================================== */}
        <TabsContent value="overview" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Group Members & Active Operations</h2>
            <span className="text-xs text-muted-foreground">
              Real enterprise data &bull; Active shift prioritized
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {members.map(member => (
              <Card
                key={member.employee_id}
                className={`transition-all hover:shadow-md ${
                  member.on_shift
                    ? 'border-indigo-200 dark:border-indigo-950/60 bg-card'
                    : 'border-muted bg-muted/20 opacity-85'
                }`}
              >
                <CardHeader className="p-4 pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <Avatar className="h-10 w-10 border border-border">
                        <AvatarFallback className="bg-indigo-100 dark:bg-indigo-950/50 text-indigo-700 dark:text-indigo-300 font-semibold text-xs">
                          {member.full_name
                            .split(' ')
                            .map(n => n[0])
                            .slice(0, 2)
                            .join('')}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <div className="font-semibold text-sm leading-tight flex items-center gap-1.5">
                          {member.full_name}
                          {member.is_present && (
                            <span className="h-2 w-2 rounded-full bg-emerald-500 inline-block" title="Present & Checked In" />
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground truncate max-w-[160px]">
                          {member.email}
                        </div>
                      </div>
                    </div>

                    <Badge
                      variant="outline"
                      className={`text-[10px] font-medium uppercase ${
                        member.availability_status === 'AVAILABLE'
                          ? 'bg-emerald-500/10 text-emerald-600 border-emerald-200'
                          : member.availability_status === 'BUSY'
                          ? 'bg-amber-500/10 text-amber-600 border-amber-200'
                          : 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400'
                      }`}
                    >
                      {member.availability_status}
                    </Badge>
                  </div>
                </CardHeader>

                <CardContent className="p-4 pt-2 space-y-3">
                  {/* Status Pills */}
                  <div className="flex items-center flex-wrap gap-1.5 text-[11px]">
                    <span
                      className={`px-2 py-0.5 rounded-full font-medium ${
                        member.on_shift
                          ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300'
                          : 'bg-muted text-muted-foreground'
                      }`}
                    >
                      {member.on_shift ? `On Shift: ${member.current_shift_name || 'Active'}` : 'Off Shift'}
                    </span>

                    <span
                      className={`px-2 py-0.5 rounded-full font-medium ${
                        member.is_present
                          ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300'
                          : 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300'
                      }`}
                    >
                      {member.is_present ? 'Checked In' : 'Checked Out'}
                    </span>

                    {member.employee_code && (
                      <span className="px-1.5 py-0.5 rounded bg-muted text-[10px] font-mono text-muted-foreground">
                        {member.employee_code}
                      </span>
                    )}
                  </div>

                  {/* Active Incidents Summary */}
                  <div className="border-t pt-2.5">
                    <div className="flex items-center justify-between text-xs mb-1.5">
                      <span className="text-muted-foreground">Active Workload</span>
                      <span className="font-semibold text-foreground">
                        {member.active_incident_count} {member.active_incident_count === 1 ? 'incident' : 'incidents'}
                      </span>
                    </div>

                    {member.active_incidents.length > 0 ? (
                      <div className="space-y-1.5">
                        {member.active_incidents.slice(0, 2).map(inc => (
                          <div
                            key={inc.id}
                            className="text-xs p-1.5 rounded bg-muted/50 flex items-center justify-between gap-2 border border-muted"
                          >
                            <div className="truncate flex items-center gap-1.5">
                              <Badge variant="outline" className="text-[9px] px-1 py-0 uppercase">
                                {inc.priority}
                              </Badge>
                              <span className="font-mono text-[11px] font-medium text-foreground">
                                {inc.incident_number}
                              </span>
                              <span className="truncate text-muted-foreground text-[11px]">
                                {inc.short_description}
                              </span>
                            </div>
                            <Badge variant="secondary" className="text-[9px] px-1 py-0 shrink-0 uppercase">
                              {inc.state}
                            </Badge>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-[11px] text-muted-foreground italic py-1">
                        No active incidents currently assigned.
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center justify-end gap-2 pt-1 border-t">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs px-2"
                      onClick={() => handleStartDirectChat(member.user_id)}
                    >
                      <MessageSquare className="mr-1 h-3 w-3" /> Chat
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs px-2.5"
                      onClick={() => setSelectedEmployeeId(member.employee_id)}
                    >
                      View Details
                      <ChevronRight className="ml-1 h-3 w-3" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* =====================================================================
            TAB 2: WORK BOARD (5 KANBAN COLUMNS)
            ===================================================================== */}
        <TabsContent value="workboard" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Operational Work Board</h2>
            <span className="text-xs text-muted-foreground">
              Live progression & SLA elapsed timer &bull; Real-time updates
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-3.5">
            {/* Column 1: Assignment Pending */}
            <div className="flex flex-col rounded-lg border bg-muted/20 p-3 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b">
                <span className="font-semibold text-xs uppercase tracking-wide text-amber-600 dark:text-amber-400 flex items-center gap-1.5">
                  <AlertCircle className="h-3.5 w-3.5" /> Assignment Pending
                </span>
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                  {work_board.unassigned.length}
                </Badge>
              </div>

              <div className="space-y-2.5 min-h-[350px]">
                {work_board.unassigned.length === 0 ? (
                  <div className="text-center py-8 text-xs text-muted-foreground">No pending items</div>
                ) : (
                  work_board.unassigned.map(item => (
                    <Card key={item.id} className="p-3 hover:shadow-sm border-l-4 border-l-red-500 space-y-2">
                      <div className="flex items-center justify-between gap-1">
                        <Link
                          href={`/incidents/${item.incident_number}`}
                          className="font-mono text-xs font-semibold hover:underline text-indigo-600 dark:text-indigo-400 flex items-center gap-1"
                        >
                          {item.incident_number}
                          <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                        </Link>
                        <Badge variant="outline" className="text-[9px] px-1 py-0 uppercase">
                          {item.priority}
                        </Badge>
                      </div>

                      <p className="text-xs font-medium text-foreground line-clamp-2 leading-snug">
                        {item.short_description}
                      </p>

                      <div className="flex items-center justify-between pt-1 border-t text-[10px]">
                        <span className="text-muted-foreground">Waiting triage</span>
                        <span className={`px-1.5 py-0.5 rounded border text-[9px] font-mono ${getSlaBadgeClass(item.priority, item.elapsed_minutes)}`}>
                          {formatElapsed(item.elapsed_minutes)}
                        </span>
                      </div>
                    </Card>
                  ))
                )}
              </div>
            </div>

            {/* Column 2: Assigned */}
            <div className="flex flex-col rounded-lg border bg-muted/20 p-3 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b">
                <span className="font-semibold text-xs uppercase tracking-wide text-indigo-600 dark:text-indigo-400 flex items-center gap-1.5">
                  <UserCheck className="h-3.5 w-3.5" /> Assigned
                </span>
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                  {work_board.assigned.length}
                </Badge>
              </div>

              <div className="space-y-2.5 min-h-[350px]">
                {work_board.assigned.length === 0 ? (
                  <div className="text-center py-8 text-xs text-muted-foreground">No assigned items</div>
                ) : (
                  work_board.assigned.map(item => (
                    <Card key={item.id} className="p-3 hover:shadow-sm border-l-4 border-l-indigo-500 space-y-2">
                      <div className="flex items-center justify-between gap-1">
                        <Link
                          href={`/incidents/${item.incident_number}`}
                          className="font-mono text-xs font-semibold hover:underline text-indigo-600 dark:text-indigo-400 flex items-center gap-1"
                        >
                          {item.incident_number}
                          <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                        </Link>
                        <Badge variant="outline" className="text-[9px] px-1 py-0 uppercase">
                          {item.priority}
                        </Badge>
                      </div>

                      <p className="text-xs font-medium text-foreground line-clamp-2 leading-snug">
                        {item.short_description}
                      </p>

                      <div className="flex items-center justify-between pt-1 border-t text-[10px]">
                        <span className="text-muted-foreground font-medium truncate max-w-[100px]">
                          {item.assigned_to || 'Assigned'}
                        </span>
                        <span className={`px-1.5 py-0.5 rounded border text-[9px] font-mono ${getSlaBadgeClass(item.priority, item.elapsed_minutes)}`}>
                          {formatElapsed(item.elapsed_minutes)}
                        </span>
                      </div>
                    </Card>
                  ))
                )}
              </div>
            </div>

            {/* Column 3: In Progress */}
            <div className="flex flex-col rounded-lg border bg-muted/20 p-3 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b">
                <span className="font-semibold text-xs uppercase tracking-wide text-blue-600 dark:text-blue-400 flex items-center gap-1.5">
                  <PlayCircle className="h-3.5 w-3.5" /> In Progress
                </span>
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                  {work_board.in_progress.length}
                </Badge>
              </div>

              <div className="space-y-2.5 min-h-[350px]">
                {work_board.in_progress.length === 0 ? (
                  <div className="text-center py-8 text-xs text-muted-foreground">No active items</div>
                ) : (
                  work_board.in_progress.map(item => (
                    <Card key={item.id} className="p-3 hover:shadow-sm border-l-4 border-l-blue-500 space-y-2">
                      <div className="flex items-center justify-between gap-1">
                        <Link
                          href={`/incidents/${item.incident_number}`}
                          className="font-mono text-xs font-semibold hover:underline text-indigo-600 dark:text-indigo-400 flex items-center gap-1"
                        >
                          {item.incident_number}
                          <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                        </Link>
                        <Badge variant="outline" className="text-[9px] px-1 py-0 uppercase">
                          {item.priority}
                        </Badge>
                      </div>

                      <p className="text-xs font-medium text-foreground line-clamp-2 leading-snug">
                        {item.short_description}
                      </p>

                      <div className="flex items-center justify-between pt-1 border-t text-[10px]">
                        <span className="text-muted-foreground font-medium truncate max-w-[100px]">
                          {item.assigned_to || 'Assigned'}
                        </span>
                        <span className={`px-1.5 py-0.5 rounded border text-[9px] font-mono ${getSlaBadgeClass(item.priority, item.elapsed_minutes)}`}>
                          {formatElapsed(item.elapsed_minutes)}
                        </span>
                      </div>
                    </Card>
                  ))
                )}
              </div>
            </div>

            {/* Column 4: Blocked / Pending */}
            <div className="flex flex-col rounded-lg border bg-muted/20 p-3 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b">
                <span className="font-semibold text-xs uppercase tracking-wide text-amber-600 dark:text-amber-400 flex items-center gap-1.5">
                  <AlertTriangle className="h-3.5 w-3.5" /> Blocked / Hold
                </span>
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                  {work_board.blocked.length}
                </Badge>
              </div>

              <div className="space-y-2.5 min-h-[350px]">
                {work_board.blocked.length === 0 ? (
                  <div className="text-center py-8 text-xs text-muted-foreground">No blocked items</div>
                ) : (
                  work_board.blocked.map(item => (
                    <Card key={item.id} className="p-3 hover:shadow-sm border-l-4 border-l-amber-500 space-y-2">
                      <div className="flex items-center justify-between gap-1">
                        <Link
                          href={`/incidents/${item.incident_number}`}
                          className="font-mono text-xs font-semibold hover:underline text-indigo-600 dark:text-indigo-400 flex items-center gap-1"
                        >
                          {item.incident_number}
                          <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                        </Link>
                        <Badge variant="outline" className="text-[9px] px-1 py-0 uppercase">
                          {item.priority}
                        </Badge>
                      </div>

                      <p className="text-xs font-medium text-foreground line-clamp-2 leading-snug">
                        {item.short_description}
                      </p>

                      <div className="flex items-center justify-between pt-1 border-t text-[10px]">
                        <span className="text-muted-foreground font-medium truncate max-w-[100px]">
                          {item.assigned_to || 'Assigned'}
                        </span>
                        <span className="px-1.5 py-0.5 rounded border text-[9px] font-mono bg-amber-500/10 text-amber-600">
                          {formatElapsed(item.elapsed_minutes)}
                        </span>
                      </div>
                    </Card>
                  ))
                )}
              </div>
            </div>

            {/* Column 5: Completed Today */}
            <div className="flex flex-col rounded-lg border bg-muted/20 p-3 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b">
                <span className="font-semibold text-xs uppercase tracking-wide text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
                  <CheckSquare className="h-3.5 w-3.5" /> Resolved Today
                </span>
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                  {work_board.completed_today.length}
                </Badge>
              </div>

              <div className="space-y-2.5 min-h-[350px]">
                {work_board.completed_today.length === 0 ? (
                  <div className="text-center py-8 text-xs text-muted-foreground">None resolved yet today</div>
                ) : (
                  work_board.completed_today.map(item => (
                    <Card key={item.id} className="p-3 hover:shadow-sm border-l-4 border-l-emerald-500 space-y-2 opacity-85">
                      <div className="flex items-center justify-between gap-1">
                        <Link
                          href={`/incidents/${item.incident_number}`}
                          className="font-mono text-xs font-semibold hover:underline text-indigo-600 dark:text-indigo-400 flex items-center gap-1"
                        >
                          {item.incident_number}
                          <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                        </Link>
                        <Badge variant="outline" className="text-[9px] px-1 py-0 uppercase">
                          {item.priority}
                        </Badge>
                      </div>

                      <p className="text-xs font-medium text-foreground line-clamp-2 leading-snug">
                        {item.short_description}
                      </p>

                      <div className="flex items-center justify-between pt-1 border-t text-[10px]">
                        <span className="text-muted-foreground font-medium truncate max-w-[100px]">
                          {item.assigned_to || 'Resolved'}
                        </span>
                        <Badge variant="outline" className="text-[9px] text-emerald-600 border-emerald-200">
                          RESOLVED
                        </Badge>
                      </div>
                    </Card>
                  ))
                )}
              </div>
            </div>
          </div>
        </TabsContent>

        {/* =====================================================================
            TAB 3: LIVE TIMELINE FEED
            ===================================================================== */}
        <TabsContent value="timeline" className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <h2 className="text-base font-semibold">Group Operational Timeline</h2>

            <div className="flex items-center gap-2">
              <Filter className="h-3.5 w-3.5 text-muted-foreground" />
              <select
                value={timelineFilter}
                onChange={e => setTimelineFilter(e.target.value)}
                className="text-xs rounded border bg-background px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="ALL">All Event Types</option>
                <option value="INCIDENTS">Incidents</option>
                <option value="ASSIGNMENTS">Assignments</option>
                <option value="PRESENCE">Presence & Shift</option>
                <option value="NOTICES">Notices</option>
                <option value="SYSTEM">System & Pilot</option>
              </select>
            </div>
          </div>

          <Card>
            <CardContent className="p-4">
              {isTimelineLoading ? (
                <div className="space-y-4 py-4">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-14 w-full" />
                  ))}
                </div>
              ) : timeline.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground text-sm">
                  No activity events recorded for this group yet.
                </div>
              ) : (
                <div className="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-muted">
                  {timeline.map(event => (
                    <div key={event.id} className="relative group">
                      {/* Timeline dot */}
                      <div className="absolute -left-6 top-1 h-3.5 w-3.5 rounded-full border-2 border-background bg-indigo-600 group-hover:scale-110 transition-transform" />

                      <div className="bg-muted/30 rounded-lg p-3 border hover:bg-muted/50 transition-colors">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                            <Badge variant="outline" className="text-[9px] px-1.5 py-0 uppercase">
                              {event.event_type}
                            </Badge>
                            {event.title}
                          </span>
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {new Date(event.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                          </span>
                        </div>

                        <p className="text-xs text-muted-foreground">
                          {event.description}
                        </p>

                        {event.actor_name && (
                          <div className="mt-1.5 text-[10px] text-slate-500 flex items-center gap-1">
                            <span>Actor:</span>
                            <span className="font-medium text-slate-700 dark:text-slate-300">{event.actor_name}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* =====================================================================
            TAB 4: COLLABORATION & CHAT
            ===================================================================== */}
        <TabsContent value="chat" className="space-y-4">
          <Card className="overflow-hidden border">
            <div className="grid grid-cols-1 md:grid-cols-3 min-h-[550px]">
              {/* Left Column: Channels & Search */}
              <div className="border-r p-3 space-y-3 bg-muted/20">
                <form onSubmit={handleChatSearch} className="relative">
                  <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder="Search group messages..."
                    value={chatSearchQuery}
                    onChange={e => setChatSearchQuery(e.target.value)}
                    className="text-xs pl-8 h-8"
                  />
                </form>

                {searchResults ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs font-semibold px-1">
                      <span>Search Results ({searchResults.length})</span>
                      <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1" onClick={() => setSearchResults(null)}>
                        Clear
                      </Button>
                    </div>
                    <div className="space-y-1.5 max-h-[450px] overflow-y-auto">
                      {searchResults.length === 0 ? (
                        <div className="text-xs text-muted-foreground p-2 text-center">No matching messages found</div>
                      ) : (
                        searchResults.map(msg => (
                          <div key={msg.id} className="p-2 rounded bg-background border text-xs space-y-1">
                            <div className="flex justify-between font-medium text-[11px]">
                              <span>{msg.sender_name}</span>
                              <span className="text-muted-foreground text-[10px]">
                                {new Date(msg.created_at).toLocaleDateString()}
                              </span>
                            </div>
                            <p className="text-muted-foreground text-[11px] line-clamp-2">{msg.content}</p>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <div className="text-[11px] font-semibold text-muted-foreground uppercase px-2 mb-1.5">
                        Group Channels
                      </div>
                      <div className="space-y-1">
                        {conversations
                          .filter(c => c.type === 'TEAM')
                          .map(conv => (
                            <button
                              key={conv.id}
                              onClick={() => setSelectedConvId(conv.id)}
                              className={`w-full text-left px-2.5 py-2 rounded-md text-xs font-medium flex items-center justify-between transition-colors ${
                                selectedConvId === conv.id
                                  ? 'bg-indigo-600 text-white'
                                  : 'hover:bg-muted text-foreground'
                              }`}
                            >
                              <span className="flex items-center gap-1.5 truncate">
                                <Hash className="h-3.5 w-3.5 opacity-70" />
                                {conv.name || `${header.name} Channel`}
                              </span>
                              <Badge variant="secondary" className="text-[9px] px-1 py-0">
                                {conv.member_count}
                              </Badge>
                            </button>
                          ))}
                      </div>
                    </div>

                    <div>
                      <div className="text-[11px] font-semibold text-muted-foreground uppercase px-2 mb-1.5">
                        Incident Threads
                      </div>
                      <div className="space-y-1">
                        {conversations.filter(c => c.type === 'INCIDENT').length === 0 ? (
                          <div className="text-xs text-muted-foreground px-2 italic">No active incident threads</div>
                        ) : (
                          conversations
                            .filter(c => c.type === 'INCIDENT')
                            .map(conv => (
                              <button
                                key={conv.id}
                                onClick={() => setSelectedConvId(conv.id)}
                                className={`w-full text-left px-2.5 py-2 rounded-md text-xs font-medium flex items-center justify-between transition-colors ${
                                  selectedConvId === conv.id
                                    ? 'bg-indigo-600 text-white'
                                    : 'hover:bg-muted text-foreground'
                                }`}
                              >
                                <span className="truncate flex items-center gap-1.5 font-mono">
                                  #{conv.incident_number}
                                </span>
                              </button>
                            ))
                        )}
                      </div>
                    </div>

                    <div>
                      <div className="text-[11px] font-semibold text-muted-foreground uppercase px-2 mb-1.5">
                        Direct Messages
                      </div>
                      <div className="space-y-1">
                        {conversations.filter(c => c.type === 'DIRECT').length === 0 ? (
                          <div className="text-xs text-muted-foreground px-2 italic">No direct messages yet</div>
                        ) : (
                          conversations
                            .filter(c => c.type === 'DIRECT')
                            .map(conv => (
                              <button
                                key={conv.id}
                                onClick={() => setSelectedConvId(conv.id)}
                                className={`w-full text-left px-2.5 py-2 rounded-md text-xs font-medium flex items-center justify-between transition-colors ${
                                  selectedConvId === conv.id
                                    ? 'bg-indigo-600 text-white'
                                    : 'hover:bg-muted text-foreground'
                                }`}
                              >
                                <span className="truncate flex items-center gap-1.5">
                                  <Users className="h-3.5 w-3.5 opacity-70" />
                                  {conv.name || 'Direct Conversation'}
                                </span>
                              </button>
                            ))
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Right Column: Chat History & Input */}
              <div className="col-span-2 flex flex-col justify-between p-4">
                {/* Chat Header */}
                <div className="pb-3 border-b flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <MessageSquare className="h-4 w-4 text-indigo-600" />
                    <span className="font-semibold text-sm">
                      {conversations.find(c => c.id === selectedConvId)?.name || `${header.name} Operational Room`}
                    </span>
                    <Badge variant="outline" className="text-[10px]">
                      Audited by Admin
                    </Badge>
                  </div>
                  <span className="text-[11px] text-muted-foreground">
                    Use #INC-XXXXXXXX to reference incidents
                  </span>
                </div>

                {/* Messages List */}
                <div className="flex-1 py-4 space-y-3 overflow-y-auto max-h-[400px]">
                  {messages.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-muted-foreground text-xs py-12">
                      <MessageSquare className="h-8 w-8 mb-2 opacity-30" />
                      No messages yet in this discussion. Start the collaboration.
                    </div>
                  ) : (
                    messages.map(msg => {
                      const isMe = msg.sender_id === user?.id;
                      return (
                        <div key={msg.id} className={`flex flex-col ${isMe ? 'items-end' : 'items-start'}`}>
                          <div className="flex items-center gap-1.5 mb-0.5 text-[11px]">
                            <span className="font-semibold text-foreground">{msg.sender_name}</span>
                            <Badge variant="secondary" className="text-[9px] px-1 py-0 uppercase">
                              {msg.sender_role}
                            </Badge>
                            <span className="text-muted-foreground text-[10px]">
                              {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>

                          <div
                            className={`rounded-lg px-3 py-2 text-xs max-w-[80%] leading-relaxed ${
                              isMe
                                ? 'bg-indigo-600 text-white rounded-tr-none'
                                : 'bg-muted/70 text-foreground border rounded-tl-none'
                            }`}
                          >
                            {/* Render text with clickable #INC tags */}
                            {msg.content.split(/(INC-[A-Z0-9]+|INC\d+)/g).map((part, idx) => {
                              if (part.match(/^(INC-[A-Z0-9]+|INC\d+)$/)) {
                                return (
                                  <Link
                                    key={idx}
                                    href={`/incidents/${part}`}
                                    className={`font-mono font-semibold underline ${
                                      isMe ? 'text-amber-200' : 'text-indigo-600 dark:text-indigo-400'
                                    }`}
                                  >
                                    #{part}
                                  </Link>
                                );
                              }
                              return <span key={idx}>{part}</span>;
                            })}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Message Input Box */}
                <div className="pt-3 border-t">
                  <div className="flex items-center gap-2">
                    <Input
                      placeholder="Type a team update or instruction... (e.g. Please check #INC-7K4M92XQ)"
                      value={newMessageText}
                      onChange={e => setNewMessageText(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleSendMessage();
                        }
                      }}
                      className="text-xs"
                    />
                    <Button
                      size="sm"
                      onClick={handleSendMessage}
                      disabled={isSendingMessage || !newMessageText.trim() || !selectedConvId}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white px-3"
                    >
                      <Send className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        </TabsContent>

        {/* =====================================================================
            TAB 5: GROUP ANALYTICS
            ===================================================================== */}
        <TabsContent value="analytics" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Group Operational Metrics</h2>
            <div className="flex items-center gap-1.5 bg-muted p-1 rounded-lg">
              {(['today', '7d', '30d'] as const).map(p => (
                <button
                  key={p}
                  onClick={() => setAnalyticsPeriod(p)}
                  className={`text-xs px-2.5 py-1 rounded font-medium transition-colors ${
                    analyticsPeriod === p
                      ? 'bg-background shadow-sm text-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {p === 'today' ? 'Today' : p === '7d' ? '7 Days' : '30 Days'}
                </button>
              ))}
            </div>
          </div>

          {isAnalyticsLoading || !analytics ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
                <Card>
                  <CardContent className="p-4">
                    <div className="text-xs text-muted-foreground">Total Handled</div>
                    <div className="text-2xl font-bold mt-1">{analytics.total_incidents}</div>
                    <div className="text-[11px] text-muted-foreground">In selected period</div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-4">
                    <div className="text-xs text-muted-foreground">Resolved Successfully</div>
                    <div className="text-2xl font-bold text-emerald-600 mt-1">{analytics.resolved_count}</div>
                    <div className="text-[11px] text-muted-foreground">Closed out items</div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-4">
                    <div className="text-xs text-muted-foreground">Avg Resolution Time</div>
                    <div className="text-2xl font-bold text-indigo-600 mt-1">
                      {analytics.avg_resolution_minutes > 0 ? `${analytics.avg_resolution_minutes.toFixed(1)}m` : 'N/A'}
                    </div>
                    <div className="text-[11px] text-muted-foreground">From assign to complete</div>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-4">
                    <div className="text-xs text-muted-foreground">Auto-Assign Rate</div>
                    <div className="text-2xl font-bold text-blue-600 mt-1">
                      {analytics.auto_assignment_rate_pct.toFixed(0)}%
                    </div>
                    <div className="text-[11px] text-muted-foreground">Current shift engine</div>
                  </CardContent>
                </Card>
              </div>

              {/* Workload Distribution Table */}
              <Card>
                <CardHeader className="p-4 pb-2">
                  <CardTitle className="text-sm font-semibold">Engineer Workload Distribution</CardTitle>
                  <CardDescription className="text-xs">
                    Incidents assigned and completed by member during {analyticsPeriod}
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-4 pt-2">
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead>
                        <tr className="border-b text-muted-foreground">
                          <th className="py-2 font-medium">Engineer</th>
                          <th className="py-2 font-medium text-center">Assigned</th>
                          <th className="py-2 font-medium text-center">Completed</th>
                          <th className="py-2 font-medium text-right">Completion Rate</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {analytics.workload_distribution.map(item => {
                          const rate = item.assigned_count > 0 ? (item.completed_count / item.assigned_count) * 100 : 0;
                          return (
                            <tr key={item.employee_id} className="hover:bg-muted/30">
                              <td className="py-2.5 font-medium flex items-center gap-2">
                                <span className="h-6 w-6 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center font-bold text-[10px]">
                                  {item.employee_name[0]}
                                </span>
                                {item.employee_name}
                              </td>
                              <td className="py-2.5 text-center font-mono">{item.assigned_count}</td>
                              <td className="py-2.5 text-center font-mono text-emerald-600 font-semibold">
                                {item.completed_count}
                              </td>
                              <td className="py-2.5 text-right font-mono">
                                {item.assigned_count > 0 ? `${rate.toFixed(0)}%` : '—'}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* =======================================================================
          SLIDE-OVER EMPLOYEE DETAILS DRAWER (Sheet)
          ======================================================================= */}
      <Sheet open={!!selectedEmployeeId} onOpenChange={open => !open && setSelectedEmployeeId(null)}>
        <SheetContent className="sm:max-w-md overflow-y-auto">
          <SheetHeader className="pb-4 border-b">
            <SheetTitle className="text-lg">Employee Operational Profile</SheetTitle>
            <SheetDescription className="text-xs">
              Complete shift, presence, and workload details
            </SheetDescription>
          </SheetHeader>

          {isDrawerLoading || !employeeDrawerData ? (
            <div className="space-y-4 py-6">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-40 w-full" />
            </div>
          ) : (
            <div className="py-5 space-y-5">
              {/* Profile Card */}
              <div className="flex items-center gap-3">
                <Avatar className="h-14 w-14 border-2 border-indigo-200">
                  <AvatarFallback className="bg-indigo-100 text-indigo-700 text-base font-bold">
                    {employeeDrawerData.full_name
                      .split(' ')
                      .map((n: string) => n[0])
                      .slice(0, 2)
                      .join('')}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <h3 className="font-bold text-base leading-tight">{employeeDrawerData.full_name}</h3>
                  <p className="text-xs text-muted-foreground">{employeeDrawerData.email}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant="outline" className="text-[10px]">
                      {employeeDrawerData.employee_code || 'ID: ' + employeeDrawerData.id.slice(0, 8)}
                    </Badge>
                    <Badge
                      variant="outline"
                      className={`text-[10px] ${
                        employeeDrawerData.availability_status === 'AVAILABLE'
                          ? 'bg-emerald-500/10 text-emerald-600'
                          : 'bg-amber-500/10 text-amber-600'
                      }`}
                    >
                      {employeeDrawerData.availability_status}
                    </Badge>
                  </div>
                </div>
              </div>

              {/* Status Section */}
              <Card className="bg-muted/30">
                <CardContent className="p-3.5 space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Team / Group:</span>
                    <span className="font-medium">{employeeDrawerData.team_name || header.name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Presence Status:</span>
                    <span className="font-medium flex items-center gap-1">
                      {employeeDrawerData.is_present ? (
                        <>
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /> Present (Checked In)
                        </>
                      ) : (
                        <>
                          <XCircle className="h-3.5 w-3.5 text-rose-500" /> Absent (Checked Out)
                        </>
                      )}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Active Shift:</span>
                    <span className="font-medium">{employeeDrawerData.current_shift_name || 'None Scheduled'}</span>
                  </div>
                </CardContent>
              </Card>

              {/* Skills */}
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                  Skills & Proficiencies
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {employeeDrawerData.skills?.length > 0 ? (
                    employeeDrawerData.skills.map((s: any) => (
                      <Badge key={s.id} variant="secondary" className="text-xs">
                        {s.name} (L{s.proficiency_level || 1})
                      </Badge>
                    ))
                  ) : (
                    <span className="text-xs text-muted-foreground italic">Standard operations skillset</span>
                  )}
                </div>
              </div>

              {/* Active Assignments */}
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                  Active Incidents ({employeeDrawerData.active_incidents?.length || 0})
                </h4>
                <div className="space-y-2">
                  {employeeDrawerData.active_incidents?.length > 0 ? (
                    employeeDrawerData.active_incidents.map((inc: any) => (
                      <div key={inc.id} className="p-2.5 rounded border bg-card text-xs space-y-1">
                        <div className="flex justify-between font-semibold">
                          <Link href={`/incidents/${inc.incident_number}`} className="font-mono text-indigo-600 hover:underline">
                            {inc.incident_number}
                          </Link>
                          <Badge variant="outline" className="text-[9px] uppercase">
                            {inc.priority}
                          </Badge>
                        </div>
                        <p className="text-muted-foreground line-clamp-1">{inc.short_description}</p>
                      </div>
                    ))
                  ) : (
                    <div className="text-xs text-muted-foreground italic p-2 border rounded text-center">
                      No active assignments
                    </div>
                  )}
                </div>
              </div>

              <div className="pt-2">
                <Button
                  className="w-full text-xs bg-indigo-600 hover:bg-indigo-700 text-white"
                  onClick={() => {
                    setSelectedEmployeeId(null);
                    handleStartDirectChat(employeeDrawerData.user_id);
                  }}
                >
                  <MessageSquare className="mr-1.5 h-3.5 w-3.5" /> Start Direct Chat with {employeeDrawerData.full_name}
                </Button>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* =======================================================================
          SEND GROUP NOTICE & WORK ITEM DIALOG
          ======================================================================= */}
      <Dialog open={isNoticeOpen} onOpenChange={setIsNoticeOpen}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Send className="h-4 w-4 text-indigo-600" /> Send Incident Notice & Assign to {header.name}
            </DialogTitle>
            <DialogDescription className="text-xs">
              Sends the COMPLETE INCIDENT NOTICE to all authorized members of {header.name} in realtime.
              Incident ID is generated automatically server-side.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2 text-xs">
            <div className="rounded-lg bg-indigo-50 dark:bg-indigo-950/40 p-3 border border-indigo-200 dark:border-indigo-900/50 space-y-1">
              <div className="font-semibold text-indigo-900 dark:text-indigo-300 flex items-center justify-between">
                <span>Enterprise Realtime Delivery</span>
                <span className="font-mono text-[11px] bg-indigo-200/60 dark:bg-indigo-900/60 px-2 py-0.5 rounded text-indigo-950 dark:text-indigo-200">
                  Target: {header.name}
                </span>
              </div>
              <p className="text-indigo-700 dark:text-indigo-400 text-[11px] leading-relaxed">
                Only members of <strong>{header.name}</strong> will receive this notice. An unpredictable, database-unique
                Incident ID (e.g. <span className="font-mono font-bold">INC-7K4M92XQ</span>) is generated automatically.
              </p>
            </div>

            {/* Core Issue Fields */}
            <div>
              <label className="font-medium mb-1 block text-zinc-900 dark:text-zinc-100">
                Issue / Short Description *
              </label>
              <Input
                placeholder="e.g. Database connection failure"
                value={noticeTitle}
                onChange={e => setNoticeTitle(e.target.value)}
                className="text-xs"
              />
            </div>

            <div>
              <label className="font-medium mb-1 block text-zinc-900 dark:text-zinc-100">
                Description / Problem Details *
              </label>
              <textarea
                placeholder="Multiple application servers are unable to establish a database connection..."
                value={noticeMessage}
                onChange={e => setNoticeMessage(e.target.value)}
                className="w-full h-20 rounded-md border border-input bg-background p-2.5 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {/* Priority, Impact, Urgency */}
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="font-medium mb-1 block">Priority</label>
                <select
                  value={noticePriority}
                  onChange={e => {
                    const p = e.target.value;
                    setNoticePriority(p);
                    if (p === 'P1' || p === 'P2') {
                      setNoticeImpact('High');
                      setNoticeUrgency('High');
                    } else if (p === 'P3') {
                      setNoticeImpact('Medium');
                      setNoticeUrgency('Medium');
                    } else {
                      setNoticeImpact('Low');
                      setNoticeUrgency('Low');
                    }
                  }}
                  className="w-full rounded border bg-background px-2.5 py-1.5 text-xs font-semibold"
                >
                  <option value="P1">P1 - Critical</option>
                  <option value="P2">P2 - High</option>
                  <option value="P3">P3 - Medium</option>
                  <option value="P4">P4 - Low</option>
                </select>
              </div>

              <div>
                <label className="font-medium mb-1 block">Impact</label>
                <select
                  value={noticeImpact}
                  onChange={e => setNoticeImpact(e.target.value)}
                  className="w-full rounded border bg-background px-2.5 py-1.5 text-xs"
                >
                  <option value="High">High</option>
                  <option value="Medium">Medium</option>
                  <option value="Low">Low</option>
                </select>
              </div>

              <div>
                <label className="font-medium mb-1 block">Urgency</label>
                <select
                  value={noticeUrgency}
                  onChange={e => setNoticeUrgency(e.target.value)}
                  className="w-full rounded border bg-background px-2.5 py-1.5 text-xs"
                >
                  <option value="High">High</option>
                  <option value="Medium">Medium</option>
                  <option value="Low">Low</option>
                </select>
              </div>
            </div>

            {/* Category & Configuration Item */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="font-medium mb-1 block">Category</label>
                <Input
                  placeholder="e.g. Database"
                  value={noticeCategory || (header.work_domain || header.name.split(' ')[0])}
                  onChange={e => setNoticeCategory(e.target.value)}
                  className="text-xs"
                />
              </div>

              <div>
                <label className="font-medium mb-1 block">Configuration Item</label>
                <Input
                  placeholder="e.g. Production Database"
                  value={noticeCi || `Production ${header.name}`}
                  onChange={e => setNoticeCi(e.target.value)}
                  className="text-xs"
                />
              </div>
            </div>

            {/* Work Instructions */}
            <div>
              <label className="font-medium mb-1 block text-zinc-900 dark:text-zinc-100">
                Work Instructions
              </label>
              <Input
                placeholder="e.g. Investigate database connection pool exhaustion and check the database server logs."
                value={noticeWorkInstructions}
                onChange={e => setNoticeWorkInstructions(e.target.value)}
                className="text-xs"
              />
              <span className="text-[10px] text-muted-foreground">
                Assigned engineer will see this in their &quot;YOUR TASK&quot; panel. If left blank, the description is used.
              </span>
            </div>

            {/* Collapsible Advanced Attributes */}
            <div>
              <button
                type="button"
                onClick={() => setShowAdvancedNoticeFields(!showAdvancedNoticeFields)}
                className="text-xs text-indigo-600 dark:text-indigo-400 font-medium hover:underline flex items-center gap-1"
              >
                {showAdvancedNoticeFields ? 'Hide' : 'Show'} Additional Metadata (Caller, Location, Subcategory)
              </button>
              {showAdvancedNoticeFields && (
                <div className="grid grid-cols-3 gap-3 mt-2 p-2.5 bg-muted/40 rounded-md border">
                  <div>
                    <label className="font-medium mb-1 block text-[11px]">Caller</label>
                    <Input
                      placeholder="e.g. Operations Center"
                      value={noticeCaller}
                      onChange={e => setNoticeCaller(e.target.value)}
                      className="text-xs h-8"
                    />
                  </div>
                  <div>
                    <label className="font-medium mb-1 block text-[11px]">Location</label>
                    <Input
                      placeholder="e.g. Primary Cloud DC"
                      value={noticeLocation}
                      onChange={e => setNoticeLocation(e.target.value)}
                      className="text-xs h-8"
                    />
                  </div>
                  <div>
                    <label className="font-medium mb-1 block text-[11px]">Subcategory</label>
                    <Input
                      placeholder="e.g. Connection Pool"
                      value={noticeSubcategory}
                      onChange={e => setNoticeSubcategory(e.target.value)}
                      className="text-xs h-8"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Live Notice Preview */}
            <div className="rounded-md border bg-zinc-950 text-zinc-100 p-3 font-mono text-[11px] space-y-1 overflow-x-auto">
              <div className="text-amber-400 font-bold mb-1">🚨 LIVE NOTICE PREVIEW (Group receives immediately):</div>
              <div className="text-zinc-400">Incident ID: <span className="text-white font-bold">[Auto-generated INC-XXXXXXXX]</span></div>
              <div className="text-zinc-400">Issue: <span className="text-white">{noticeTitle || 'Not provided'}</span></div>
              <div className="text-zinc-400">Description: <span className="text-zinc-300">{noticeMessage || 'Not provided'}</span></div>
              <div className="text-zinc-400">Priority: <span className="text-amber-300 font-bold">{noticePriority}</span> | Impact: <span className="text-zinc-300">{noticeImpact}</span> | Urgency: <span className="text-zinc-300">{noticeUrgency}</span></div>
              <div className="text-zinc-400">Category: <span className="text-zinc-300">{noticeCategory || header.work_domain || 'Database'}</span> | Group: <span className="text-indigo-400 font-bold">{header.name}</span></div>
              <div className="text-zinc-400">Configuration Item: <span className="text-zinc-300">{noticeCi || `Production ${header.name}`}</span></div>
              <div className="text-zinc-400">Current Status: <span className="text-emerald-400 font-bold">NEW</span></div>
              <div className="text-zinc-400">Work Instructions: <span className="text-zinc-300">{noticeWorkInstructions || noticeMessage || 'Not provided'}</span></div>
              <div className="border-t border-zinc-800 pt-1 text-zinc-500">Assignment: ⏳ Assigning...</div>
            </div>

            <div className="flex items-center gap-2 pt-1">
              <input
                type="checkbox"
                id="autoAssignCheck"
                checked={autoAssign}
                onChange={e => setAutoAssign(e.target.checked)}
                className="rounded border-input text-indigo-600 focus:ring-indigo-500 h-4 w-4"
              />
              <label htmlFor="autoAssignCheck" className="text-xs font-medium cursor-pointer">
                Auto-assign work to eligible member on current shift
              </label>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setIsNoticeOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSendNotice}
              disabled={isSendingNotice || !noticeTitle.trim() || !noticeMessage.trim()}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium"
            >
              <Send className="mr-1.5 h-3.5 w-3.5" />
              {isSendingNotice ? 'Executing Pipeline...' : 'Send Notice'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* =======================================================================
          ASSIGNMENT RESULT DISPLAY MODAL (Complete 15 Fields + Realtime Events)
          ======================================================================= */}
      <Dialog open={!!assignmentResult} onOpenChange={open => !open && setAssignmentResult(null)}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              {assignmentResult?.assignment_status === 'ASSIGNED' ? (
                <>
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                  <span>Assigned to: {assignmentResult.assigned_employee_name}</span>
                </>
              ) : (
                <>
                  <AlertCircle className="h-5 w-5 text-amber-500" />
                  <span>Assignment Status: Assignment Pending</span>
                </>
              )}
            </DialogTitle>
            <DialogDescription className="text-xs">
              Complete assignment execution result and issue notice for {assignmentResult?.target_group || assignmentResult?.assignment_group}
            </DialogDescription>
          </DialogHeader>

          {assignmentResult && (
            <div className="space-y-4 py-2 text-xs">
              {/* Status Banner */}
              {assignmentResult.assignment_status === 'ASSIGNED' ? (
                <div className="rounded-lg bg-emerald-50 dark:bg-emerald-950/40 p-3 border border-emerald-200 dark:border-emerald-900/50">
                  <div className="font-bold text-emerald-800 dark:text-emerald-200 text-sm">
                    Assigned to: {assignmentResult.assigned_employee_name}
                  </div>
                  <div className="text-emerald-700 dark:text-emerald-300 text-[11px] mt-0.5">
                    Engineer is verified on active shift, present, and available. Realtime assignment notification dispatched.
                  </div>
                </div>
              ) : (
                <div className="rounded-lg bg-amber-50 dark:bg-amber-950/40 p-3 border border-amber-200 dark:border-amber-900/50">
                  <div className="font-bold text-amber-800 dark:text-amber-200 text-sm">
                    Assignment Status: Assignment Pending
                  </div>
                  <div className="text-amber-700 dark:text-amber-300 text-[11px] mt-0.5">
                    Reason: <span className="font-semibold">{assignmentResult.pending_reason || assignmentResult.unassigned_reason || 'Assignment pending initialization.'}</span>
                  </div>
                </div>
              )}

              {/* Realtime Event Stream Timeline */}
              {assignmentResult.timeline_events && assignmentResult.timeline_events.length > 0 && (
                <div className="rounded-lg border bg-zinc-50 dark:bg-zinc-900/60 p-3 space-y-1.5">
                  <div className="font-semibold text-zinc-900 dark:text-zinc-100 text-[11px] uppercase tracking-wider">
                    Realtime Event Sequence
                  </div>
                  <div className="space-y-1 font-mono text-[11px]">
                    {assignmentResult.timeline_events.map((evt, idx) => (
                      <div key={idx} className="flex items-start gap-2 text-zinc-700 dark:text-zinc-300">
                        <span className="text-emerald-600 dark:text-emerald-400 font-bold">✓</span>
                        <span>{evt}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Complete Detail Grid */}
              <div className="rounded-lg border bg-card p-4 space-y-2.5">
                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">1. Incident ID:</span>
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400 text-sm">
                      {assignmentResult.incident_number}
                    </span>
                    <button
                      onClick={() => copyIncidentId(assignmentResult.incident_number)}
                      className="p-1 hover:bg-muted rounded text-muted-foreground"
                      title="Copy Incident ID"
                    >
                      {copiedId ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">2. Issue / Short Description:</span>
                  <span className="font-semibold text-right max-w-[320px] truncate">
                    {assignmentResult.short_description}
                  </span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">3. Full Description:</span>
                  <span className="text-right max-w-[320px] truncate text-muted-foreground">
                    {assignmentResult.description || 'Not provided'}
                  </span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">4. Priority / Impact / Urgency:</span>
                  <div className="flex items-center gap-1.5 font-medium">
                    <Badge variant="outline" className="font-bold">{assignmentResult.priority || 'P3'}</Badge>
                    <span className="text-muted-foreground">Impact: {assignmentResult.impact || 'Not provided'}</span>
                    <span className="text-muted-foreground">Urgency: {assignmentResult.urgency || 'Not provided'}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">5. Target Group:</span>
                  <span className="font-semibold">{assignmentResult.target_group || assignmentResult.assignment_group}</span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">6. Configuration Item:</span>
                  <span className="font-medium">{assignmentResult.configuration_item || 'Not provided'}</span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">7. Assignment Status:</span>
                  <Badge
                    variant={assignmentResult.assignment_status === 'ASSIGNED' ? 'default' : 'secondary'}
                    className="text-[10px] uppercase font-bold"
                  >
                    {assignmentResult.assignment_status === 'ASSIGNED' ? 'ASSIGNED' : 'Assignment Pending'}
                  </Badge>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">8. Assigned Employee:</span>
                  <span className="font-bold">
                    {assignmentResult.assigned_employee_name || 'Assignment Pending'}
                  </span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">9. Employee ID:</span>
                  <span className="font-mono text-muted-foreground">
                    {assignmentResult.employee_id || 'Not provided'}
                  </span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">10. Assignment Time:</span>
                  <span className="font-mono text-muted-foreground">
                    {assignmentResult.assignment_time ? new Date(assignmentResult.assignment_time).toLocaleString() : 'Not provided'}
                  </span>
                </div>

                <div className="flex items-center justify-between pb-2 border-b">
                  <span className="text-muted-foreground font-medium">11. Employee Presence / Status:</span>
                  <span className="font-medium">
                    {assignmentResult.employee_presence || 'Not provided'}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground font-medium">12. Current Task & Status:</span>
                  <span className="font-medium text-right truncate max-w-[280px]">
                    {assignmentResult.current_task} ({assignmentResult.task_status || 'NEW'})
                  </span>
                </div>
              </div>

              {/* Full Notice Content with Copy Button */}
              {assignmentResult.notice_body && (
                <div className="rounded-lg border bg-zinc-950 text-zinc-100 p-3 space-y-2">
                  <div className="flex items-center justify-between pb-1 border-b border-zinc-800">
                    <span className="text-[11px] font-bold text-amber-400">Full Group Notice Delivered:</span>
                    <button
                      onClick={() => {
                        if (assignmentResult.notice_body) {
                          navigator.clipboard.writeText(assignmentResult.notice_body);
                          setCopiedNotice(true);
                          setTimeout(() => setCopiedNotice(false), 2000);
                          toast.success('Full notice copied to clipboard');
                        }
                      }}
                      className="text-[10px] text-zinc-400 hover:text-white flex items-center gap-1 bg-zinc-900 px-2 py-0.5 rounded"
                    >
                      {copiedNotice ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                      {copiedNotice ? 'Copied' : 'Copy Notice'}
                    </button>
                  </div>
                  <pre className="font-mono text-[11px] whitespace-pre-wrap text-zinc-300 leading-relaxed max-h-40 overflow-y-auto">
                    {assignmentResult.notice_body}
                  </pre>
                </div>
              )}
            </div>
          )}

          <DialogFooter className="flex items-center justify-between sm:justify-between w-full">
            <Button variant="outline" size="sm" onClick={() => setAssignmentResult(null)}>
              Close
            </Button>

            {assignmentResult?.incident_number && (
              <Button
                size="sm"
                className="bg-indigo-600 hover:bg-indigo-700 text-white"
                onClick={() => {
                  setAssignmentResult(null);
                  router.push(`/incidents/${assignmentResult.incident_number}`);
                }}
              >
                <ExternalLink className="mr-1.5 h-3.5 w-3.5" /> View Assignment
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
