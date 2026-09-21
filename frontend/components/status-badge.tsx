import * as React from "react"
import { Badge } from "./ui/badge"
import { getStatusColor, getPriorityColor, getAvailabilityColor } from "@/lib/utils"

export function StatusBadge({ status, type = 'status' }: { status?: string | null; type?: 'status' | 'priority' | 'availability' }) {
  if (!status) return null;
  const safeStatus = String(status);

  if (type === 'priority') {
    const variant = getPriorityColor(safeStatus) as any;
    return <Badge variant={variant}>{safeStatus}</Badge>;
  }
  
  if (type === 'availability') {
    const color = getAvailabilityColor(safeStatus);
    return (
      <div className="flex items-center space-x-2">
        <span className={`h-2 w-2 rounded-full ${color}`} />
        <span className="text-sm font-medium">{safeStatus.replace(/_/g, ' ')}</span>
      </div>
    );
  }

  const variant = getStatusColor(safeStatus) as any;
  return <Badge variant={variant}>{safeStatus.replace(/_/g, ' ')}</Badge>;
}
