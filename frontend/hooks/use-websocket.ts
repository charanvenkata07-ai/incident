'use client';

import { useEffect, useState } from 'react';
import { wsClient } from '@/lib/websocket';
import { useAuth } from './use-auth';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

export function useWebSocket() {
  const { isAuthenticated, token } = useAuth();
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (isAuthenticated && token) {
      wsClient.setToken(token);
      wsClient.connect();
      setIsConnected(true);

      const handleIncidentAssigned = (data: any) => {
        queryClient.invalidateQueries({ queryKey: ['my-work'] });
        toast.info(`New incident assigned: ${data.incident_number}`);
      };

      const handleIncidentUpdated = (data: any) => {
        queryClient.invalidateQueries({ queryKey: ['incident', data.incident_number] });
        queryClient.invalidateQueries({ queryKey: ['my-work'] });
      };

      const handleNotification = () => {
        queryClient.invalidateQueries({ queryKey: ['notifications'] });
      };

      wsClient.on('INCIDENT_ASSIGNED', handleIncidentAssigned);
      wsClient.on('INCIDENT_UPDATED', handleIncidentUpdated);
      wsClient.on('NOTIFICATION_CREATED', handleNotification);

      return () => {
        wsClient.off('INCIDENT_ASSIGNED', handleIncidentAssigned);
        wsClient.off('INCIDENT_UPDATED', handleIncidentUpdated);
        wsClient.off('NOTIFICATION_CREATED', handleNotification);
        wsClient.disconnect();
        setIsConnected(false);
      };
    }
  }, [isAuthenticated, token, queryClient]);

  return { isConnected };
}
