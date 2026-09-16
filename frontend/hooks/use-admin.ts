import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';

export function useAdminDashboard() {
  return useQuery({
    queryKey: ['admin-dashboard'],
    queryFn: () => apiClient.get('/api/admin/dashboard'),
  });
}

export function useAdminEmployees() {
  return useQuery({
    queryKey: ['admin-employees'],
    queryFn: () => apiClient.get('/api/admin/employees'),
  });
}

export function useAdminSettings() {
  return useQuery({
    queryKey: ['admin-settings'],
    queryFn: () => apiClient.get('/api/admin/settings'),
  });
}
