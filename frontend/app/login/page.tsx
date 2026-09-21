'use client';

import * as React from 'react';
import { useAuth } from '@/hooks/use-auth';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { Shield, User, Users, ArrowLeft, KeyRound, Check, ChevronRight } from 'lucide-react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Skeleton } from '@/components/ui/skeleton';

interface LoginGroup {
  id: string;
  name: string;
  work_domain: string | null;
  description: string | null;
  member_count: number;
}

interface LoginEmployee {
  id: string;
  user_id: string;
  name: string;
  email: string;
  employee_code: string | null;
}

type LoginMode = 'SELECTION' | 'ADMIN' | 'EMPLOYEE_STEP_GROUP' | 'EMPLOYEE_STEP_NAME' | 'EMPLOYEE_STEP_PASSWORD';

import { motion } from 'framer-motion';

export default function LoginPage() {
  const { login } = useAuth();

  const [mode, setMode] = React.useState<LoginMode>('SELECTION');
  const [error, setError] = React.useState('');
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  // Admin form state
  const [adminEmail, setAdminEmail] = React.useState('');
  const [adminPassword, setAdminPassword] = React.useState('');

  // Employee selection flow state
  const [groups, setGroups] = React.useState<LoginGroup[]>([]);
  const [loadingGroups, setLoadingGroups] = React.useState(false);
  const [selectedGroup, setSelectedGroup] = React.useState<LoginGroup | null>(null);

  const [employees, setEmployees] = React.useState<LoginEmployee[]>([]);
  const [loadingEmployees, setLoadingEmployees] = React.useState(false);
  const [selectedEmployee, setSelectedEmployee] = React.useState<LoginEmployee | null>(null);

  const [employeePassword, setEmployeePassword] = React.useState('');

  // Load groups when switching to employee login
  const startEmployeeLogin = async () => {
    setError('');
    setMode('EMPLOYEE_STEP_GROUP');
    setLoadingGroups(true);
    try {
      const data = await apiClient.get<LoginGroup[]>('/api/auth/groups');
      setGroups(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load groups');
    } finally {
      setLoadingGroups(false);
    }
  };

  // When group selected -> load its employees
  const handleSelectGroup = async (group: LoginGroup) => {
    setError('');
    setSelectedGroup(group);
    setSelectedEmployee(null);
    setMode('EMPLOYEE_STEP_NAME');
    setLoadingEmployees(true);
    try {
      const data = await apiClient.get<LoginEmployee[]>(`/api/auth/groups/${group.id}/employees`);
      setEmployees(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load employees for selected group');
    } finally {
      setLoadingEmployees(false);
    }
  };

  // When employee selected -> proceed to password authentication
  const handleSelectEmployee = (emp: LoginEmployee) => {
    setError('');
    setSelectedEmployee(emp);
    setEmployeePassword('');
    setMode('EMPLOYEE_STEP_PASSWORD');
  };

  // Submit Admin Login
  const handleAdminSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!adminEmail || !adminPassword) {
      setError('Email and password are required');
      return;
    }
    setIsSubmitting(true);
    setError('');
    try {
      await login(adminEmail, adminPassword);
    } catch (err: any) {
      setError(err?.message || 'Invalid admin credentials');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Submit Employee Login
  const handleEmployeeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEmployee || !selectedGroup || !employeePassword) {
      setError('Password is required');
      return;
    }
    setIsSubmitting(true);
    setError('');
    try {
      await login({
        email: selectedEmployee.email,
        employee_id: selectedEmployee.id,
        password: employeePassword,
        team_id: selectedGroup.id,
      });
    } catch (err: any) {
      setError(err?.message || 'Authentication failed. Please verify your password.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const getInitials = (name: string) => {
    const parts = name.split(' ');
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return name.slice(0, 2).toUpperCase();
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F7F9FC] dark:bg-[#020817] px-3 sm:px-4 py-8">
      <Card className="w-full max-w-lg bg-white/95 dark:bg-[#071426]/95 backdrop-blur-xl border-black/[0.08] dark:border-white/[0.08] shadow-2xl rounded-3xl overflow-hidden">
        <CardHeader className="text-center space-y-2 pt-8 pb-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.96, filter: 'blur(8px)' }}
            animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
            transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            className="flex flex-col items-center justify-center mb-2"
          >
            <div className="relative">
              <div className="absolute -inset-2 rounded-full bg-[#087CFF]/15 blur-xl pointer-events-none" />
              <img
                src="/brand/incidentflow-mark.png"
                alt="IncidentFlow Mark"
                className="relative h-16 w-16 sm:h-20 sm:w-20 object-contain drop-shadow-md"
              />
            </div>
            <div className="flex items-center mt-3">
              <span className="text-2xl font-bold tracking-tight text-[#071A33] dark:text-white">Incident</span>
              <span className="text-2xl font-bold tracking-tight text-[#087CFF] dark:text-[#149BFF]">Flow</span>
            </div>
            <p className="text-[10px] font-bold tracking-widest text-[#667085] dark:text-zinc-400 uppercase mt-0.5">
              Enterprise Real-Time Incident Orchestration
            </p>
          </motion.div>
          <CardDescription className="text-zinc-600 dark:text-zinc-300 text-xs sm:text-sm font-medium">
            {mode === 'SELECTION' && 'Select your access level to sign in'}
            {mode === 'ADMIN' && 'Administrator Control Center sign in'}
            {mode === 'EMPLOYEE_STEP_GROUP' && 'Step 1: Select your operational group'}
            {mode === 'EMPLOYEE_STEP_NAME' && `Step 2: Select your name in ${selectedGroup?.name}`}
            {mode === 'EMPLOYEE_STEP_PASSWORD' && `Step 3: Authenticate as ${selectedEmployee?.name}`}
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {error && (
            <div className="p-3 text-xs sm:text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 rounded border border-red-200 dark:border-red-800 text-center font-medium">
              {error}
            </div>
          )}

          {/* ───────────────────────────────────────────────────────────── */}
          {/* STEP 0: INITIAL SELECTION                                     */}
          {/* ───────────────────────────────────────────────────────────── */}
          {mode === 'SELECTION' && (
            <div className="space-y-3 pt-2">
              <Button
                type="button"
                className="w-full h-16 sm:h-18 flex items-center justify-between px-5 bg-white hover:bg-zinc-100 dark:bg-zinc-900 dark:hover:bg-zinc-800 border-2 border-zinc-200 dark:border-zinc-700 text-zinc-950 dark:text-zinc-50 shadow-sm"
                onClick={() => {
                  setError('');
                  setMode('ADMIN');
                }}
              >
                <div className="flex items-center space-x-3 text-left">
                  <div className="w-10 h-10 rounded-lg bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center text-zinc-800 dark:text-zinc-200">
                    <Shield className="w-5 h-5" />
                  </div>
                  <div>
                    <span className="font-bold text-sm sm:text-base block">ADMIN LOGIN</span>
                    <span className="text-xs text-zinc-500 font-normal">Manage groups, automation, shifts & system settings</span>
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-zinc-400" />
              </Button>

              <Button
                type="button"
                className="w-full h-16 sm:h-18 flex items-center justify-between px-5 bg-white hover:bg-blue-50 dark:bg-zinc-900 dark:hover:bg-zinc-800 border-2 border-blue-200 dark:border-blue-900 text-zinc-950 dark:text-zinc-50 shadow-sm"
                onClick={startEmployeeLogin}
              >
                <div className="flex items-center space-x-3 text-left">
                  <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-950 flex items-center justify-center text-blue-600">
                    <User className="w-5 h-5" />
                  </div>
                  <div>
                    <span className="font-bold text-sm sm:text-base block text-blue-600 dark:text-blue-400">EMPLOYEE LOGIN</span>
                    <span className="text-xs text-zinc-500 font-normal">Select group & engineer identity to access My Work</span>
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-zinc-400" />
              </Button>
            </div>
          )}

          {/* ───────────────────────────────────────────────────────────── */}
          {/* FLOW A: ADMIN LOGIN                                           */}
          {/* ───────────────────────────────────────────────────────────── */}
          {mode === 'ADMIN' && (
            <form onSubmit={handleAdminSubmit} className="space-y-4 pt-1">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">Admin Email Address</label>
                <Input
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                  placeholder="admin@incidentflow.dev"
                  type="email"
                  autoFocus
                  required
                  disabled={isSubmitting}
                  className="bg-white dark:bg-zinc-900"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">Password</label>
                <Input
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  placeholder="••••••••"
                  type="password"
                  required
                  disabled={isSubmitting}
                  className="bg-white dark:bg-zinc-900"
                />
              </div>
              <Button type="submit" className="w-full bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900" disabled={isSubmitting}>
                {isSubmitting ? 'Signing in...' : 'Sign In as Admin'}
              </Button>

              <div className="pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="w-full text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
                  onClick={() => {
                    setError('');
                    setMode('SELECTION');
                  }}
                >
                  <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Back to Sign-in Options
                </Button>
              </div>
            </form>
          )}

          {/* ───────────────────────────────────────────────────────────── */}
          {/* FLOW B - STEP 1: SELECT GROUP                                 */}
          {/* ───────────────────────────────────────────────────────────── */}
          {mode === 'EMPLOYEE_STEP_GROUP' && (
            <div className="space-y-3">
              {loadingGroups ? (
                <div className="space-y-2">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <Skeleton key={i} className="h-14 w-full" />
                  ))}
                </div>
              ) : groups.length === 0 ? (
                <p className="text-center text-sm text-zinc-500 py-6">No active groups found in database.</p>
              ) : (
                <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
                  {groups.map((grp) => (
                    <button
                      key={grp.id}
                      type="button"
                      onClick={() => handleSelectGroup(grp)}
                      className="w-full text-left p-3.5 rounded-lg border border-zinc-200 dark:border-zinc-800 hover:border-blue-500 hover:bg-blue-50/50 dark:hover:bg-zinc-800/60 transition-all flex items-center justify-between group active:scale-[0.99]"
                    >
                      <div className="flex-1 min-w-0 pr-2">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-sm text-zinc-900 dark:text-zinc-100 group-hover:text-blue-600 dark:group-hover:text-blue-400">
                            {grp.name}
                          </span>
                          <span className="text-[10px] font-semibold text-zinc-500 bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">
                            {grp.member_count} members
                          </span>
                        </div>
                        {grp.work_domain && (
                          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 line-clamp-1">
                            {grp.work_domain}
                          </p>
                        )}
                      </div>
                      <ChevronRight className="w-4 h-4 text-zinc-400 group-hover:text-blue-600 dark:group-hover:text-blue-400 flex-shrink-0" />
                    </button>
                  ))}
                </div>
              )}

              <div className="pt-2 border-t border-zinc-100 dark:border-zinc-800">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="w-full text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
                  onClick={() => {
                    setError('');
                    setMode('SELECTION');
                  }}
                >
                  <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Back to Sign-in Options
                </Button>
              </div>
            </div>
          )}

          {/* ───────────────────────────────────────────────────────────── */}
          {/* FLOW B - STEP 2: SELECT EMPLOYEE IN GROUP                     */}
          {/* ───────────────────────────────────────────────────────────── */}
          {mode === 'EMPLOYEE_STEP_NAME' && selectedGroup && (
            <div className="space-y-3">
              {/* Group context banner */}
              <div className="bg-blue-50/60 dark:bg-blue-950/30 p-2.5 rounded-md border border-blue-200 dark:border-blue-900 text-xs">
                <span className="font-semibold text-blue-700 dark:text-blue-300 block">{selectedGroup.name}</span>
                <span className="text-zinc-500 dark:text-zinc-400">{selectedGroup.work_domain}</span>
              </div>

              {loadingEmployees ? (
                <div className="space-y-2">
                  {[1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : employees.length === 0 ? (
                <p className="text-center text-sm text-zinc-500 py-6">No active employees found in this group.</p>
              ) : (
                <div className="space-y-2 max-h-[55vh] overflow-y-auto pr-1">
                  {employees.map((emp) => (
                    <button
                      key={emp.id}
                      type="button"
                      onClick={() => handleSelectEmployee(emp)}
                      className="w-full text-left p-3 rounded-lg border border-zinc-200 dark:border-zinc-800 hover:border-blue-500 hover:bg-blue-50/40 dark:hover:bg-zinc-800/60 transition-all flex items-center justify-between group active:scale-[0.99]"
                    >
                      <div className="flex items-center space-x-3">
                        <Avatar className="w-8 h-8 text-xs bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200">
                          <AvatarFallback>{getInitials(emp.name)}</AvatarFallback>
                        </Avatar>
                        <div>
                          <p className="font-semibold text-sm text-zinc-900 dark:text-zinc-100 group-hover:text-blue-600 dark:group-hover:text-blue-400">
                            {emp.name}
                          </p>
                          <p className="text-[11px] text-zinc-500 font-mono">
                            {emp.employee_code || emp.email}
                          </p>
                        </div>
                      </div>
                      <ChevronRight className="w-4 h-4 text-zinc-400 group-hover:text-blue-600 dark:group-hover:text-blue-400" />
                    </button>
                  ))}
                </div>
              )}

              <div className="pt-2 border-t border-zinc-100 dark:border-zinc-800 flex justify-between">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
                  onClick={() => {
                    setError('');
                    setMode('EMPLOYEE_STEP_GROUP');
                  }}
                >
                  <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Back to Groups
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
                  onClick={() => {
                    setError('');
                    setMode('SELECTION');
                  }}
                >
                  Sign-in Options
                </Button>
              </div>
            </div>
          )}

          {/* ───────────────────────────────────────────────────────────── */}
          {/* FLOW B - STEP 3: PASSWORD AUTHENTICATION                      */}
          {/* ───────────────────────────────────────────────────────────── */}
          {mode === 'EMPLOYEE_STEP_PASSWORD' && selectedGroup && selectedEmployee && (
            <form onSubmit={handleEmployeeSubmit} className="space-y-4 pt-1">
              {/* Selected engineer summary box */}
              <div className="p-3 bg-zinc-50 dark:bg-zinc-800/60 rounded-lg border border-zinc-200 dark:border-zinc-700 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <Avatar className="w-10 h-10 bg-blue-600 text-white font-bold">
                    <AvatarFallback>{getInitials(selectedEmployee.name)}</AvatarFallback>
                  </Avatar>
                  <div>
                    <p className="font-bold text-sm text-zinc-950 dark:text-zinc-50">{selectedEmployee.name}</p>
                    <p className="text-xs text-indigo-600 dark:text-indigo-400 font-medium">{selectedGroup.name}</p>
                  </div>
                </div>
                <span className="text-[10px] font-mono text-zinc-500 bg-white dark:bg-zinc-900 px-2 py-1 rounded border">
                  {selectedEmployee.employee_code || 'ACTIVE'}
                </span>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">Enter Password</label>
                <Input
                  value={employeePassword}
                  onChange={(e) => setEmployeePassword(e.target.value)}
                  placeholder="••••••••"
                  type="password"
                  autoFocus
                  required
                  disabled={isSubmitting}
                  className="bg-white dark:bg-zinc-900"
                />
              </div>

              <Button type="submit" className="w-full bg-blue-600 text-white hover:bg-blue-700" disabled={isSubmitting}>
                {isSubmitting ? 'Verifying credentials...' : `Sign In as ${selectedEmployee.name.split(' ')[0]}`}
              </Button>

              <div className="pt-2 border-t border-zinc-100 dark:border-zinc-800 flex justify-between">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
                  onClick={() => {
                    setError('');
                    setMode('EMPLOYEE_STEP_NAME');
                  }}
                >
                  <ArrowLeft className="w-3.5 h-3.5 mr-1" /> Back to Employees
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
                  onClick={() => {
                    setError('');
                    setMode('SELECTION');
                  }}
                >
                  Sign-in Options
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
