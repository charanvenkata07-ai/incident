import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { format, formatDistanceToNow, parseISO } from 'date-fns';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '';
  try {
    const d = typeof dateString === 'string' ? parseISO(dateString) : new Date(dateString);
    if (isNaN(d.getTime())) return '';
    return format(d, 'MMM d, yyyy');
  } catch {
    return '';
  }
}

export function formatTime(dateString: string | null | undefined): string {
  if (!dateString) return '';
  try {
    const d = typeof dateString === 'string' ? parseISO(dateString) : new Date(dateString);
    if (isNaN(d.getTime())) return '';
    return format(d, 'h:mm a');
  } catch {
    return '';
  }
}

export function formatRelativeTime(dateString: string | null | undefined): string {
  if (!dateString) return '';
  try {
    const d = typeof dateString === 'string' ? parseISO(dateString) : new Date(dateString);
    if (isNaN(d.getTime())) return '';
    return formatDistanceToNow(d, { addSuffix: true });
  } catch {
    return '';
  }
}

export function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export function getPriorityColor(priority?: string | null): string {
  if (!priority) return 'default';
  switch (String(priority).toUpperCase()) {
    case 'P1': return 'destructive';
    case 'P2': return 'warning';
    case 'P3': return 'warning';
    case 'P4': return 'info';
    default: return 'default';
  }
}

export function getStatusColor(status?: string | null): string {
  if (!status) return 'default';
  switch (String(status).toUpperCase()) {
    case 'NEW': return 'default';
    case 'ASSIGNED': return 'info';
    case 'ACKNOWLEDGED': return 'warning';
    case 'IN_PROGRESS': return 'info';
    case 'COMPLETED':
    case 'RESOLVED':
    case 'CLOSED': return 'success';
    default: return 'default';
  }
}

export function getAvailabilityColor(status?: string | null): string {
  if (!status) return 'bg-zinc-500';
  switch (String(status).toUpperCase()) {
    case 'AVAILABLE': return 'bg-green-500';
    case 'BUSY': return 'bg-yellow-500';
    case 'BREAK': return 'bg-orange-500';
    case 'OFFLINE': return 'bg-zinc-500';
    default: return 'bg-zinc-500';
  }
}
