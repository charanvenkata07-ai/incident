import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import type { Incident } from '@/types';

export function useIncident(incidentNumber: string) {
  return useQuery({
    queryKey: ['incident', incidentNumber],
    queryFn: () => apiClient.get<Incident>(`/api/incidents/${incidentNumber}`),
    enabled: !!incidentNumber,
  });
}

export function useAcknowledgeIncident() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (incidentNumber: string) => apiClient.post(`/api/incidents/${incidentNumber}/acknowledge`),
    onSuccess: (_, incidentNumber) => {
      queryClient.invalidateQueries({ queryKey: ['incident', incidentNumber] });
      queryClient.invalidateQueries({ queryKey: ['my-work'] });
      toast.success('Incident acknowledged');
    },
    onError: (error: any) => toast.error(error.message),
  });
}

export function useStartWork() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (incidentNumber: string) => apiClient.post(`/api/incidents/${incidentNumber}/start`),
    onSuccess: (_, incidentNumber) => {
      queryClient.invalidateQueries({ queryKey: ['incident', incidentNumber] });
      queryClient.invalidateQueries({ queryKey: ['my-work'] });
      toast.success('Work started on incident');
    },
    onError: (error: any) => toast.error(error.message),
  });
}

export function useCompleteWork() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (incidentNumber: string) => apiClient.post(`/api/incidents/${incidentNumber}/complete`),
    onSuccess: (_, incidentNumber) => {
      queryClient.invalidateQueries({ queryKey: ['incident', incidentNumber] });
      queryClient.invalidateQueries({ queryKey: ['my-work'] });
      toast.success('Work completed on incident');
    },
    onError: (error: any) => toast.error(error.message),
  });
}
