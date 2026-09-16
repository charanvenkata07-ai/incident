import * as React from "react"
import { Badge } from "./ui/badge"
import { getStatusColor, getPriorityColor, getAvailabilityColor } from "@/lib/utils"

export function StatusBadge({ status, type = 'status' }: { status: string; type?: 'status' | 'priority' | 'availability' }) {
  if (type === 'priority') {
    const variant = getPriorityColor(status) as any;
    return <Badge variant={variant}>{status}</Badge>;
  }
  
  if (type === 'availability') {
    const color = getAvailabilityColor(status);
    return (
      <div className="flex items-center space-x-2">
        <span className={`h-2 w-2 rounded-full ${color}`} />
        <span className="text-sm font-medium">{status.replace('_', ' ')}</span>
      </div>
    );
  }

  const variant = getStatusColor(status) as any;
  return <Badge variant={variant}>{status.replace('_', ' ')}</Badge>;
}
