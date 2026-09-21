'use client';

import * as React from 'react';
import { useAuth } from '@/hooks/use-auth';
import { apiClient } from '@/lib/api-client';
import { wsClient } from '@/lib/websocket';
import { toast } from 'sonner';
import Link from 'next/link';
import {
  User, Mail, Phone, Clock, Shield, Award, Users2,
  Calendar, CheckCircle2, AlertTriangle, Upload, Camera,
  Sparkles, Save, MessageSquare, ExternalLink, RefreshCw
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Skeleton } from '@/components/ui/skeleton';

interface UserProfileData {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  role: string;
  avatar_url?: string;
  phone?: string;
  bio?: string;
  timezone?: string;
  notification_preferences?: string;
  chat_preferences?: string;
  team_id?: string;
  team_name?: string;
  employee_code?: string;
  is_group_leader: boolean;
  availability_status: string;
  is_present: boolean;
  skills: Array<{ id: string; name: string; description?: string; is_active: boolean }>;
  active_incident_count: number;
  shift?: {
    id: string;
    name: string;
    start_time: string;
    end_time: string;
    timezone: string;
    is_overnight: boolean;
  };
}

export default function EmployeeProfilePage() {
  const { user, refreshUser } = useAuth();
  const [profile, setProfile] = React.useState<UserProfileData | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isSaving, setIsSaving] = React.useState(false);
  const [isUploadingAvatar, setIsUploadingAvatar] = React.useState(false);

  // Form fields
  const [fullName, setFullName] = React.useState('');
  const [phone, setPhone] = React.useState('');
  const [bio, setBio] = React.useState('');
  const [timezone, setTimezone] = React.useState('Asia/Kolkata');
  const [availabilityStatus, setAvailabilityStatus] = React.useState('AVAILABLE');
  const [notificationPref, setNotificationPref] = React.useState('ALL');
  const [chatPref, setChatPref] = React.useState('ENTER_SEND');

  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const fetchProfile = React.useCallback(async () => {
    try {
      setIsLoading(true);
      const data = await apiClient.get<UserProfileData>('/api/me/profile');
      setProfile(data);
      setFullName(data.full_name || '');
      setPhone(data.phone || '');
      setBio(data.bio || '');
      setTimezone(data.timezone || 'Asia/Kolkata');
      setAvailabilityStatus(data.availability_status || 'AVAILABLE');
      setNotificationPref(data.notification_preferences || 'ALL');
      setChatPref(data.chat_preferences || 'ENTER_SEND');
    } catch (err: any) {
      toast.error('Failed to load profile: ' + (err.message || 'Unknown error'));
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  // Subscribe to realtime profile updates
  React.useEffect(() => {
    const unsub = wsClient.subscribe('PROFILE_UPDATED', (payload: any) => {
      if (payload.user_id === user?.id) {
        setProfile(prev => prev ? {
          ...prev,
          full_name: payload.full_name ?? prev.full_name,
          avatar_url: payload.avatar_url ?? prev.avatar_url,
          phone: payload.phone ?? prev.phone,
          bio: payload.bio ?? prev.bio,
          timezone: payload.timezone ?? prev.timezone,
          availability_status: payload.availability_status ?? prev.availability_status,
          is_present: payload.is_present ?? prev.is_present,
          is_group_leader: payload.is_group_leader ?? prev.is_group_leader,
        } : null);
      }
    });

    return () => unsub();
  }, [user?.id]);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsSaving(true);
      const updated = await apiClient.patch<UserProfileData>('/api/me/profile', {
        full_name: fullName,
        phone,
        bio,
        timezone,
        availability_status: availabilityStatus,
        notification_preferences: notificationPref,
        chat_preferences: chatPref,
      });

      setProfile(updated);
      toast.success('Profile updated successfully!');
      if (refreshUser) refreshUser();
    } catch (err: any) {
      toast.error('Failed to update profile: ' + (err.message || 'Network error'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      toast.error('Please select an image file (PNG, JPG, WEBP).');
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      toast.error('Avatar file must be less than 5MB.');
      return;
    }

    try {
      setIsUploadingAvatar(true);
      const formData = new FormData();
      formData.append('file', file);

      const res = await apiClient.uploadFile<{ status: string; avatar_url: string }>('/api/me/avatar', formData);
      if (res && res.avatar_url) {
        setProfile(prev => prev ? { ...prev, avatar_url: res.avatar_url } : null);
        toast.success('Avatar updated successfully!');
        if (refreshUser) refreshUser();
      }
    } catch (err: any) {
      toast.error('Failed to upload avatar: ' + (err.message || 'Error'));
    } finally {
      setIsUploadingAvatar(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleTogglePresence = async () => {
    if (!profile) return;
    try {
      const newStatus = profile.is_present ? 'OFFLINE' : 'AVAILABLE';
      await apiClient.patch('/api/me/availability', {
        status: newStatus,
        is_present: !profile.is_present
      });
      setProfile(prev => prev ? {
        ...prev,
        is_present: !prev.is_present,
        availability_status: newStatus
      } : null);
      toast.success(`Presence marked as ${!profile.is_present ? 'Present' : 'Offline'}`);
    } catch (err: any) {
      toast.error('Failed to toggle presence: ' + (err.message || 'Error'));
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto space-y-6 py-6 px-4">
        <Skeleton className="h-10 w-48" />
        <Card><CardContent className="h-64" /></Card>
      </div>
    );
  }

  const avatarSrc = profile?.avatar_url
    ? (profile.avatar_url.startsWith('http') ? profile.avatar_url : apiClient.getMediaUrl(profile.avatar_url))
    : undefined;

  return (
    <div className="max-w-4xl mx-auto space-y-6 py-6 px-4">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-950 dark:text-zinc-50 flex items-center gap-2">
            <User className="h-6 w-6 text-indigo-600" />
            Employee Profile
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Manage your personal profile, operational presence, contact details, and messaging preferences.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchProfile}
            className="text-xs flex items-center gap-1"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>

          <Button asChild size="sm" className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs">
            <Link href="/employee/team-chat" className="flex items-center gap-1.5">
              <MessageSquare className="h-3.5 w-3.5" />
              Team Chat
            </Link>
          </Button>
        </div>
      </div>

      {/* Profile Overview Card */}
      <Card className="border-zinc-200 dark:border-zinc-800 shadow-sm overflow-hidden">
        <div className="h-24 bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-500" />
        <CardContent className="relative pt-0 pb-6 px-6">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 -mt-12 mb-4">
            <div className="flex items-end gap-4">
              <div className="relative group">
                <Avatar className="h-24 w-24 border-4 border-white dark:border-zinc-900 shadow-md bg-zinc-100">
                  {avatarSrc && <AvatarImage src={avatarSrc} alt={profile?.full_name} />}
                  <AvatarFallback className="text-xl font-bold bg-indigo-100 text-indigo-700">
                    {profile?.full_name?.charAt(0) || 'U'}
                  </AvatarFallback>
                </Avatar>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploadingAvatar}
                  className="absolute inset-0 bg-black/40 text-white rounded-full opacity-0 group-hover:opacity-100 flex flex-col items-center justify-center transition-opacity cursor-pointer text-[10px] font-medium"
                  title="Upload profile avatar"
                >
                  <Camera className="h-5 w-5 mb-0.5" />
                  {isUploadingAvatar ? 'Saving...' : 'Change'}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  onChange={handleAvatarChange}
                  className="hidden"
                />
              </div>

              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold text-zinc-950 dark:text-zinc-50">
                    {profile?.full_name}
                  </h2>
                  {profile?.is_group_leader && (
                    <Badge className="bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200 border-amber-300 gap-1 text-[11px] font-bold">
                      <Shield className="h-3 w-3 text-amber-600" />
                      Group Leader
                    </Badge>
                  )}
                  <Badge variant="outline" className="text-[10px] font-semibold uppercase">
                    {profile?.role}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
                  <Mail className="h-3.5 w-3.5" />
                  {profile?.email}
                  {profile?.employee_code && (
                    <>
                      <span>•</span>
                      <span className="font-mono">{profile.employee_code}</span>
                    </>
                  )}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant={profile?.is_present ? 'default' : 'outline'}
                size="sm"
                onClick={handleTogglePresence}
                className={profile?.is_present ? 'bg-emerald-600 hover:bg-emerald-700 text-white text-xs' : 'text-xs'}
              >
                <span className={`w-2 h-2 rounded-full mr-2 ${profile?.is_present ? 'bg-white' : 'bg-zinc-400'}`} />
                {profile?.is_present ? 'Present (Active)' : 'Mark Present'}
              </Button>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4 border-t border-zinc-100 dark:border-zinc-800 text-xs">
            <div className="p-3 bg-zinc-50 dark:bg-zinc-900/60 rounded-lg">
              <div className="text-muted-foreground text-[11px]">Assigned Team</div>
              <div className="font-bold text-zinc-900 dark:text-zinc-100 mt-0.5 truncate">
                {profile?.team_name || 'Assignment Pending'}
              </div>
            </div>

            <div className="p-3 bg-zinc-50 dark:bg-zinc-900/60 rounded-lg">
              <div className="text-muted-foreground text-[11px]">Active Tickets</div>
              <div className="font-bold text-indigo-600 dark:text-indigo-400 mt-0.5 flex items-center gap-1">
                <span>{profile?.active_incident_count || 0} assigned</span>
              </div>
            </div>

            <div className="p-3 bg-zinc-50 dark:bg-zinc-900/60 rounded-lg">
              <div className="text-muted-foreground text-[11px]">Shift Status</div>
              <div className="font-bold text-zinc-900 dark:text-zinc-100 mt-0.5 truncate">
                {profile?.shift ? profile.shift.name : 'No Active Shift'}
              </div>
            </div>

            <div className="p-3 bg-zinc-50 dark:bg-zinc-900/60 rounded-lg">
              <div className="text-muted-foreground text-[11px]">Availability</div>
              <div className="font-bold text-zinc-900 dark:text-zinc-100 mt-0.5 flex items-center gap-1">
                <span className={`w-2 h-2 rounded-full ${
                  profile?.availability_status === 'AVAILABLE' ? 'bg-emerald-500' :
                  profile?.availability_status === 'BUSY' ? 'bg-amber-500' : 'bg-zinc-400'
                }`} />
                {profile?.availability_status || 'OFFLINE'}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Left 2 Cols: Edit Profile Form */}
        <div className="md:col-span-2 space-y-6">
          <Card className="border-zinc-200 dark:border-zinc-800 shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-bold">Personal Information</CardTitle>
              <CardDescription className="text-xs">
                Update your display name, contact phone number, and engineering bio.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSaveProfile} className="space-y-4 text-xs">
                <div className="space-y-1.5">
                  <label className="font-semibold text-zinc-700 dark:text-zinc-300">Full Name / Display Name</label>
                  <Input
                    value={fullName}
                    onChange={e => setFullName(e.target.value)}
                    placeholder="Your Full Name"
                    className="h-9 text-xs"
                    required
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="font-semibold text-zinc-700 dark:text-zinc-300">Phone Number</label>
                    <Input
                      value={phone}
                      onChange={e => setPhone(e.target.value)}
                      placeholder="+91 98765 43210"
                      className="h-9 text-xs"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="font-semibold text-zinc-700 dark:text-zinc-300">Timezone</label>
                    <select
                      value={timezone}
                      onChange={e => setTimezone(e.target.value)}
                      className="w-full h-9 rounded-md border border-input bg-background px-3 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    >
                      <option value="Asia/Kolkata">Asia/Kolkata (IST +5:30)</option>
                      <option value="UTC">UTC (Universal Coordinated Time)</option>
                      <option value="America/New_York">America/New_York (EST/EDT)</option>
                      <option value="America/Los_Angeles">America/Los_Angeles (PST/PDT)</option>
                      <option value="Europe/London">Europe/London (GMT/BST)</option>
                      <option value="Asia/Tokyo">Asia/Tokyo (JST +9:00)</option>
                      <option value="Asia/Singapore">Asia/Singapore (SGT +8:00)</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="font-semibold text-zinc-700 dark:text-zinc-300">Professional Bio</label>
                  <textarea
                    value={bio}
                    onChange={e => setBio(e.target.value)}
                    placeholder="Briefly describe your operational domain, systems experience, or notes for colleagues..."
                    rows={3}
                    className="w-full rounded-md border border-input bg-background p-2.5 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t">
                  <div className="space-y-1.5">
                    <label className="font-semibold text-zinc-700 dark:text-zinc-300">Availability Status</label>
                    <select
                      value={availabilityStatus}
                      onChange={e => setAvailabilityStatus(e.target.value)}
                      className="w-full h-9 rounded-md border border-input bg-background px-3 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    >
                      <option value="AVAILABLE">🟢 Available (Ready for Incidents)</option>
                      <option value="BUSY">🟡 Busy (Investigating P1/P2)</option>
                      <option value="IN_CALL">🟣 In Bridge / Conference</option>
                      <option value="WRAP_UP">🟠 Wrap Up / Handoff</option>
                      <option value="OFFLINE">⚪ Offline / On Break</option>
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="font-semibold text-zinc-700 dark:text-zinc-300">Notification Alerts</label>
                    <select
                      value={notificationPref}
                      onChange={e => setNotificationPref(e.target.value)}
                      className="w-full h-9 rounded-md border border-input bg-background px-3 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    >
                      <option value="ALL">All Incidents & Chat Messages</option>
                      <option value="MENTIONS_ONLY">@Mentions & Direct Messages Only</option>
                      <option value="CRITICAL_ONLY">P1 Critical Incidents Only</option>
                    </select>
                  </div>
                </div>

                <div className="flex justify-end pt-3">
                  <Button
                    type="submit"
                    disabled={isSaving}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs px-5 h-9 flex items-center gap-1.5"
                  >
                    <Save className="h-3.5 w-3.5" />
                    {isSaving ? 'Saving Changes...' : 'Save Profile Changes'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>

        {/* Right 1 Col: Operational Details & Skills */}
        <div className="space-y-6">
          {/* Shift Details Card */}
          <Card className="border-zinc-200 dark:border-zinc-800 shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-bold flex items-center gap-1.5">
                <Clock className="h-4 w-4 text-indigo-600" />
                Shift Assignment
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              {profile?.shift ? (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-zinc-900 dark:text-zinc-100">{profile.shift.name}</span>
                    {profile.shift.is_overnight && (
                      <Badge variant="secondary" className="text-[10px]">Overnight</Badge>
                    )}
                  </div>
                  <div className="text-muted-foreground flex items-center gap-2">
                    <Calendar className="h-3.5 w-3.5" />
                    <span>{profile.shift.start_time} — {profile.shift.end_time}</span>
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    Timezone: {profile.shift.timezone}
                  </div>
                </div>
              ) : (
                <div className="text-center py-4 text-muted-foreground">
                  <Clock className="h-8 w-8 mx-auto mb-1 opacity-40" />
                  <p>No shift assigned for today</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Technical Skills Card */}
          <Card className="border-zinc-200 dark:border-zinc-800 shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-bold flex items-center gap-1.5">
                <Award className="h-4 w-4 text-amber-600" />
                Verified Competencies
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {profile?.skills && profile.skills.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {profile.skills.map(s => (
                    <Badge
                      key={s.id}
                      variant="outline"
                      className="bg-zinc-50 dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800 text-[11px] font-medium"
                    >
                      {s.name}
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">No specific skill tags linked yet.</p>
              )}
            </CardContent>
          </Card>

          {/* Quick Links */}
          <Card className="border-zinc-200 dark:border-zinc-800 shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-bold">Quick Navigation</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-xs">
              <Link
                href="/employee/work"
                className="flex items-center justify-between p-2 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
              >
                <span>My Work Incidents</span>
                <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
              </Link>
              <Link
                href="/employee/team"
                className="flex items-center justify-between p-2 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
              >
                <span>My Team & Shift Roster</span>
                <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
              </Link>
              <Link
                href="/employee/team-chat"
                className="flex items-center justify-between p-2 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
              >
                <span>Team Chat Room</span>
                <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
