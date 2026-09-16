import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { IncidentBrief } from '@/types';

export function useMyWork(statusFilter?: string) {
  return useQuery({
    queryKey: ['my-work', statusFilter],
    queryFn: () => {
      const queryParams = statusFilter ? `?status=${statusFilter}` : '';
      return apiClient.get<IncidentBrief[]>(`/api/me/work${queryParams}`);
    },
  });
}
