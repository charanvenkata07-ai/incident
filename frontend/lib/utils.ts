import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { format, formatDistanceToNow, parseISO } from 'date-fns';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '';
  return format(parseISO(dateString), 'MMM d, yyyy');
}

export function formatTime(dateString: string | null | undefined): string {
  if (!dateString) return '';
  return format(parseISO(dateString), 'h:mm a');
}

export function formatRelativeTime(dateString: string | null | undefined): string {
  if (!dateString) return '';
  return formatDistanceToNow(parseISO(dateString), { addSuffix: true });
}

export function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export function getPriorityColor(priority: string): string {
  switch (priority.toUpperCase()) {
    case 'P1': return 'destructive';
    case 'P2': return 'warning';
    case 'P3': return 'warning';
    case 'P4': return 'info';
    default: return 'default';
  }
}

export function getStatusColor(status: string): string {
  switch (status.toUpperCase()) {
    case 'NEW':
    case 'ASSIGNED': return 'info';
    case 'ACKNOWLEDGED': return 'warning';
    case 'IN_PROGRESS': return 'success';
    case 'COMPLETED':
    case 'RESOLVED':
    case 'CLOSED': return 'default';
    default: return 'default';
  }
}

export function getAvailabilityColor(status: string): string {
  switch (status.toUpperCase()) {
    case 'AVAILABLE': return 'bg-green-500';
    case 'BUSY': return 'bg-yellow-500';
    case 'BREAK': return 'bg-orange-500';
    case 'OFFLINE': return 'bg-zinc-500';
    default: return 'bg-zinc-500';
  }
}
