export interface User {
  id: string
  email: string
  full_name: string
  role: 'EMPLOYEE' | 'SUPERVISOR' | 'ADMIN'
  is_active: boolean
}

export interface Employee {
  id: string
  user_id: string
  full_name: string
  email: string
  team_id: string | null
  team_name: string | null
  employee_code: string | null
  availability_status: 'AVAILABLE' | 'BUSY' | 'BREAK' | 'OFFLINE'
  is_present: boolean
  skills: Skill[]
  active_incident_count: number
}

export interface Team {
  id: string
  name: string
  description: string | null
  servicenow_group_id: string | null
  is_active: boolean
  employee_count: number
}

export interface Skill {
  id: string
  name: string
  description: string | null
}

export interface Shift {
  id: string
  name: string
  start_time: string // HH:MM
  end_time: string   // HH:MM
  timezone: string
  is_overnight: boolean
  is_active: boolean
}

export interface ShiftAssignment {
  id: string
  shift: Shift
  employee: Employee
  date: string
  is_active: boolean
}

export interface Incident {
  id: string
  incident_number: string
  servicenow_sys_id: string | null
  short_description: string
  description: string | null
  priority: 'P1' | 'P2' | 'P3' | 'P4'
  impact: string | null
  urgency: string | null
  category: string | null
  subcategory: string | null
  assignment_group: string | null
  assigned_to: string | null
  state: 'NEW' | 'ASSIGNED' | 'ACKNOWLEDGED' | 'IN_PROGRESS' | 'RESOLVED' | 'CLOSED'
  work_notes: string | null
  additional_comments: string | null
  work_instructions: string | null
  opened_at: string | null
  sync_status: 'PENDING' | 'SYNCED' | 'SYNC_FAILED'
  created_at: string
  updated_at: string | null
  current_assignment: AssignmentBrief | null
  activity_timeline: ActivityEvent[]
}

export interface IncidentBrief {
  id: string
  incident_number: string
  short_description: string
  priority: string
  state: string
  assigned_employee_name: string | null
  assignment_status: string | null
  assigned_at: string | null
}

export interface Assignment {
  id: string
  incident_id: string
  incident_number: string
  short_description: string
  employee_id: string
  employee_name: string
  assignment_type: 'AUTOMATIC' | 'MANUAL' | 'SERVICE_NOW'
  status: 'ASSIGNED' | 'ACKNOWLEDGED' | 'IN_PROGRESS' | 'COMPLETED' | 'REASSIGNED' | 'UNASSIGNED'
  reason: string | null
  assigned_at: string
  acknowledged_at: string | null
  started_at: string | null
  completed_at: string | null
}

export interface AssignmentBrief {
  id: string
  employee_name: string
  assignment_type: string
  status: string
  assigned_at: string
}

export interface ActivityEvent {
  id: string
  action: string
  actor_name: string | null
  created_at: string
  old_value: Record<string, unknown> | null
  new_value: Record<string, unknown> | null
  reason: string | null
}

export interface Notification {
  id: string
  type: string
  title: string
  message: string
  incident_id: string | null
  incident_number?: string
  is_read: boolean
  created_at: string
}

export interface DashboardStats {
  active_incidents: number
  unassigned_incidents: number
  employees_on_shift: number
  available_employees: number
  busy_employees: number
}

export interface SystemHealth {
  api: { status: string }
  database: { status: string }
  redis: { status: string }
  worker: { status: string }
  servicenow: { status: string; last_sync: string | null }
}

export interface AuditLog {
  id: string
  actor_name: string | null
  action: string
  entity_type: string
  entity_id: string | null
  old_value: Record<string, unknown> | null
  new_value: Record<string, unknown> | null
  reason: string | null
  created_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
}
