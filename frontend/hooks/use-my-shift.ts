import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { ShiftAssignment } from '@/types';

export function useMyShift() {
  return useQuery({
    queryKey: ['my-shift'],
    queryFn: () => apiClient.get<ShiftAssignment>('/api/me/shift'),
  });
}
