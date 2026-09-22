import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import type { Incident, IncidentBrief } from '@/types';

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
    onMutate: async (incidentNumber: string) => {
      await queryClient.cancelQueries({ queryKey: ['incident', incidentNumber] });
      await queryClient.cancelQueries({ queryKey: ['my-work'] });

      const previousMyWork = queryClient.getQueriesData<IncidentBrief[]>({ queryKey: ['my-work'] });
      const previousIncident = queryClient.getQueryData<Incident>(['incident', incidentNumber]);

      queryClient.setQueriesData<IncidentBrief[]>({ queryKey: ['my-work'] }, (old) => {
        if (!old || !Array.isArray(old)) return old;
        return old.map((item) =>
          item.incident_number === incidentNumber || item.id === incidentNumber
            ? { ...item, state: 'ACKNOWLEDGED', assignment_status: 'ACKNOWLEDGED' }
            : item
        );
      });

      queryClient.setQueryData<Incident | undefined>(['incident', incidentNumber], (old) => {
        if (!old) return old;
        return {
          ...old,
          state: 'ACKNOWLEDGED',
          current_assignment: old.current_assignment
            ? { ...old.current_assignment, status: 'ACKNOWLEDGED', acknowledged_at: new Date().toISOString() }
            : null,
        };
      });

      return { previousMyWork, previousIncident };
    },
    onError: (error: any, incidentNumber, context) => {
      if (context?.previousMyWork) {
        context.previousMyWork.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
      if (context?.previousIncident) {
        queryClient.setQueryData(['incident', incidentNumber], context.previousIncident);
      }
      toast.error(error?.message || 'Failed to acknowledge incident');
    },
    onSuccess: (_, incidentNumber) => {
      queryClient.setQueriesData<IncidentBrief[]>({ queryKey: ['my-work'] }, (old) => {
        if (!old || !Array.isArray(old)) return old;
        return old.map((item) =>
          item.incident_number === incidentNumber || item.id === incidentNumber
            ? { ...item, state: 'ACKNOWLEDGED', assignment_status: 'ACKNOWLEDGED' }
            : item
        );
      });
      queryClient.invalidateQueries({ queryKey: ['incident', incidentNumber] });
      queryClient.invalidateQueries({ queryKey: ['my-work'] });
      toast.success('Incident acknowledged');
    },
  });
}

export function useStartWork() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (incidentNumber: string) => apiClient.post(`/api/incidents/${incidentNumber}/start`),
    onMutate: async (incidentNumber: string) => {
      await queryClient.cancelQueries({ queryKey: ['incident', incidentNumber] });
      await queryClient.cancelQueries({ queryKey: ['my-work'] });

      const previousMyWork = queryClient.getQueriesData<IncidentBrief[]>({ queryKey: ['my-work'] });
      const previousIncident = queryClient.getQueryData<Incident>(['incident', incidentNumber]);

      queryClient.setQueriesData<IncidentBrief[]>({ queryKey: ['my-work'] }, (old) => {
        if (!old || !Array.isArray(old)) return old;
        return old.map((item) =>
          item.incident_number === incidentNumber || item.id === incidentNumber
            ? { ...item, state: 'IN_PROGRESS', assignment_status: 'IN_PROGRESS' }
            : item
        );
      });

      queryClient.setQueryData<Incident | undefined>(['incident', incidentNumber], (old) => {
        if (!old) return old;
        return {
          ...old,
          state: 'IN_PROGRESS',
          current_assignment: old.current_assignment
            ? { ...old.current_assignment, status: 'IN_PROGRESS', started_at: new Date().toISOString() }
            : null,
        };
      });

      return { previousMyWork, previousIncident };
    },
    onError: (error: any, incidentNumber, context) => {
      if (context?.previousMyWork) {
        context.previousMyWork.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
      if (context?.previousIncident) {
        queryClient.setQueryData(['incident', incidentNumber], context.previousIncident);
      }
      toast.error(error?.message || 'Failed to start work');
    },
    onSuccess: (_, incidentNumber) => {
      queryClient.setQueriesData<IncidentBrief[]>({ queryKey: ['my-work'] }, (old) => {
        if (!old || !Array.isArray(old)) return old;
        return old.map((item) =>
          item.incident_number === incidentNumber || item.id === incidentNumber
            ? { ...item, state: 'IN_PROGRESS', assignment_status: 'IN_PROGRESS' }
            : item
        );
      });
      queryClient.invalidateQueries({ queryKey: ['incident', incidentNumber] });
      queryClient.invalidateQueries({ queryKey: ['my-work'] });
      toast.success('Work started on incident');
    },
  });
}

export function useCompleteWork() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (incidentNumber: string) => apiClient.post(`/api/incidents/${incidentNumber}/complete`),
    onMutate: async (incidentNumber: string) => {
      await queryClient.cancelQueries({ queryKey: ['incident', incidentNumber] });
      await queryClient.cancelQueries({ queryKey: ['my-work'] });

      const previousMyWork = queryClient.getQueriesData<IncidentBrief[]>({ queryKey: ['my-work'] });
      const previousIncident = queryClient.getQueryData<Incident>(['incident', incidentNumber]);

      queryClient.setQueriesData<IncidentBrief[]>({ queryKey: ['my-work'] }, (old) => {
        if (!old || !Array.isArray(old)) return old;
        return old.map((item) =>
          item.incident_number === incidentNumber || item.id === incidentNumber
            ? { ...item, state: 'RESOLVED', assignment_status: 'COMPLETED' }
            : item
        );
      });

      queryClient.setQueryData<Incident | undefined>(['incident', incidentNumber], (old) => {
        if (!old) return old;
        return {
          ...old,
          state: 'RESOLVED',
          current_assignment: old.current_assignment
            ? { ...old.current_assignment, status: 'COMPLETED', completed_at: new Date().toISOString() }
            : null,
        };
      });

      return { previousMyWork, previousIncident };
    },
    onError: (error: any, incidentNumber, context) => {
      if (context?.previousMyWork) {
        context.previousMyWork.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
      if (context?.previousIncident) {
        queryClient.setQueryData(['incident', incidentNumber], context.previousIncident);
      }
      toast.error(error?.message || 'Failed to complete work');
    },
    onSuccess: (_, incidentNumber) => {
      queryClient.setQueriesData<IncidentBrief[]>({ queryKey: ['my-work'] }, (old) => {
        if (!old || !Array.isArray(old)) return old;
        return old.map((item) =>
          item.incident_number === incidentNumber || item.id === incidentNumber
            ? { ...item, state: 'RESOLVED', assignment_status: 'COMPLETED' }
            : item
        );
      });
      queryClient.invalidateQueries({ queryKey: ['incident', incidentNumber] });
      queryClient.invalidateQueries({ queryKey: ['my-work'] });
      toast.success('Work completed on incident');
    },
  });
}
