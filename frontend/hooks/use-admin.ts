import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import type { DashboardStats, Employee, Incident, Assignment, AuditLog, SystemHealth } from '@/types';

export function useAdminDashboard() {
  return useQuery<DashboardStats>({
    queryKey: ['admin-dashboard'],
    queryFn: () => apiClient.get<DashboardStats>('/api/admin/dashboard'),
  });
}

export function useAdminEmployees() {
  return useQuery<Employee[]>({
    queryKey: ['admin-employees'],
    queryFn: () => apiClient.get<Employee[]>('/api/admin/employees'),
  });
}

export function useAdminIncidents(filters?: Record<string, string>) {
  return useQuery<{ items: Incident[]; total: number }>({
    queryKey: ['admin-incidents', filters],
    queryFn: () => {
      const params = new URLSearchParams(filters || {}).toString();
      return apiClient.get(`/api/admin/incidents${params ? `?${params}` : ''}`);
    },
  });
}

export function useAdminShifts() {
  return useQuery({
    queryKey: ['admin-shifts'],
    queryFn: () => apiClient.get('/api/admin/shifts'),
  });
}

export function useAdminAssignments(filters?: Record<string, string>) {
  return useQuery<{ items: Assignment[]; total: number }>({
    queryKey: ['admin-assignments', filters],
    queryFn: () => {
      const params = new URLSearchParams(filters || {}).toString();
      return apiClient.get(`/api/admin/assignments${params ? `?${params}` : ''}`);
    },
  });
}

export function useAdminAnalytics() {
  return useQuery({
    queryKey: ['admin-analytics'],
    queryFn: () => apiClient.get('/api/admin/analytics'),
  });
}

export function useAdminAuditLogs(filters?: Record<string, string>) {
  return useQuery<{ items: AuditLog[]; total: number }>({
    queryKey: ['admin-audit-logs', filters],
    queryFn: () => {
      const params = new URLSearchParams(filters || {}).toString();
      return apiClient.get(`/api/admin/audit-logs${params ? `?${params}` : ''}`);
    },
  });
}

export function useAdminSettings() {
  return useQuery({
    queryKey: ['admin-settings'],
    queryFn: () => apiClient.get('/api/admin/settings'),
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => apiClient.patch('/api/admin/settings', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-settings'] });
      toast.success('Settings updated');
    },
    onError: () => toast.error('Failed to update settings'),
  });
}

export function useManualAssign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ incidentId, employeeId, reason }: { incidentId: string; employeeId: string; reason?: string }) =>
      apiClient.post(`/api/admin/incidents/${incidentId}/assign`, { employee_id: employeeId, reason }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-assignments'] });
      queryClient.invalidateQueries({ queryKey: ['admin-incidents'] });
      queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
      toast.success('Incident assigned');
    },
    onError: () => toast.error('Failed to assign incident'),
  });
}

export function useReassign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ incidentId, employeeId, reason }: { incidentId: string; employeeId: string; reason?: string }) =>
      apiClient.post(`/api/admin/incidents/${incidentId}/reassign`, { new_employee_id: employeeId, reason }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-assignments'] });
      queryClient.invalidateQueries({ queryKey: ['admin-incidents'] });
      toast.success('Incident reassigned');
    },
    onError: () => toast.error('Failed to reassign incident'),
  });
}

export function useUnassign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (incidentId: string) => apiClient.post(`/api/admin/incidents/${incidentId}/unassign`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-assignments'] });
      queryClient.invalidateQueries({ queryKey: ['admin-incidents'] });
      queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
      toast.success('Incident unassigned');
    },
    onError: () => toast.error('Failed to unassign incident'),
  });
}

export function useCreateShift() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => apiClient.post('/api/admin/shifts', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-shifts'] });
      toast.success('Shift created');
    },
    onError: () => toast.error('Failed to create shift'),
  });
}

export function useUpdateShift() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) => apiClient.patch(`/api/admin/shifts/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-shifts'] });
      toast.success('Shift updated');
    },
    onError: () => toast.error('Failed to update shift'),
  });
}

export function useAdminHealth() {
  return useQuery<SystemHealth>({
    queryKey: ['admin-health'],
    queryFn: () => apiClient.get<SystemHealth>('/api/admin/health'),
    refetchInterval: 30000,
  });
}
