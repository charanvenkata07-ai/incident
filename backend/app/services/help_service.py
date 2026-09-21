"""
IncidentFlow — Admin Help Center & Feature Documentation Service
Provides authoritative documentation, feature registry, search,
summaries, FAQs, and real-time coverage auditing.
"""
from typing import Optional, Dict, Any, List
import re

HELP_CATEGORIES = [
    {
        "id": "core_operations",
        "name": "Core Operations",
        "description": "Essential workflows for managing incidents, assignments, individual workloads, and real-time alerts.",
        "icon": "LayoutDashboard"
    },
    {
        "id": "people_and_teams",
        "name": "People & Teams",
        "description": "Operational workforce configuration, mandatory 10-employee team invariants, and Group Leader permissions.",
        "icon": "Users"
    },
    {
        "id": "scheduling",
        "name": "Scheduling",
        "description": "Shift coverage as the primary assignment authority, 24/7 rotations, Saturday working days, and Sunday holidays.",
        "icon": "Calendar"
    },
    {
        "id": "automation",
        "name": "Automation",
        "description": "Schedule-driven assignment engine, deterministic rotation, incident history deduplication, and protection modes.",
        "icon": "Zap"
    },
    {
        "id": "servicenow",
        "name": "ServiceNow",
        "description": "Bi-directional ServiceNow synchronization, webhooks, field mappings, sys_ids, and staging pipeline.",
        "icon": "GitBranch"
    },
    {
        "id": "communication",
        "name": "Communication",
        "description": "Real-time Team Chat, Admin-Leader private channels, incident threads, rich media, and server-side moderation.",
        "icon": "MessageSquare"
    },
    {
        "id": "administration",
        "name": "Administration",
        "description": "System configuration, Admin-managed Task Catalog, role-based access control (RBAC), and preferences.",
        "icon": "Settings"
    },
    {
        "id": "monitoring",
        "name": "Monitoring",
        "description": "Operational analytics, immutable audit logs, real-time diagnostics, and synchronization health telemetry.",
        "icon": "TrendingUp"
    },
    {
        "id": "security",
        "name": "Security",
        "description": "Enterprise JWT authentication, authorization scopes, webhook signatures, and sandboxed media uploads.",
        "icon": "Shield"
    },
    {
        "id": "troubleshooting",
        "name": "Troubleshooting",
        "description": "Diagnostic resolutions, common error codes, connection recovery steps, and incident assignment exception handling.",
        "icon": "AlertCircle"
    }
]

# Complete Registry of Actual Admin Features (Must match 100% with documented articles)
ACTUAL_ADMIN_FEATURES = [
    "admin_dashboard",
    "employees",
    "teams",
    "group_leader",
    "employee_ids",
    "shifts",
    "working_days",
    "incidents",
    "automatic_assignment",
    "team_notice",
    "assignment_rotation",
    "my_work",
    "task_catalog",
    "notifications",
    "chat_system",
    "admin_leader_chat",
    "global_search",
    "servicenow_integration",
    "shadow_mode",
    "live_mode",
    "email_smtp",
    "analytics",
    "audit_logs",
    "diagnostics",
    "security_rbac",
    "failed_to_fetch_troubleshooting",
    "backend_unavailable_troubleshooting",
    "cors_failure_troubleshooting",
    "websocket_troubleshooting",
    "chat_failure_troubleshooting",
    "notifications_troubleshooting",
    "servicenow_troubleshooting",
    "smtp_email_troubleshooting",
    "duplicate_assignment_troubleshooting",
    "unassigned_incident_troubleshooting",
    "team_activation_blocked_troubleshooting",
    "duplicate_employee_id_troubleshooting",
    "task_catalog_precedence_troubleshooting",
    "my_work_sync_troubleshooting",
    "upload_failure_troubleshooting",
    "sunday_holiday_troubleshooting",
    "cross_team_assignment_troubleshooting",
    "midnight_shift_troubleshooting"
]

HELP_ARTICLES: List[Dict[str, Any]] = [
    # -----------------------------------------------------------------------
    # 1. CORE OPERATIONS
    # -----------------------------------------------------------------------
    {
        "id": "admin_dashboard",
        "feature_key": "admin_dashboard",
        "slug": "admin-dashboard",
        "title": "Admin Dashboard",
        "category_id": "core_operations",
        "category_name": "Core Operations",
        "summary": "Centralized executive overview displaying real-time incident metrics, active shifts, team capacity, automation mode, and health telemetry.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "The Admin Dashboard provides a real-time command center for administrators. It aggregates incoming incident statistics, team roster status, active shift coverage, workload distribution, and ServiceNow integration states into a single unified telemetry view.",
        "how_it_works": [
            "Loads active incident counts segmented by state (NEW, ASSIGNED, IN_PROGRESS, RESOLVED, CLOSED).",
            "Queries the active 24/7 shift for the configured team timezone (Asia/Kolkata) and displays on-duty engineers.",
            "Displays the system automation status banner: LIVE (active mutation), SHADOW (simulated assignments with 0 ServiceNow mutations), or PAUSED.",
            "Shows real-time WebSocket connection state and system health indicators (Database, Redis, Worker, ServiceNow, SMTP).",
            "Streams live group activity events and recent audit log actions across all teams."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR"],
        "who_can_use_it_description": "Administrators and Supervisors. Ordinary employees have access to their personal dashboard instead.",
        "important_rules": [
            "Dashboard metrics reflect live database state; real-time updates are driven by authenticated WebSockets.",
            "The automation banner warns prominently if LIVE mode is enabled.",
            "All timestamps are calculated in the team's timezone (Asia/Kolkata) and displayed in localized formats."
        ],
        "common_problems": [
            "Metrics showing 0: Verify that database migrations and initial seeder scripts have been executed.",
            "Connection banner red/offline: Verify that the FastAPI backend server is running and port 8000 is accessible."
        ],
        "troubleshooting": [
            {
                "problem": "Dashboard metrics fail to load or show 'Error fetching dashboard data'",
                "possible_causes": "Backend server down, expired JWT session token, or database query timeout.",
                "what_to_check": "Inspect browser Network tab for /api/admin/dashboard HTTP 401 or 500 responses.",
                "expected_behavior": "Returns HTTP 200 with JSON summary containing incident_counts, team_counts, and active_shift.",
                "resolution": "Re-authenticate if the JWT has expired; restart backend server if offline.",
                "escalation": "Escalate to backend engineering if PostgreSQL connection pool is saturated."
            }
        ],
        "faqs": [
            {
                "question": "What is the difference between New and Unassigned incidents?",
                "answer": "New indicates the incident recently ingested from ServiceNow. Unassigned indicates the incident is awaiting scheduled shift coverage or has completed all team member cycles."
            },
            {
                "question": "Why does the dashboard show 0 present employees but work is still assigned?",
                "answer": "IncidentFlow uses schedule-driven assignment where scheduled shift determines assignment coverage, not presence."
            }
        ],
        "summary_bullets": [
            "Aggregates live incident, assignment, and team metrics.",
            "Displays current active shift and on-duty workforce.",
            "Shows automation mode (LIVE, SHADOW, or PAUSED).",
            "Real-time updates delivered over secure WebSockets."
        ],
        "keywords": ["dashboard", "metrics", "incidents", "overview", "statistics", "kpi", "telemetry"],
        "related_features": ["incidents", "shifts", "analytics", "diagnostics"],
        "contextual_hint": "Provides high-level operational statistics and real-time system status across all teams."
    },
    {
        "id": "incidents",
        "feature_key": "incidents",
        "slug": "incidents-management",
        "title": "Incident Management",
        "category_id": "core_operations",
        "category_name": "Core Operations",
        "summary": "Ingestion, inspection, and administrative orchestration of incidents sourced from ServiceNow.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Provides complete administrative control over incidents. Displays the full ServiceNow incident record including incident_number, sys_id, short description, priority (P1–P4), assignment group, work notes, comments, and historical assignment records.",
        "how_it_works": [
            "Incidents are ingested via the ServiceNow webhook (/api/integrations/servicenow/webhook) or created manually.",
            "ServiceNow remains the authoritative source of truth for incident data; IncidentFlow acts as the intelligent orchestration and assignment layer.",
            "Administrators can inspect incident details, assignees, work instructions, and the complete assignment audit history.",
            "Manual assignment allows an Admin to override automated assignment, subject to strict cross-team protection."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR"],
        "who_can_use_it_description": "Administrators and Supervisors. Assigned employees view and work on incidents in My Work.",
        "important_rules": [
            "ServiceNow is always the source of truth for incident data.",
            "Cross-team assignment is strictly blocked: an incident belonging to 'Database L2' cannot be manually assigned to an employee of 'Linux L2'.",
            "An incident can have only ONE active personal assignment at any given time (enforced by DB unique index)."
        ],
        "common_problems": [
            "Duplicate incident records: Ingestion uses the servicenow_sys_id as unique idempotency key.",
            "Cross-team block error: Admin attempted to assign an engineer outside the designated group."
        ],
        "troubleshooting": [
            {
                "problem": "Cross-team assignment blocked error (HTTP 400)",
                "possible_causes": "Target employee belongs to a team other than the incident's assignment group.",
                "what_to_check": "Verify target employee's team in Admin > Employees vs the incident's assignment group.",
                "expected_behavior": "Server strictly rejects cross-team assignments with code CROSS_TEAM_ASSIGNMENT_BLOCKED.",
                "resolution": "Select an employee belonging to the matching team or reassign the incident group in ServiceNow first.",
                "escalation": "Contact Admin lead if team restructuring is required."
            }
        ],
        "faqs": [
            {
                "question": "Can I manually assign an incident to anyone?",
                "answer": "Only to active employees belonging to the incident's designated assignment group. Cross-team assignment is strictly blocked."
            },
            {
                "question": "Does manual assignment update ServiceNow?",
                "answer": "In LIVE mode, assigned_to is updated in ServiceNow. In SHADOW or DRY_RUN mode, ServiceNow is not mutated."
            }
        ],
        "summary_bullets": [
            "ServiceNow is the authoritative source of truth for incidents.",
            "IncidentFlow orchestrates assignment and work execution.",
            "Strict cross-team assignment blocking protects domain integrity.",
            "Maintains full permanent assignment history."
        ],
        "keywords": ["incident", "servicenow", "priority", "assignment group", "work notes", "sys_id"],
        "related_features": ["automatic_assignment", "assignments", "servicenow_integration"],
        "contextual_hint": "Manage and inspect incidents ingested from ServiceNow or created for operational dispatch."
    },
    {
        "id": "my_work",
        "feature_key": "my_work",
        "slug": "my-work",
        "title": "My Work & Task Lifecycle",
        "category_id": "core_operations",
        "category_name": "Core Operations",
        "summary": "Personal work queue where assigned engineers review, acknowledge, execute, and complete their assigned incidents.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "My Work is the personal operational workbench for employees. Exactly ONE scheduled employee receives personal ownership of an incident and sees it in My Work with clear task instructions and lifecycle actions.",
        "how_it_works": [
            "When an incident is assigned, only the selected engineer receives personal ownership.",
            "The engineer sees the item with status 'ASSIGNED' and clicks 'Acknowledge' (transitions to 'ACKNOWLEDGED').",
            "The engineer clicks 'Start Work' (transitions to 'IN_PROGRESS', recording started_at timestamp).",
            "The engineer performs the required diagnostic or remediation steps outlined in 'YOUR TASK'.",
            "The engineer clicks 'Complete' (transitions to 'COMPLETED', sets is_active=False, records completed_at, and permanently archives the record in history).",
            "Upon completion, the engineer's active workload drops to 0, making them eligible for new work."
        ],
        "who_can_use_it": ["EMPLOYEE", "ADMIN", "SUPERVISOR"],
        "who_can_use_it_description": "Engineers view their personal work; Admins can inspect active work assignments across all employees.",
        "important_rules": [
            "Only the single assigned employee sees the active task in My Work. Teammates receive the informational Group Notice but do NOT see personal task ownership.",
            "Work completion is permanent: the assignment record remains in historical audit and cannot be deleted.",
            "Completing an incident frees the engineer for NEW work, but prevents the same incident from returning to them during the same cycle."
        ],
        "common_problems": [
            "Engineer cannot complete task: Ensure the task status was advanced from ASSIGNED -> ACKNOWLEDGED -> IN_PROGRESS."
        ],
        "troubleshooting": [
            {
                "problem": "Engineer sees team notice but no incident in My Work",
                "possible_causes": "The engineer received the Level 1 Group Notice, but another teammate was selected for the Level 2 Personal Assignment.",
                "what_to_check": "Inspect Admin > Assignments to see who holds the active personal assignment for that incident.",
                "expected_behavior": "Only the selected employee receives the personal assignment in My Work.",
                "resolution": "Inform the engineer that group notices are informational for team awareness.",
                "escalation": "None needed; this is expected behavior."
            }
        ],
        "faqs": [
            {
                "question": "Why did my teammate receive the incident instead of me?",
                "answer": "IncidentFlow uses sequential deterministic rotation across scheduled shift members. When work arrives, the next eligible member in rotation receives it."
            }
        ],
        "summary_bullets": [
            "Personal workbench for assigned incidents.",
            "Strict lifecycle: ASSIGNED -> ACKNOWLEDGED -> IN_PROGRESS -> COMPLETED.",
            "Permanent completion audit and workload release.",
            "Single-owner ownership distinct from group notices."
        ],
        "keywords": ["my work", "task", "lifecycle", "acknowledge", "start work", "complete"],
        "related_features": ["incidents", "team_notice", "automatic_assignment"],
        "contextual_hint": "Shows active work items assigned personally to the logged-in engineer."
    },
    {
        "id": "notifications",
        "feature_key": "notifications",
        "slug": "notifications-system",
        "title": "Notifications & Alerts",
        "category_id": "core_operations",
        "category_name": "Core Operations",
        "summary": "Dual-level notification engine delivering real-time in-app alerts, team notices, and SMTP emails.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Manages communication dispatch for all operational events. Distinguishes between Level 1 Group Notices (broadcast to all 10 team members) and Level 2 Personal Assignments (targeted exclusively to the assigned engineer). Also dispatches system notifications and optional SMTP emails.",
        "how_it_works": [
            "When an incident arrives, Group Notice is broadcast over WebSockets to all 10 members of the group.",
            "When the assignment engine selects the individual engineer, an individual notification is created.",
            "In-app notifications feature unread counters, mark-as-read, and deep links to the target incident.",
            "If SMTP is configured, high-priority notifications trigger background email delivery with STARTTLS."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR", "EMPLOYEE"],
        "who_can_use_it_description": "All users receive notifications; Admins configure notification templates and SMTP settings.",
        "important_rules": [
            "Level 1 Group Notices must NEVER be mistaken for individual ownership.",
            "If SMTP fails or is not configured, in-app notifications and WebSockets still function flawlessly.",
            "System will never mark an email as 'delivered' unless SMTP server explicitly returns a 250 acceptance code."
        ],
        "common_problems": [
            "Unread badge count not clearing: Click 'Mark all as read' in /employee/notifications."
        ],
        "troubleshooting": [
            {
                "problem": "Emails not arriving in inbox",
                "possible_causes": "SMTP server not configured, invalid App Password, or firewall blocking port 587.",
                "what_to_check": "Navigate to Admin > Settings > SMTP Configuration and run 'Send Test Email'.",
                "expected_behavior": "Shows CONFIG_ERROR or specific SMTP handshake error details if misconfigured.",
                "resolution": "Enter valid SMTP credentials and verify port and STARTTLS settings.",
                "escalation": "Consult corporate mail server administrators for relay permissions."
            }
        ],
        "faqs": [
            {
                "question": "Do all 10 members get an email for every incident?",
                "answer": "No. In-app notices go to all 10 members. Email notifications are prioritized for the personal assignee to avoid inbox spam."
            }
        ],
        "summary_bullets": [
            "Dual-level alerts: Team Notice vs Personal Assignment.",
            "Real-time delivery over WebSockets with unread badges.",
            "Strict verification: no false email delivery claims.",
            "Configurable in Admin Settings."
        ],
        "keywords": ["notifications", "email", "smtp", "alerts", "in-app", "group notice"],
        "related_features": ["team_notice", "email_smtp", "my_work"],
        "contextual_hint": "Real-time dispatch system for group announcements and personal assignment alerts."
    },

    # -----------------------------------------------------------------------
    # 2. PEOPLE & TEAMS
    # -----------------------------------------------------------------------
    {
        "id": "employees",
        "feature_key": "employees",
        "slug": "employee-management",
        "title": "Employee Management & 10-Member Teams",
        "category_id": "people_and_teams",
        "category_name": "People & Teams",
        "summary": "Workforce management enforcing compulsory scheduled shifts, canonical Employee IDs, and the 10-employee team invariant.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Allows Admins to manage operational engineers. Every employee belongs to a team, has a globally unique Employee ID (e.g. DB001), holds an active shift schedule, and possesses assigned skill proficiencies.",
        "how_it_works": [
            "Admin creates or edits employee records with Name, Canonical Employee ID, Team, and Skills.",
            "The system checks that Employee ID is globally unique in the database (UNIQUE constraint).",
            "Employees are never deactivated during normal operations to remove them from assignment. Historical assignment records remain permanent.",
            "Every active team must have EXACTLY 10 active employees for the team to be in ACTIVE operational status."
        ],
        "who_can_use_it": ["ADMIN", "GROUP_LEADER"],
        "who_can_use_it_description": "Administrators. Group Leaders can view team members but cannot delete or reassign them.",
        "important_rules": [
            "Every active team MUST have exactly 10 permanent active employees. Teams with 9 or 11 members cannot be activated.",
            "Employee ID (e.g. DB001, MDM001) is the canonical identifier; email is not used as primary key.",
            "Employees are not removed from assignment because of availability or presence; schedule drives assignment.",
            "Historical assignment and audit records for an employee are permanent and cannot be deleted."
        ],
        "common_problems": [
            "Attempting to activate a team with 9 or 11 employees fails with TEAM_ACTIVATION_BLOCKED.",
            "Attempting to create an employee with an existing Employee ID fails with DUPLICATE_EMPLOYEE_ID."
        ],
        "troubleshooting": [
            {
                "problem": "Team activation blocked with 9 or 11 employees",
                "possible_causes": "Team roster violates the 10-member hard business invariant.",
                "what_to_check": "Navigate to Admin > Teams > [Target Team] and inspect member count.",
                "expected_behavior": "Activation endpoint rejects with HTTP 400 listing violation.",
                "resolution": "Add or remove draft members so the active team contains exactly 10 members.",
                "escalation": "Align staffing roster with team lead before activating."
            }
        ],
        "faqs": [
            {
                "question": "Why must every team have exactly 10 employees?",
                "answer": "IncidentFlow's enterprise operating model requires standard 10-member rosters to guarantee 24/7 3-shift coverage with deterministic rotation and zero single points of failure."
            }
        ],
        "summary_bullets": [
            "Hard invariant: Exactly 10 active employees per active team.",
            "Globally unique Employee IDs (e.g. DB001..DB010).",
            "Compulsory shift schedule for every active member.",
            "Permanent historical records: no silent deletions."
        ],
        "keywords": ["employees", "10 employees", "employee id", "roster", "staffing", "activation"],
        "related_features": ["teams", "group_leader", "shifts", "employee_ids"],
        "contextual_hint": "Manage engineer profiles, canonical IDs, and verify the 10-employee team invariant."
    },
    {
        "id": "teams",
        "feature_key": "teams",
        "slug": "team-management",
        "title": "Team Management & Activation Invariants",
        "category_id": "people_and_teams",
        "category_name": "People & Teams",
        "summary": "Team configuration, ServiceNow group mapping, work domains, and strict 10-member activation validation.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Allows Admins to configure operational teams (e.g. Database L2, MDM L3, Linux L2). Teams map directly to ServiceNow assignment groups and represent the domain boundary for automated incident dispatch.",
        "how_it_works": [
            "Admins create a team with Name, Work Domain, Description, and ServiceNow Group ID.",
            "A newly created team starts in DRAFT status, allowing flexible member configuration.",
            "To transition to ACTIVE status, the team must pass strict validation via TeamService.validate_team_activation.",
            "Validation checks: Exactly 10 active employees, exactly 1 active Group Leader, 100% active shift coverage, and valid configuration."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators only.",
        "important_rules": [
            "Active teams must strictly fulfill: 10 active members + 1 Group Leader + 100% shift coverage.",
            "Draft teams can have fewer or more than 10 employees for configuration staging.",
            "Deactivating a team returns it to DRAFT, pausing automated incident routing to that team."
        ],
        "common_problems": [
            "Team activation blocked: Review the violations list returned by the server."
        ],
        "troubleshooting": [
            {
                "problem": "Team cannot be activated (HTTP 400 TEAM_ACTIVATION_BLOCKED)",
                "possible_causes": "Member count not 10, no Group Leader designated, or member has no shift assignment.",
                "what_to_check": "Check Admin > Groups > [Team] > Validation tab for specific unmet criteria.",
                "expected_behavior": "Returns detailed JSON array of blocking reasons.",
                "resolution": "Resolve all listed violations: assign exactly 1 leader, adjust roster to 10, assign shifts.",
                "escalation": "Contact Admin supervisor if shift patterns need restructuring."
            }
        ],
        "faqs": [
            {
                "question": "Can an active team have two Group Leaders?",
                "answer": "No. Exactly one active Group Leader is allowed per team. Designating a new leader automatically demotes the previous leader."
            }
        ],
        "summary_bullets": [
            "Represents operational assignment groups mapped to ServiceNow.",
            "Two states: DRAFT (staging) and ACTIVE (production operational).",
            "Mandatory 4-point validation gate for activation.",
            "Guarantees 24/7 shift coverage across all members."
        ],
        "keywords": ["teams", "groups", "activation", "servicenow group", "work domain", "validation"],
        "related_features": ["employees", "group_leader", "shifts"],
        "contextual_hint": "Configure operational groups and validate mandatory 10-member production readiness."
    },
    {
        "id": "group_leader",
        "feature_key": "group_leader",
        "slug": "group-leader-governance",
        "title": "Group Leader Roles & Permissions",
        "category_id": "people_and_teams",
        "category_name": "People & Teams",
        "summary": "Designation, responsibilities, and elevated server-side privileges for the single active team leader.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Designates the operational leader for each team. The Group Leader serves as the primary liaison between executive management and frontline engineers, possessing exclusive communication channels with Admins and team moderation privileges.",
        "how_it_works": [
            "Admin designates an employee as Group Leader in Admin > Employees or Admin > Groups.",
            "Enforces server-side invariant: Exactly ONE active Group Leader per team.",
            "Promoting a new leader automatically steps down the existing leader with full audit logging.",
            "Group Leaders receive access to private Admin ↔ Group Leader chat and moderation controls in team channels."
        ],
        "who_can_use_it": ["ADMIN", "GROUP_LEADER"],
        "who_can_use_it_description": "Admin designates leaders; designated employees gain Group Leader capabilities.",
        "important_rules": [
            "Only ONE active Group Leader per team at any time.",
            "Permissions are strictly validated server-side, not just in UI.",
            "Former leaders cleanly lose elevated permissions upon transition."
        ],
        "common_problems": [
            "Employee claims leader permissions but cannot access Admin chat: Verify is_group_leader=True on their employee record."
        ],
        "troubleshooting": [
            {
                "problem": "Cannot designate second leader without demoting first",
                "possible_causes": "Server enforces single-leader invariant automatically.",
                "what_to_check": "Check audit log for CHANGE_GROUP_LEADER event.",
                "expected_behavior": "Designating member B automatically clears is_group_leader on member A.",
                "resolution": "Confirm the promotion in the UI; system handles demotion cleanly.",
                "escalation": "None needed."
            }
        ],
        "faqs": [
            {
                "question": "Does a Group Leader still receive incident assignments?",
                "answer": "Yes. Group Leaders are scheduled on shifts and participate in rotation like all team engineers."
            }
        ],
        "summary_bullets": [
            "Exactly one active Group Leader per team.",
            "Exclusive Admin ↔ Leader private direct chat channel.",
            "Team chat moderation privileges enforced server-side.",
            "Automatic demotion of predecessor with full audit trail."
        ],
        "keywords": ["group leader", "team lead", "moderation", "admin chat", "permissions"],
        "related_features": ["teams", "employees", "admin_leader_chat"],
        "contextual_hint": "Manage team leadership and elevated communication permissions."
    },
    {
        "id": "employee_ids",
        "feature_key": "employee_ids",
        "slug": "employee-id-standards",
        "title": "Canonical Employee IDs",
        "category_id": "people_and_teams",
        "category_name": "People & Teams",
        "summary": "Globally unique, deterministic employee identifiers (e.g. DB001..DB010) used for rotation and identity.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Establishes canonical alphanumeric identifiers for all engineers. Employee IDs serve as the immutable system identity across rotation logs, assignment history, ServiceNow staging, and audit trails.",
        "how_it_works": [
            "Standardized formatting: [PREFIX][NUMBER] (e.g. DB001 for Database L2, MDM001 for MDM L3, NET001 for Network L2).",
            "Database enforces UNIQUE constraint on employee_code.",
            "The rotation engine uses Employee ID as a deterministic tie-breaker (e.g. DB001 before DB002).",
            "Never uses email as primary identity in assignment engines."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR", "EMPLOYEE"],
        "who_can_use_it_description": "Administrators assign and view Employee IDs; all users see their assigned ID in Profile.",
        "important_rules": [
            "Employee IDs must be globally unique across all teams.",
            "Duplicate Employee ID creation is rejected at both API and database level.",
            "Employee IDs are permanent: historical assignments link directly to employee_id."
        ],
        "common_problems": [
            "Duplicate ID error when creating an employee: The specified code is already assigned."
        ],
        "troubleshooting": [
            {
                "problem": "Duplicate employee code error on creation (DUPLICATE_EMPLOYEE_ID)",
                "possible_causes": "Another employee in the organization already uses that code.",
                "what_to_check": "Search Admin > Employees for the target code.",
                "expected_behavior": "Rejects with HTTP 400.",
                "resolution": "Choose the next sequential code in the team series (e.g. DB007 instead of DB006).",
                "escalation": "Check employee directory to avoid colliding numbering."
            }
        ],
        "faqs": [
            {
                "question": "Can two employees on different teams have the same ID?",
                "answer": "No. Employee IDs are globally unique across the entire IncidentFlow instance."
            }
        ],
        "summary_bullets": [
            "Canonical globally unique identifiers (DB001..DB010).",
            "Enforced by database-level unique constraints.",
            "Deterministic tie-breaker in rotation algorithms.",
            "Permanent reference in audit logs and assignment history."
        ],
        "keywords": ["employee id", "employee code", "unique", "canonical identity", "identifier"],
        "related_features": ["employees", "assignment_rotation"],
        "contextual_hint": "Standardized unique identifiers for rotation and historical auditing."
    },

    # -----------------------------------------------------------------------
    # 3. SCHEDULING
    # -----------------------------------------------------------------------
    {
        "id": "shifts",
        "feature_key": "shifts",
        "slug": "shifts-and-scheduling",
        "title": "Shifts & Schedule Authority",
        "category_id": "scheduling",
        "category_name": "Scheduling",
        "summary": "Scheduled shift coverage as the sole assignment authority for distributing incoming incidents.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Defines 24/7 operational shifts and daily engineer schedules. In IncidentFlow's schedule-driven workforce model, an engineer's scheduled shift is the primary authority determining incident assignment eligibility.",
        "how_it_works": [
            "Shifts are configured with Start Time, End Time, and Timezone (Asia/Kolkata default).",
            "Supports 3 standard shifts: Morning (06:00–14:00), Evening (14:00–22:00), and Night (22:00–06:00 overnight).",
            "When an incident arrives, IncidentFlow checks the current timestamp in team timezone to determine the active shift.",
            "Only engineers scheduled on that active shift are eligible for assignment. Future/next shift engineers are excluded.",
            "Presence and availability are NOT assignment criteria; scheduled work equals assignment responsibility."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR", "EMPLOYEE"],
        "who_can_use_it_description": "Administrators configure shifts; employees view their personal shifts in My Shift.",
        "important_rules": [
            "Shift schedule is the assignment authority: DO NOT use availability status or presence to filter candidates.",
            "Overnight shifts (crossing midnight, e.g. 22:00–06:00) are fully supported using timezone-aware calculations.",
            "Every active employee must have an active shift assignment."
        ],
        "common_problems": [
            "Incident arriving at 00:30 not assigned: Ensure the night shift definition correctly crosses midnight."
        ],
        "troubleshooting": [
            {
                "problem": "Incident unassigned with NO_CURRENT_SCHEDULED_COVERAGE",
                "possible_causes": "Current arrival time falls in a gap between configured shifts or no active shift covers this hour.",
                "what_to_check": "Navigate to Admin > Shifts and verify that shift start and end times cover 24 hours without gaps.",
                "expected_behavior": "Incidents outside scheduled coverage are queued for next shift.",
                "resolution": "Adjust shift boundaries to ensure continuous 24/7 coverage.",
                "escalation": "Contact shift planning coordinator."
            }
        ],
        "faqs": [
            {
                "question": "What happens if an engineer on shift is marked OFFLINE?",
                "answer": "Under the authoritative schedule-driven model, scheduled engineers are eligible for work regardless of online/offline status."
            }
        ],
        "summary_bullets": [
            "Shift schedule is the sole assignment authority.",
            "Availability and presence are completely bypassed.",
            "Continuous 24/7 coverage with midnight-crossing support.",
            "Calculated in team timezone (Asia/Kolkata)."
        ],
        "keywords": ["shifts", "schedule", "coverage", "24/7", "timezone", "midnight"],
        "related_features": ["working_days", "automatic_assignment", "teams"],
        "contextual_hint": "Manage 24/7 shift definitions and schedule coverage across team members."
    },
    {
        "id": "working_days",
        "feature_key": "working_days",
        "slug": "working-days-and-sunday-holiday",
        "title": "Working Days & Sunday Holiday Policy",
        "category_id": "scheduling",
        "category_name": "Scheduling",
        "summary": "Mandatory working day schedule (Monday through Saturday) and default Sunday holiday queuing.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Defines operational working days for automated assignment. Monday through Saturday are active working days where incidents are automatically assigned. Sunday is the only default holiday where automatic assignment is paused.",
        "how_it_works": [
            "IncidentFlow inspects now.weekday() in the team's local timezone (0=Monday ... 5=Saturday, 6=Sunday).",
            "Monday through Saturday (days 0–5): Automated assignment executes normally.",
            "Saturday is explicitly a working day. The system will NEVER disable Saturday assignment.",
            "Sunday (day 6): Automated assignment is paused. Incoming incidents are transitioned to state 'QUEUED' with audit reason 'SUNDAY_HOLIDAY_QUEUED'.",
            "When Monday starts, queued work is evaluated and resumed."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR", "EMPLOYEE"],
        "who_can_use_it_description": "System enforces automatically; Admins can inspect queued work and holiday logs.",
        "important_rules": [
            "Saturday IS A WORKING DAY. Do NOT treat Saturday as a weekend holiday.",
            "Sunday IS THE ONLY DEFAULT HOLIDAY.",
            "Sunday incidents are never dropped or deleted; they are securely held in QUEUED state."
        ],
        "common_problems": [
            "Incidents not assigned on Sunday: This is expected business policy; work resumes on Monday."
        ],
        "troubleshooting": [
            {
                "problem": "Incident not assigned on Saturday",
                "possible_causes": "Misconfigured calendar or third-party weekend override.",
                "what_to_check": "Verify backend timestamp and ensure now.weekday() == 5 is processed as a working day.",
                "expected_behavior": "Saturday work is assigned normally.",
                "resolution": "Check system logs to verify shift coverage exists for Saturday.",
                "escalation": "Report to engineering if Saturday is incorrectly flagged as a holiday."
            }
        ],
        "faqs": [
            {
                "question": "Can an Admin manually assign an incident on Sunday?",
                "answer": "Yes. While automatic assignment is paused on Sunday, Admins can perform manual assignments if emergency intervention is required."
            }
        ],
        "summary_bullets": [
            "Monday to Saturday are active working days.",
            "Saturday is explicitly an operational working day.",
            "Sunday is the sole default holiday.",
            "Sunday work is securely held in QUEUED state."
        ],
        "keywords": ["working days", "saturday", "sunday", "holiday", "queued", "weekend"],
        "related_features": ["shifts", "automatic_assignment"],
        "contextual_hint": "Defines Mon-Sat operational working days and Sunday automated assignment pausing."
    },

    # -----------------------------------------------------------------------
    # 4. AUTOMATION
    # -----------------------------------------------------------------------
    {
        "id": "automatic_assignment",
        "feature_key": "automatic_assignment",
        "slug": "automatic-assignment-workflow",
        "title": "Automatic Assignment Engine",
        "category_id": "automation",
        "category_name": "Automation",
        "summary": "Authoritative end-to-end incident dispatch workflow driven by shifts, rotation, and assignment history deduplication.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "The Automatic Assignment Engine orchestrates work distribution when incidents arrive from ServiceNow. It resolves the target team, sends a team notice, identifies the active shift, filters out past handlers, and assigns the next eligible engineer deterministically.",
        "how_it_works": [
            "Step 1: Incident arrives from ServiceNow webhook or admin notice.",
            "Step 2: Engine resolves the target team (e.g. Database L2).",
            "Step 3: Dispatches Level 1 Team Notice to all 10 members for group visibility.",
            "Step 4: Sunday Check: If today is Sunday, marks incident QUEUED and halts.",
            "Step 5: Active Shift: Determines current shift covering arrival time in Asia/Kolkata.",
            "Step 6: Candidates: Retrieves engineers assigned to current shift.",
            "Step 7: Deduplication: Queries all historical assignments for this incident. Skips any engineer who has already handled it.",
            "Step 8: Cycle Completion: If all 10 team members have handled the incident, marks state ALL_TEAM_MEMBERS_ASSIGNED and halts.",
            "Step 9: Deterministic Selection: Picks the next engineer sorted by (active_workload ASC, employee_code ASC).",
            "Step 10: Assignment: Creates active assignment, sends Level 2 Personal Notice to assignee, updates My Work, and logs full audit trail."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR"],
        "who_can_use_it_description": "Automated system; configured and monitored by Admins.",
        "important_rules": [
            "PRESENCE AND AVAILABILITY ARE NOT CRITERIA. Do NOT filter by is_present, AVAILABLE, BUSY, or OFFLINE.",
            "Same incident is NEVER assigned to the same engineer twice in the same cycle.",
            "Exactly ONE engineer receives personal task ownership in My Work.",
            "When all 10 members have handled it, cycle terminates as ALL_TEAM_MEMBERS_ASSIGNED."
        ],
        "common_problems": [
            "Incident not assigned: Check if incident arrived on Sunday or all 10 members already handled it."
        ],
        "troubleshooting": [
            {
                "problem": "Incident state is ALL_TEAM_MEMBERS_ASSIGNED",
                "possible_causes": "Every one of the 10 team members has already received and completed this incident.",
                "what_to_check": "Inspect Admin > Assignments filter by incident_id to see all 10 historical records.",
                "expected_behavior": "Prevents infinite loops by stopping assignment when all members have handled it.",
                "resolution": "If re-work is necessary, Admin can manually reassign or trigger a new incident cycle.",
                "escalation": "Review incident recurrence root cause with team leader."
            }
        ],
        "faqs": [
            {
                "question": "Does the engine use random selection?",
                "answer": "No. IncidentFlow never uses random assignment or Math.random(). Selection is strictly deterministic based on shift, workload, and canonical employee codes."
            }
        ],
        "summary_bullets": [
            "Schedule-driven assignment authority.",
            "No availability or presence gating.",
            "Per-incident assignment history deduplication.",
            "Terminates as ALL_TEAM_MEMBERS_ASSIGNED when cycle completes."
        ],
        "keywords": ["automatic assignment", "engine", "workflow", "rotation", "deduplication", "all team members assigned"],
        "related_features": ["team_notice", "assignment_rotation", "my_work", "audit_logs"],
        "contextual_hint": "Core assignment pipeline distributing work deterministically across scheduled shift engineers."
    },
    {
        "id": "team_notice",
        "feature_key": "team_notice",
        "slug": "team-notice-vs-personal-assignment",
        "title": "Team Notice vs. Personal Assignment",
        "category_id": "automation",
        "category_name": "Automation",
        "summary": "Critical architectural distinction between Level 1 informational team broadcasts and Level 2 individual task ownership.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Separates group situational awareness from operational work ownership. Every incoming incident generates two distinct communication levels: Level 1 broadcast to the entire team, and Level 2 targeted assignment to the selected individual.",
        "how_it_works": [
            "LEVEL 1 — TEAM NOTICE: Dispatched to ALL 10 TEAM MEMBERS simultaneously. Message: 'Your team has been assigned incident INC0012345.' Includes short description, priority, and assignment group. Purely informational.",
            "LEVEL 2 — PERSONAL ASSIGNMENT: Dispatched exclusively to the single selected engineer. Message: 'You have been assigned incident INC0012345.' Creates the work record in My Work.",
            "Teammates see the incident notice in their team activity feed, but do NOT receive task ownership."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR", "EMPLOYEE"],
        "who_can_use_it_description": "All 10 members receive Team Notices; only the assigned engineer gets the Personal Assignment.",
        "important_rules": [
            "Team Notice DOES NOT equal work assignment.",
            "Exactly ONE engineer owns the work item at any given time.",
            "Enforced at database level by unique partial index uq_active_incident_assignment."
        ],
        "common_problems": [
            "Team members confused about who works on the incident: Remind engineers to check 'My Work'."
        ],
        "troubleshooting": [
            {
                "problem": "Multiple engineers think they need to work on the same incident",
                "possible_causes": "Engineers reading the Level 1 Group Notice as an individual call to action.",
                "what_to_check": "Instruct engineers to check My Work (/employee/work).",
                "expected_behavior": "Only the selected assignee has an active task card.",
                "resolution": "Clarify that group notices are informational for team awareness.",
                "escalation": "Group Leader can clarify assignment in Team Chat."
            }
        ],
        "faqs": [
            {
                "question": "Can two engineers be assigned to the same incident simultaneously?",
                "answer": "No. The database enforces a unique constraint allowing only one active assignment per incident."
            }
        ],
        "summary_bullets": [
            "Level 1: Team Notice broadcast to all 10 members.",
            "Level 2: Personal Assignment targeted to 1 engineer.",
            "Only the personal assignee receives task card in My Work.",
            "Guaranteed single-ownership invariant."
        ],
        "keywords": ["team notice", "group notice", "personal assignment", "ownership", "single owner"],
        "related_features": ["automatic_assignment", "my_work", "notifications"],
        "contextual_hint": "Explains the difference between team-wide awareness notices and single-owner work assignments."
    },
    {
        "id": "assignment_rotation",
        "feature_key": "assignment_rotation",
        "slug": "assignment-rotation-and-history",
        "title": "Assignment Rotation & Incident History",
        "category_id": "automation",
        "category_name": "Automation",
        "summary": "Sequential work rotation across team members and permanent per-incident history deduplication.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Ensures equitable, sequential work distribution across all 10 engineers while preventing repeated work from returning to the same individual during the same cycle.",
        "how_it_works": [
            "Rotation order: DB001 -> DB002 -> DB003 -> ... -> DB010.",
            "When incident INC001 arrives, it goes to DB001.",
            "If another notice or retry for INC001 arrives, DB001 is skipped because they are in the incident's assignment history.",
            "The repeated INC001 is assigned to DB002.",
            "If a NEW incident INC002 arrives, DB001 is eligible for it (provided DB001 completed INC001 and has low workload).",
            "Next-day rule: If INC001 arrives again tomorrow, DB001 and DB002 remain in history and are skipped; DB003 is selected."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR"],
        "who_can_use_it_description": "Automated engine; Admins monitor rotation progression in Admin > Assignments.",
        "important_rules": [
            "Assignment history is PERMANENT. Completing an incident does NOT delete historical records.",
            "An engineer who handled an incident is NEVER assigned it again in that cycle.",
            "Fair workload distribution: engineers with lower active workload are prioritized.",
            "Deterministic tie-breaker: canonical Employee ID (e.g. DB001 before DB002)."
        ],
        "common_problems": [
            "Engineer receives multiple incidents: Only if they are distinct incidents; same incident is never duplicated."
        ],
        "troubleshooting": [
            {
                "problem": "Engineer was assigned twice for the same incident",
                "possible_causes": "Severe regression or manual database tampering.",
                "what_to_check": "Query SELECT employee_id, COUNT(*) FROM incident_assignments WHERE incident_id = ? GROUP BY employee_id.",
                "expected_behavior": "Each employee_id appears at most once per incident in normal automated cycles.",
                "resolution": "Check audit log to see if an Admin manually reassigned the work.",
                "escalation": "Escalate to backend engineering if automated engine assigned duplicate."
            }
        ],
        "faqs": [
            {
                "question": "What happens when all 10 employees have handled the incident?",
                "answer": "The cycle completes. IncidentFlow marks the incident state as ALL_TEAM_MEMBERS_ASSIGNED and stops further automated rotation."
            }
        ],
        "summary_bullets": [
            "Sequential rotation (DB001..DB010).",
            "Permanent incident assignment history.",
            "No duplicate employee assignment per incident.",
            "Next-day persistence of historical handlers."
        ],
        "keywords": ["rotation", "history", "deduplication", "sequential", "fair distribution"],
        "related_features": ["automatic_assignment", "employee_ids", "incidents"],
        "contextual_hint": "Detailed mechanics of sequential team rotation and per-incident historical deduplication."
    },

    # -----------------------------------------------------------------------
    # 5. SERVICENOW
    # -----------------------------------------------------------------------
    {
        "id": "servicenow_integration",
        "feature_key": "servicenow_integration",
        "slug": "servicenow-integration",
        "title": "ServiceNow Integration & Staging",
        "category_id": "servicenow",
        "category_name": "ServiceNow",
        "summary": "ServiceNow webhook ingestion, sys_id mapping, bi-directional sync, and credentials protection.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Connects IncidentFlow to corporate ServiceNow instances. Ingests incident webhooks, maps field attributes (sys_id, incident_number, assignment_group, short_description, priority), and synchronizes assignment outcomes back to ServiceNow.",
        "how_it_works": [
            "ServiceNow sends an HTTP POST webhook to /api/integrations/servicenow/webhook.",
            "IncidentFlow verifies the optional webhook secret signature.",
            "The incident is ingested into the local staging database with servicenow_sys_id as unique constraint.",
            "If the same webhook arrives multiple times (network retry), IncidentFlow detects the existing record idempotently.",
            "In LIVE mode, once assigned, IncidentFlow makes a PATCH request to ServiceNow to update assigned_to and work_notes."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators configure credentials in Admin > Integrations.",
        "important_rules": [
            "Actual ServiceNow credentials must NEVER be shared in chat or exposed to non-admin users.",
            "ServiceNow is always the source of truth for incident records.",
            "In SHADOW or DRY_RUN mode, ServiceNow mutations are strictly ZERO."
        ],
        "common_problems": [
            "Webhook rejected: Check if webhook secret matches in Admin > Integrations.",
            "Incident not syncing: Check if ServiceNow mock mode is enabled for staging testing."
        ],
        "troubleshooting": [
            {
                "problem": "ServiceNow webhook returns HTTP 401 Unauthorized",
                "possible_causes": "Webhook secret mismatch or missing Authorization / X-ServiceNow-Signature header.",
                "what_to_check": "Inspect Admin > Integrations > ServiceNow settings and verify webhook secret.",
                "expected_behavior": "Returns HTTP 200 with {status: 'processed', incident_number: 'INC...'} on success.",
                "resolution": "Update ServiceNow Business Rule / Outbound REST message with the correct secret.",
                "escalation": "Contact ServiceNow platform administrator."
            }
        ],
        "faqs": [
            {
                "question": "Can IncidentFlow run without a live ServiceNow instance?",
                "answer": "Yes. SERVICENOW_MOCK=True enables mock mode where simulated incidents and responses allow 100% feature testing."
            }
        ],
        "summary_bullets": [
            "Authoritative incident source of truth.",
            "Webhook ingestion with cryptographic signature validation.",
            "Idempotent processing using servicenow_sys_id.",
            "Protected credentials and mock mode support."
        ],
        "keywords": ["servicenow", "webhook", "sys_id", "integration", "sync", "credentials"],
        "related_features": ["shadow_mode", "live_mode", "incidents"],
        "contextual_hint": "Configure and test bi-directional ServiceNow webhook ingestion and field mapping."
    },
    {
        "id": "shadow_mode",
        "feature_key": "shadow_mode",
        "slug": "shadow-mode",
        "title": "Shadow Mode (Zero Mutation Staging)",
        "category_id": "servicenow",
        "category_name": "ServiceNow",
        "summary": "Safe automation evaluation mode executing full assignment logic with strictly ZERO ServiceNow mutations.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Enables safe observation and testing of the automated assignment engine against real production workloads without altering external ServiceNow records. Evaluates shifts, rotation, and candidate ranking, logging the recommended assignment as an audit event.",
        "how_it_works": [
            "Set system automation mode to SHADOW (AUTOMATION_MODE=SHADOW).",
            "When incidents arrive, the engine evaluates candidates, checks history, and determines the winning engineer.",
            "A SHADOW_ASSIGN audit event is recorded with complete candidate ranking and workload dossier.",
            "Zero PATCH requests are sent to ServiceNow; external incident remains unmutated.",
            "Allows management to verify assignment accuracy before enabling LIVE assignment."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators configure in Admin > Live Pilot or Admin > Settings.",
        "important_rules": [
            "ServiceNow mutations in Shadow Mode are strictly ZERO.",
            "Engine evaluates identical business logic as LIVE mode.",
            "Full decision dossier is recorded in immutable audit logs."
        ],
        "common_problems": [
            "Admins expecting ServiceNow assigned_to to change: Switch to LIVE mode to enable actual mutation."
        ],
        "troubleshooting": [
            {
                "problem": "Cannot see shadow mode decisions",
                "possible_causes": "Filtering by wrong action in audit logs.",
                "what_to_check": "Navigate to Admin > Audit Logs and filter by action SHADOW_ASSIGN.",
                "expected_behavior": "Displays JSON dossier containing recommended candidate, workloads, and reason.",
                "resolution": "Select SHADOW_ASSIGN action in audit log filter dropdown.",
                "escalation": "Verify that automation mode is set to SHADOW in Settings."
            }
        ],
        "faqs": [
            {
                "question": "Why should we use Shadow Mode?",
                "answer": "Shadow Mode gives leadership 100% confidence in assignment decisions and rotation behavior before permitting live external changes."
            }
        ],
        "summary_bullets": [
            "Full assignment evaluation with 0 external mutations.",
            "Records candidate dossier in SHADOW_ASSIGN audit logs.",
            "Safe staging tool for operational readiness validation.",
            "Seamless one-click transition to LIVE mode."
        ],
        "keywords": ["shadow mode", "staging", "zero mutation", "simulation", "pilot"],
        "related_features": ["live_mode", "servicenow_integration", "audit_logs"],
        "contextual_hint": "Simulate and verify assignment decisions with zero external ServiceNow mutations."
    },
    {
        "id": "live_mode",
        "feature_key": "live_mode",
        "slug": "live-mode-activation",
        "title": "Live Mode & Controlled Pilot Protection",
        "category_id": "servicenow",
        "category_name": "ServiceNow",
        "summary": "Controlled live automation updating ServiceNow with mandatory safety guards and explicit confirmation phrases.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Activates live automated incident assignment with real ServiceNow field mutations. LIVE mode includes enterprise safety controls: controlled pilot group isolation, maximum active assignment caps, approved employee roster whitelisting, and two-man rule confirmation.",
        "how_it_works": [
            "Admin navigates to Admin > Live Pilot.",
            "Activating LIVE mode requires entering the exact safety confirmation phrase: 'ENABLE LIVE ASSIGNMENT'.",
            "Pilot controls allow restricting automation to a single pilot group (e.g. Analytics – MDM L3).",
            "Enforces max_active_assignments threshold (e.g. max 5 concurrent active assignments).",
            "Creates an audit event CHANGE_AUTOMATION_MODE with the Admin user's identity."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators with confirmed master password authorization.",
        "important_rules": [
            "LIVE mode is NEVER enabled by default.",
            "Requires exact phrase: 'ENABLE LIVE ASSIGNMENT'.",
            "Protected by pilot group isolation and capacity limit guards.",
            "Every state transition is permanently logged in audit logs."
        ],
        "common_problems": [
            "Activation rejected: Ensure the phrase 'ENABLE LIVE ASSIGNMENT' is entered in exact uppercase."
        ],
        "troubleshooting": [
            {
                "problem": "Incidents skipped with reason PILOT_CAPACITY_REACHED",
                "possible_causes": "Active assignments count has reached the configured pilot threshold.",
                "what_to_check": "Check Admin > Live Pilot for Current Active count vs Max Active limit.",
                "expected_behavior": "Protects against runaway assignment volume during pilot.",
                "resolution": "Engineers complete active tasks, or Admin increases max_active_assignments limit.",
                "escalation": "Adjust pilot configuration in Admin > Live Pilot."
            }
        ],
        "faqs": [
            {
                "question": "Can we instantly pause LIVE automation if an issue occurs?",
                "answer": "Yes. Clicking 'Emergency Pause' instantly stops all automated assignment, reverting state to PAUSED with zero delay."
            }
        ],
        "summary_bullets": [
            "Real ServiceNow field mutations (assigned_to, work_notes).",
            "Protected by exact confirmation phrase 'ENABLE LIVE ASSIGNMENT'.",
            "Controlled pilot group and roster isolation.",
            "Capacity threshold guards and emergency pause."
        ],
        "keywords": ["live mode", "live pilot", "servicenow mutation", "safety guard", "capacity limit"],
        "related_features": ["shadow_mode", "servicenow_integration", "audit_logs"],
        "contextual_hint": "Manage live automated assignments with capacity limits and pilot group isolation."
    },

    # -----------------------------------------------------------------------
    # 6. COMMUNICATION
    # -----------------------------------------------------------------------
    {
        "id": "chat_system",
        "feature_key": "chat_system",
        "slug": "chat-system-architecture",
        "title": "Enterprise Chat & Collaboration",
        "category_id": "communication",
        "category_name": "Communication",
        "summary": "Real-time communication channels including Team Chat, Direct Chat, Incident Threads, reactions, and media.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Provides a comprehensive real-time chat architecture for operations. Supports Team Chat (for all 10 members), Direct Chat (1-on-1 engineer messaging), Incident Chat (discussions scoped to a specific ticket), and rich interactions including replies, reactions, image attachments, and audio voice notes.",
        "how_it_works": [
            "Chat channels use WebSocket events for sub-50ms message delivery and typing indicators.",
            "Images and audio notes are validated for mime-type and stored securely on the backend filesystem.",
            "Supports emoji reactions (👍, ❤️, 🚀, 👀) with optimistic UI updates.",
            "Includes message editing, deletion, and full-text conversation search."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR", "EMPLOYEE"],
        "who_can_use_it_description": "All authenticated employees, leaders, and admins.",
        "important_rules": [
            "Chat authorization strictly respects team boundaries: engineers cannot view or post in other teams' private chats.",
            "Uploaded media must not exceed file size limits (5MB for images, 10MB for audio).",
            "Never paste unencrypted API keys or production database passwords in chat."
        ],
        "common_problems": [
            "Messages showing red retry button: WebSocket connection dropped temporarily."
        ],
        "troubleshooting": [
            {
                "problem": "Chat messages failing to send or stuck in pending state",
                "possible_causes": "WebSocket connection disconnected or auth token expired.",
                "what_to_check": "Look at the header connection badge (Connected vs Offline).",
                "expected_behavior": "WebSocket auto-reconnects with exponential backoff.",
                "resolution": "Click the retry button on the failed message once reconnected.",
                "escalation": "Check backend WebSocket endpoint logs."
            }
        ],
        "faqs": [
            {
                "question": "Can an employee delete another person's message?",
                "answer": "No. Ordinary users can only edit or delete their own messages. Group Leaders and Admins have moderation privileges."
            }
        ],
        "summary_bullets": [
            "Real-time team, direct, and incident-scoped chat.",
            "Emoji reactions, threaded replies, and read receipts.",
            "Secure image and audio voice note uploads.",
            "Strict team-boundary authorization enforcement."
        ],
        "keywords": ["chat", "team chat", "direct chat", "reactions", "voice notes", "images"],
        "related_features": ["admin_leader_chat", "notifications"],
        "contextual_hint": "Real-time messaging platform supporting team, direct, and incident discussions."
    },
    {
        "id": "admin_leader_chat",
        "feature_key": "admin_leader_chat",
        "slug": "admin-group-leader-private-chat",
        "title": "Admin ↔ Group Leader Private Channels",
        "category_id": "communication",
        "category_name": "Communication",
        "summary": "Confidential communication pipeline connecting executive Administrators directly with active Group Leaders.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Provides an exclusive, private communication channel between Administrators and designated Group Leaders. Allows confidential discussions regarding team capacity, operational escalations, shift scheduling adjustments, and performance reviews.",
        "how_it_works": [
            "Server validates that conversation participants consist strictly of users with ADMIN or SUPERVISOR role, or an active is_group_leader=True employee.",
            "Ordinary team engineers are strictly blocked from discovering or joining these private channels (HTTP 403 / 404).",
            "If a Group Leader steps down, their access to the channel is automatically revoked, while historical logs remain secure."
        ],
        "who_can_use_it": ["ADMIN", "GROUP_LEADER"],
        "who_can_use_it_description": "Administrators and designated Group Leaders only.",
        "important_rules": [
            "Confidential channel: non-leaders cannot view or participate.",
            "Server-side authorization enforced on every REST and WebSocket event.",
            "Immutable audit log records all participant membership changes."
        ],
        "common_problems": [
            "Former leader tries to access channel: Access is revoked immediately upon replacement."
        ],
        "troubleshooting": [
            {
                "problem": "Group Leader receives HTTP 403 when opening Admin Chat",
                "possible_causes": "The employee is not currently marked as is_group_leader=True in the database.",
                "what_to_check": "Inspect Admin > Groups > [Team] and verify who holds the active leader badge.",
                "expected_behavior": "Only the single active leader and Admins can access.",
                "resolution": "Admin re-designates the user as Group Leader in Admin > Employees.",
                "escalation": "Verify role assignment in user table."
            }
        ],
        "faqs": [
            {
                "question": "Can an ordinary engineer see that an Admin-Leader chat exists?",
                "answer": "No. The channel is completely hidden from non-leader roster queries."
            }
        ],
        "summary_bullets": [
            "Exclusive private channel for Admins and Group Leaders.",
            "Server-side RBAC protection on all messages.",
            "Automatic access revocation upon leadership transition.",
            "Designed for operational escalations and roster adjustments."
        ],
        "keywords": ["admin chat", "group leader", "private channel", "confidential", "escalation"],
        "related_features": ["group_leader", "chat_system"],
        "contextual_hint": "Confidential messaging pipeline between system Admins and team Group Leaders."
    },

    # -----------------------------------------------------------------------
    # 7. ADMINISTRATION
    # -----------------------------------------------------------------------
    {
        "id": "task_catalog",
        "feature_key": "task_catalog",
        "slug": "admin-managed-task-catalog",
        "title": "Admin-Managed Task Catalog & Precedence",
        "category_id": "administration",
        "category_name": "Administration",
        "summary": "Team-specific remediation task templates and strict ServiceNow work instruction precedence rules.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Provides standard operating procedures (SOP) and step-by-step task instructions for engineers. When an incident is assigned, IncidentFlow resolves the required task instructions to display in the engineer's 'YOUR TASK' panel.",
        "how_it_works": [
            "Admins create task templates specific to each team (e.g. 'Investigate database connectivity', 'Analyze packet-loss alert').",
            "Each template has a Title, Detailed SOP Description, Priority, and Active status.",
            "PRECEDENCE RULE 1: If the incoming ServiceNow incident provides explicit work instructions (in work_instructions or work_notes), those ServiceNow instructions take absolute precedence.",
            "PRECEDENCE RULE 2: If ServiceNow does NOT provide explicit instructions, IncidentFlow selects the matching task template from the target team's Admin-managed Task Catalog.",
            "A snapshot of the resolved task instruction is stored on the assignment record to preserve historical reproducibility."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR", "EMPLOYEE"],
        "who_can_use_it_description": "Administrators configure templates in Admin > Settings; engineers execute tasks in My Work.",
        "important_rules": [
            "ServiceNow explicit work instructions ALWAYS take precedence over local templates.",
            "If ServiceNow instructions are absent, the team's catalog template is used.",
            "Task snapshots are permanently stored: editing a catalog template does NOT alter completed historical assignments."
        ],
        "common_problems": [
            "Engineer asks why instructions differ from catalog: Check if ServiceNow provided custom work instructions."
        ],
        "troubleshooting": [
            {
                "problem": "Incident displays generic instructions instead of team template",
                "possible_causes": "No active task template exists for that team or ServiceNow work instructions field was empty.",
                "what_to_check": "Navigate to Admin > Settings > Task Catalog and verify active templates for that team.",
                "expected_behavior": "Falls back to team template when ServiceNow instructions are absent.",
                "resolution": "Create or activate relevant task templates for the target group.",
                "escalation": "Align standard operational procedures with domain lead."
            }
        ],
        "faqs": [
            {
                "question": "Can each team have its own unique tasks?",
                "answer": "Yes. Task templates are strictly scoped to individual teams to reflect their specialized operational domain."
            }
        ],
        "summary_bullets": [
            "Team-specific SOP task templates.",
            "Strict Precedence: ServiceNow instructions override catalog.",
            "Immutable task snapshots for historical integrity.",
            "Configurable in Admin Settings."
        ],
        "keywords": ["task catalog", "sop", "work instructions", "precedence", "templates"],
        "related_features": ["my_work", "incidents", "servicenow_integration"],
        "contextual_hint": "Manage operational SOP task templates and verify ServiceNow instruction precedence."
    },
    {
        "id": "global_search",
        "feature_key": "global_search",
        "slug": "global-present-page-search",
        "title": "Global Search & Command Palette",
        "category_id": "administration",
        "category_name": "Administration",
        "summary": "Persistent, multi-category global search bar and Cmd+K command palette across all authenticated pages.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Empowers users to rapidly locate any operational resource across IncidentFlow. Integrates present-page filtering with full-database global search covering Incidents, Employees, Teams, Assignments, Tasks, Notifications, authorized Chat, and Admin Help Documentation.",
        "how_it_works": [
            "Fixed sticky search bar in the top application header on every authenticated page.",
            "Keyboard shortcut: Cmd + K on macOS, Ctrl + K on Windows/Linux opens the Command Palette.",
            "Current-page search highlights matching rows and items on the active screen.",
            "Full global search executes authorized database queries, returning categorized results with match highlighting.",
            "For Admins and Supervisors, searching terms like 'shift rotation' or 'ServiceNow webhook' returns direct links to Help articles.",
            "Strict authorization: search results never expose cross-team or privileged data to unauthorized users."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR", "EMPLOYEE"],
        "who_can_use_it_description": "All authenticated users; results are strictly scoped to the user's role and team permissions.",
        "important_rules": [
            "Search NEVER bypasses database authorization filters.",
            "Shortcut Cmd + K opens search palette; Escape closes overlay.",
            "Includes dedicated Help Documentation category for Admins."
        ],
        "common_problems": [
            "Cannot find employee on another team: Ordinary employees can only search members within their own team."
        ],
        "troubleshooting": [
            {
                "problem": "Global search returning empty results",
                "possible_causes": "Search query too specific or typing errors.",
                "what_to_check": "Try partial keywords (e.g. 'DB' instead of 'Database L2 Engineer 01').",
                "expected_behavior": "Performs case-insensitive wildcard pattern matching.",
                "resolution": "Use broader search terms or clear category filters.",
                "escalation": "Check /api/search backend logs."
            }
        ],
        "faqs": [
            {
                "question": "Does search index file attachments?",
                "answer": "Search indexes filenames and chat message descriptions, but not raw binary contents."
            }
        ],
        "summary_bullets": [
            "Persistent header search bar on all pages.",
            "Cmd + K / Ctrl + K command palette with category filters.",
            "Integrated Help Center article search for Admins.",
            "Strict server-side authorization enforcement."
        ],
        "keywords": ["global search", "command palette", "cmd k", "find", "search anything"],
        "related_features": ["admin_dashboard", "incidents", "employees"],
        "contextual_hint": "Unified search across all entities and help documentation via Cmd + K."
    },
    {
        "id": "email_smtp",
        "feature_key": "email_smtp",
        "slug": "email-and-smtp-configuration",
        "title": "Email & SMTP Configuration",
        "category_id": "administration",
        "category_name": "Administration",
        "summary": "Enterprise SMTP setup, STARTTLS security, App Password authentication, and delivery verification.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Configures email notification transport. Allows IncidentFlow to dispatch priority incident alerts and daily summaries to engineers via corporate SMTP relays or Gmail App Passwords.",
        "how_it_works": [
            "Configured in Admin > Settings: SMTP Host, Port (587 STARTTLS or 465 SSL), Username, Password, and Sender Email.",
            "Admin can trigger an instant 'Send Test Email' to verify handshake and relay acceptance.",
            "System enforces strict delivery telemetry: an email is NEVER marked as 'delivered' unless the SMTP server returns a 250 OK acceptance code.",
            "If SMTP is not configured, the system cleanly displays 'NOT CONFIGURED' and avoids attempting failing connections."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators only.",
        "important_rules": [
            "Passwords must be stored securely and never displayed in plain text in UI.",
            "System will never claim an email was delivered without successful SMTP acceptance.",
            "Missing SMTP configuration does NOT break in-app notifications or assignment."
        ],
        "common_problems": [
            "Test email fails: Verify Gmail App Password is used instead of regular Google account password."
        ],
        "troubleshooting": [
            {
                "problem": "SMTP Authentication Failure (535 5.7.8)",
                "possible_causes": "Invalid App Password or Two-Factor Authentication blocking basic auth.",
                "what_to_check": "Inspect Admin > Settings > SMTP Configuration.",
                "expected_behavior": "Returns specific SMTP error code and diagnostic guidance.",
                "resolution": "Generate a dedicated 16-character App Password in your email provider security settings.",
                "escalation": "Verify mail server relay permissions with IT security."
            }
        ],
        "faqs": [
            {
                "question": "Can we disable email alerts completely?",
                "answer": "Yes. Leaving SMTP settings unconfigured safely disables email dispatch while preserving 100% in-app functionality."
            }
        ],
        "summary_bullets": [
            "Enterprise SMTP transport with STARTTLS.",
            "Built-in 'Send Test Email' verification tool.",
            "Strict delivery telemetry: no false delivery claims.",
            "Clean degradation to in-app alerts if unconfigured."
        ],
        "keywords": ["email", "smtp", "starttls", "app password", "test email", "mail server"],
        "related_features": ["notifications", "diagnostics"],
        "contextual_hint": "Configure enterprise mail transport and verify SMTP connection health."
    },

    # -----------------------------------------------------------------------
    # 8. MONITORING
    # -----------------------------------------------------------------------
    {
        "id": "analytics",
        "feature_key": "analytics",
        "slug": "operational-analytics",
        "title": "Operational Analytics & Metrics",
        "category_id": "monitoring",
        "category_name": "Monitoring",
        "summary": "Deep operational intelligence tracking incident volume, mean time to resolution (MTTR), and workload distribution.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Provides statistical reports on organizational workload, team throughput, assignment fairness, and incident lifecycle duration. Helps management detect bottlenecks, optimize shift scheduling, and ensure equitable work distribution.",
        "how_it_works": [
            "Aggregates historical assignment records over selectable timeframes (Today, 7 Days, 30 Days, Custom Range).",
            "Calculates Mean Time to Acknowledge (MTTA) and Mean Time to Resolve (MTTR).",
            "Displays workload distribution charts confirming that rotation distributes tasks evenly across all 10 team members.",
            "All metric aggregations respect team timezone (Asia/Kolkata) boundaries."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR"],
        "who_can_use_it_description": "Administrators and Supervisors.",
        "important_rules": [
            "Analytics rely on permanent historical assignment timestamps (assigned_at, started_at, completed_at).",
            "Deleting historical data is prohibited to preserve reporting integrity."
        ],
        "common_problems": [
            "Charts showing unexpected flat lines: Check date range filters and timezone selection."
        ],
        "troubleshooting": [
            {
                "problem": "Analytics page showing loading spinner indefinitely",
                "possible_causes": "Heavy query on unindexed date range or database connection saturation.",
                "what_to_check": "Inspect browser console and /api/admin/analytics endpoint duration.",
                "expected_behavior": "Optimized aggregation queries return under 200ms.",
                "resolution": "Refresh page or select a narrower date range (e.g. Last 7 Days).",
                "escalation": "Ensure index ix_inc_assign_emp_active is active in database."
            }
        ],
        "faqs": [
            {
                "question": "Can analytics be exported to CSV or PDF?",
                "answer": "Yes. The Analytics dashboard provides export options for management reporting."
            }
        ],
        "summary_bullets": [
            "Tracks MTTA, MTTR, and incident throughput.",
            "Visualizes team workload distribution and rotation fairness.",
            "Timezone-aware date aggregation (Asia/Kolkata).",
            "Exportable executive reporting."
        ],
        "keywords": ["analytics", "metrics", "mttr", "mtta", "throughput", "workload distribution", "charts"],
        "related_features": ["admin_dashboard", "audit_logs"],
        "contextual_hint": "Inspect operational throughput, MTTR, and workload distribution metrics."
    },
    {
        "id": "audit_logs",
        "feature_key": "audit_logs",
        "slug": "immutable-audit-logs",
        "title": "Immutable Audit Logs & Governance",
        "category_id": "monitoring",
        "category_name": "Monitoring",
        "summary": "Cryptographically structured, immutable audit records capturing every operational decision, assignment, and state change.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Maintains an unalterable historical log of all administrative and automated actions. Records Who performed the action, What entity was changed, Exact timestamp, Before/After values, Decision reasons, and Automation modes.",
        "how_it_works": [
            "Every assignment, re-assignment, automation mode change, group leader promotion, or configuration edit calls AuditService.log().",
            "Stores actor_id, entity_type (INCIDENT, EMPLOYEE, TEAM, SETTING), action, old_value, new_value, and reason.",
            "Includes rich filter capabilities: by Actor, Action, Entity Type, Date Range, and Text search.",
            "Records detailed candidate dossiers during automated assignment (rotation position, previous handlers, workload counts)."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators and compliance auditors.",
        "important_rules": [
            "Audit records are STRICTLY IMMUTABLE. The system provides no delete or edit APIs for audit records.",
            "Every automated assignment decision must include an auditable explanation.",
            "Historical records must be retained for compliance and SLA verification."
        ],
        "common_problems": [
            "Audit log list empty: Clear active search filters or date range restrictions."
        ],
        "troubleshooting": [
            {
                "problem": "Cannot find decision reason for an automated assignment",
                "possible_causes": "Filtering by wrong entity or looking at manual assignment logs.",
                "what_to_check": "Filter by Action: AUTO_ASSIGN or AUTO_ASSIGNMENT_DECISION and search the incident number.",
                "expected_behavior": "Audit detail shows full candidate ranking and selection reason.",
                "resolution": "Expand the audit row to view the full JSON payload.",
                "escalation": "Verify audit_service logging in backend."
            }
        ],
        "faqs": [
            {
                "question": "Can an Admin clear or wipe the audit log?",
                "answer": "No. By enterprise security design, IncidentFlow does not implement or allow deletion of audit records."
            }
        ],
        "summary_bullets": [
            "Immutable audit trail of all operational events.",
            "Captures actor, timestamps, before/after diffs, and reasons.",
            "Records complete candidate dossiers for automated decisions.",
            "No deletion or tampering permitted."
        ],
        "keywords": ["audit", "audit logs", "compliance", "governance", "immutable", "history"],
        "related_features": ["automatic_assignment", "diagnostics", "security_rbac"],
        "contextual_hint": "Review immutable governance records of all system actions and decisions."
    },
    {
        "id": "diagnostics",
        "feature_key": "diagnostics",
        "slug": "system-diagnostics-and-health",
        "title": "System Diagnostics & Telemetry",
        "category_id": "monitoring",
        "category_name": "Monitoring",
        "summary": "Real-time infrastructure probes monitoring Database, Redis, WebSockets, ServiceNow, SMTP, and Workers.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Provides real-time health verification for all infrastructure components. Executes synthetic probes to determine whether subsystems are PASS, FAIL, BLOCKED, or NOT CONFIGURED.",
        "how_it_works": [
            "Database: Executes SELECT 1 probe and measures query round-trip latency.",
            "Redis / Celery: Checks broker connectivity, queue depth, and worker ping.",
            "WebSockets: Verifies active client connection count and broadcast channel readiness.",
            "ServiceNow: Performs lightweight REST ping or mock status verification.",
            "SMTP: Checks socket reachability on configured port.",
            "Displays overall system status: HEALTHY, DEGRADED, or CRITICAL."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators at /admin/system/diagnostics.",
        "important_rules": [
            "Probes execute live tests; they do NOT return hardcoded placeholder status.",
            "If a component is unconfigured, it is explicitly reported as NOT CONFIGURED rather than failing.",
            "Failure states include remediation guidance directly on screen."
        ],
        "common_problems": [
            "Redis showing OFFLINE: In local dev mode without Redis, system gracefully degrades to memory-backed tasks."
        ],
        "troubleshooting": [
            {
                "problem": "Database probe reports FAIL",
                "possible_causes": "PostgreSQL service stopped, wrong DATABASE_URL, or connection limit exhausted.",
                "what_to_check": "Inspect DATABASE_URL in backend .env and PostgreSQL server status.",
                "expected_behavior": "Probe reports connection error message and latency.",
                "resolution": "Restart PostgreSQL server (brew services restart postgresql) or correct credentials.",
                "escalation": "Check database server disk space and max_connections."
            }
        ],
        "faqs": [
            {
                "question": "How often do diagnostics refresh?",
                "answer": "Diagnostics refresh on page load and can be manually re-tested by clicking 'Run Diagnostics Probe'."
            }
        ],
        "summary_bullets": [
            "Live synthetic health probes for all services.",
            "Reports PASS, FAIL, BLOCKED, or NOT CONFIGURED.",
            "Live latency and connection depth telemetry.",
            "Actionable remediation hints on error."
        ],
        "keywords": ["diagnostics", "health", "system status", "probes", "telemetry", "redis", "database"],
        "related_features": ["admin_dashboard", "email_smtp", "servicenow_integration"],
        "contextual_hint": "Real-time health verification for Database, WebSockets, ServiceNow, and SMTP."
    },

    # -----------------------------------------------------------------------
    # 9. SECURITY
    # -----------------------------------------------------------------------
    {
        "id": "security_rbac",
        "feature_key": "security_rbac",
        "slug": "security-authentication-and-rbac",
        "title": "Security, JWT Auth & RBAC",
        "category_id": "security",
        "category_name": "Security",
        "summary": "Enterprise role-based access control, cryptographic JWT tokens, password hashing, and API authorization.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Governs identity, authentication, and authorization throughout IncidentFlow. Implements strict Role-Based Access Control (RBAC) across EMPLOYEE, SUPERVISOR, ADMIN, and SYSTEM roles, protecting sensitive operational controls and confidential records.",
        "how_it_works": [
            "Authentication uses secure bcrypt password hashing and HS256 JWT bearer tokens.",
            "Every backend endpoint is guarded by dependency injection factories (get_current_user, require_role).",
            "Group Leaders receive elevated communication privileges without granting full Admin rights.",
            "Cross-origin requests are protected by explicit CORS policies and rate limiting middleware."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators configure user roles; system enforces RBAC on all requests.",
        "important_rules": [
            "RBAC is enforced strictly on the backend server; frontend UI gating is purely cosmetic.",
            "JWT tokens expire automatically after the configured expiration window (480 minutes default).",
            "Admins cannot demote their own account if it is the sole active Admin."
        ],
        "common_problems": [
            "User redirected to login: Token expired; re-authenticate to obtain fresh JWT."
        ],
        "troubleshooting": [
            {
                "problem": "HTTP 403 Forbidden on Admin endpoints",
                "possible_causes": "Logged in as EMPLOYEE role instead of ADMIN or SUPERVISOR.",
                "what_to_check": "Inspect user role badge in header dropdown menu.",
                "expected_behavior": "Non-admins are strictly blocked from /api/admin/* routes.",
                "resolution": "Log in with an authorized Admin account (e.g. admin@incidentflow.dev).",
                "escalation": "Request role promotion from system administrator."
            }
        ],
        "faqs": [
            {
                "question": "Can an employee access Admin Help Documentation?",
                "answer": "No. The Admin Help Center is restricted to Admins and Supervisors. Employees receive dedicated operational guides."
            }
        ],
        "summary_bullets": [
            "Bcrypt hashing and secure JWT authentication.",
            "Server-side RBAC across EMPLOYEE, SUPERVISOR, and ADMIN.",
            "Strict authorization checks on every API endpoint.",
            "Automated token expiration and session security."
        ],
        "keywords": ["security", "rbac", "authentication", "authorization", "jwt", "passwords", "permissions"],
        "related_features": ["audit_logs", "group_leader"],
        "contextual_hint": "Role-based access control and token authorization protecting operational endpoints."
    },

    # -----------------------------------------------------------------------
    # 10. TROUBLESHOOTING GUIDE (Articles for all 25 specific scenarios)
    # -----------------------------------------------------------------------
    {
        "id": "failed_to_fetch_troubleshooting",
        "feature_key": "failed_to_fetch_troubleshooting",
        "slug": "troubleshooting-failed-to-fetch",
        "title": "Troubleshooting: 'Failed to fetch' Error",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Resolution steps when the browser displays 'Failed to fetch' or network communication fails.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Addresses the common browser TypeError: Failed to fetch. Explains root causes including backend downtime, CORS misconfigurations, or network proxy interruptions, and outlines systematic recovery steps.",
        "how_it_works": [
            "Problem: Browser network request fails before receiving an HTTP response code.",
            "Causes: 1. FastAPI backend server is not running on port 8000; 2. NEXT_PUBLIC_API_URL points to an invalid address; 3. CORS origin headers reject the browser origin.",
            "Resolution: 1. Verify backend daemon status; 2. Inspect browser Network tab; 3. Confirm CORS_ORIGINS includes http://localhost:3000."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR"],
        "who_can_use_it_description": "Administrators and technical operators.",
        "important_rules": ["Check terminal processes before altering application configuration."],
        "common_problems": ["Backend stopped unexpectedly during machine sleep."],
        "troubleshooting": [
            {
                "problem": "Failed to fetch displayed on page load",
                "possible_causes": "Uvicorn process stopped.",
                "what_to_check": "Run curl -I http://localhost:8000/api/health in terminal.",
                "expected_behavior": "Returns HTTP 200 OK with healthy status.",
                "resolution": "Restart backend using: uvicorn app.main:app --reload --port 8000.",
                "escalation": "Escalate if port 8000 is occupied by a conflicting process."
            }
        ],
        "faqs": [
            {
                "question": "Does 'Failed to fetch' mean the database is corrupt?",
                "answer": "No. It is purely a network transport error indicating the browser could not establish an HTTP socket with the API server."
            }
        ],
        "summary_bullets": [
            "Common browser network error.",
            "Caused by backend downtime or CORS origin mismatch.",
            "Verify with curl http://localhost:8000/api/health.",
            "FastAPI restart resolves most instances."
        ],
        "keywords": ["failed to fetch", "network error", "cors", "backend down", "connection refused"],
        "related_features": ["diagnostics", "backend_unavailable_troubleshooting"],
        "contextual_hint": "Steps to resolve browser network fetch and connection refused errors."
    },
    {
        "id": "backend_unavailable_troubleshooting",
        "feature_key": "backend_unavailable_troubleshooting",
        "slug": "troubleshooting-backend-unavailable",
        "title": "Troubleshooting: Backend Unavailable & Port Conflicts",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Diagnosing backend server termination, port 8000 collision, and Python environment failures.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Provides steps to resolve backend startup crashes, missing virtual environment dependencies, or port 8000 collisions.",
        "how_it_works": [
            "Check if port 8000 is occupied using lsof -i :8000.",
            "Inspect Python virtualenv activation (.venv/bin/python).",
            "Verify environment configuration in backend/.env."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators.",
        "important_rules": ["Always run backend commands inside the activated Python virtual environment."],
        "common_problems": ["Stale uvicorn process holding socket."],
        "troubleshooting": [
            {
                "problem": "Uvicorn fails to start with Address already in use",
                "possible_causes": "An existing uvicorn process is already running on port 8000.",
                "what_to_check": "Execute lsof -i :8000.",
                "expected_behavior": "Shows PID of existing process.",
                "resolution": "Kill stale process using kill -9 <PID> and relaunch.",
                "escalation": "Check if another service uses port 8000."
            }
        ],
        "faqs": [{"question": "Can I run the backend on port 8080?", "answer": "Yes, update NEXT_PUBLIC_API_URL in frontend .env.local to match."}],
        "summary_bullets": ["Resolve port 8000 collisions with lsof.", "Activate Python 3.12+ virtualenv.", "Verify backend/.env variables."],
        "keywords": ["backend unavailable", "port 8000", "address in use", "python venv"],
        "related_features": ["diagnostics", "failed_to_fetch_troubleshooting"],
        "contextual_hint": "Resolve backend crashes and port 8000 socket collisions."
    },
    {
        "id": "cors_failure_troubleshooting",
        "feature_key": "cors_failure_troubleshooting",
        "slug": "troubleshooting-cors-failures",
        "title": "Troubleshooting: CORS Origin Rejections",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Fixing Cross-Origin Resource Sharing (CORS) policy blocks in browser network requests.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Explains how the browser blocks API requests when the origin header is missing from CORS_ORIGINS in backend settings.",
        "how_it_works": [
            "Browser sends Preflight OPTIONS request.",
            "FastAPI checks request origin against settings.CORS_ORIGINS.",
            "If missing, browser throws CORS policy block."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators.",
        "important_rules": ["Never use wildcard allow_origins=['*'] with allow_credentials=True in production."],
        "common_problems": ["Accessing app via 127.0.0.1:3000 when only localhost:3000 is in whitelist."],
        "troubleshooting": [
            {
                "problem": "Cross-Origin Request Blocked: The Same Origin Policy disallows reading...",
                "possible_causes": "Frontend host not included in CORS_ORIGINS.",
                "what_to_check": "Inspect CORS_ORIGINS in backend/app/core/config.py.",
                "expected_behavior": "Preflight OPTIONS returns 200 with Access-Control-Allow-Origin.",
                "resolution": "Add target origin (e.g. 'http://localhost:3000') to CORS_ORIGINS.",
                "escalation": "Restart backend to reload config."
            }
        ],
        "faqs": [{"question": "Why did CORS work yesterday?", "answer": "Using 127.0.0.1 instead of localhost creates a different browser origin."}],
        "summary_bullets": ["Enforce explicit origin whitelist.", "Differentiate localhost vs 127.0.0.1.", "Preflight OPTIONS handling."],
        "keywords": ["cors", "cross-origin", "preflight", "options", "access-control-allow-origin"],
        "related_features": ["diagnostics", "security_rbac"],
        "contextual_hint": "Fix Cross-Origin Resource Sharing blocks and origin header mismatches."
    },
    {
        "id": "websocket_troubleshooting",
        "feature_key": "websocket_troubleshooting",
        "slug": "troubleshooting-websocket-disconnection",
        "title": "Troubleshooting: WebSocket Disconnected & Realtime Updates",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Diagnosing WebSocket disconnections, proxy buffering, and missing realtime notification updates.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Resolves real-time connection drops that cause chat delays or missed notification badges.",
        "how_it_works": [
            "Frontend connects to ws://localhost:8000/ws/connect?token=JWT.",
            "Connection state transitions: CONNECTING -> CONNECTED (or RECONNECTING on drop).",
            "Heartbeat pings maintain socket liveness."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR", "EMPLOYEE"],
        "who_can_use_it_description": "All users monitor connection badge in header; Admins configure endpoints.",
        "important_rules": ["Expired JWT causes immediate WebSocket closure with code 4001."],
        "common_problems": ["Header shows red 'Offline' badge."],
        "troubleshooting": [
            {
                "problem": "WebSocket stuck in 'Reconnecting...' state",
                "possible_causes": "Invalid or expired JWT token in connection query parameter.",
                "what_to_check": "Inspect browser DevTools Console for WebSocket connection errors.",
                "expected_behavior": "Auto-reconnects on valid token.",
                "resolution": "Log out and log back in to refresh token.",
                "escalation": "Verify /ws/connect route in app/websocket/manager.py."
            }
        ],
        "faqs": [{"question": "Does WebSocket affect assignment?", "answer": "No. Assignment happens in database; WebSockets only deliver live UI notification badges."}],
        "summary_bullets": ["Token-authenticated WebSocket socket.", "Auto-reconnection with exponential backoff.", "Heartbeat liveness monitoring."],
        "keywords": ["websocket", "offline", "reconnecting", "realtime", "socket drop"],
        "related_features": ["notifications", "chat_system"],
        "contextual_hint": "Troubleshoot real-time WebSocket connection drops and reconnect issues."
    },
    {
        "id": "chat_failure_troubleshooting",
        "feature_key": "chat_failure_troubleshooting",
        "slug": "troubleshooting-chat-messages",
        "title": "Troubleshooting: Chat Loading & Message Sending Failures",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Resolving chat message delivery failures, red retry buttons, and channel access errors.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Guides users through recovering from chat message delivery timeouts, socket disconnections, or media attachment errors.",
        "how_it_works": [
            "Messages are posted via POST /api/chat/conversations/{id}/messages.",
            "If request fails, message card displays a red retry button.",
            "Clicking retry re-submits the message payload."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR", "EMPLOYEE"],
        "who_can_use_it_description": "All chat users.",
        "important_rules": ["Files over size limits are rejected immediately by client and server."],
        "common_problems": ["Sending message during network switch."],
        "troubleshooting": [
            {
                "problem": "Message shows red warning icon and 'Failed to send'",
                "possible_causes": "Temporary network drop during POST request.",
                "what_to_check": "Verify WebSocket status in header.",
                "expected_behavior": "Clicking retry button immediately re-dispatches message.",
                "resolution": "Click the retry button on the affected message.",
                "escalation": "Verify conversation membership in database."
            }
        ],
        "faqs": [{"question": "Are failed messages saved?", "answer": "Yes. Failed messages remain in client memory until retried or discarded."}],
        "summary_bullets": ["Inline retry for failed chat messages.", "Size validation on file uploads.", "Reconnection synchronization."],
        "keywords": ["chat error", "message failed", "retry", "chat not loading"],
        "related_features": ["chat_system", "websocket_troubleshooting"],
        "contextual_hint": "Fix chat delivery errors and use inline retry for failed messages."
    },
    {
        "id": "notifications_troubleshooting",
        "feature_key": "notifications_troubleshooting",
        "slug": "troubleshooting-notifications",
        "title": "Troubleshooting: Notifications Not Appearing",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Resolving missing in-app alert badges, unread counter discrepancies, and filter issues.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Helps users locate unread notifications, verify WebSocket delivery, and clear badge synchronization drifts.",
        "how_it_works": ["Alerts query GET /api/notifications.", "Unread counter counts is_read == False.", "Marking as read updates backend timestamp."],
        "who_can_use_it": ["ADMIN", "SUPERVISOR", "EMPLOYEE"],
        "who_can_use_it_description": "All users.",
        "important_rules": ["Group Notices and Personal Assignments appear in the same notification stream with distinct badges."],
        "common_problems": ["User on different team looking for incident notice."],
        "troubleshooting": [
            {
                "problem": "Unread notification badge count shows 0 despite new incident",
                "possible_causes": "User belongs to a different team than the incident's assignment group.",
                "what_to_check": "Verify user's team in Profile vs incident's assignment group.",
                "expected_behavior": "Only members of target team receive Group Notice.",
                "resolution": "Assign incident to user's team if relevant.",
                "escalation": "Check notification_service.py logs."
            }
        ],
        "faqs": [{"question": "Can I mark all notifications as read at once?", "answer": "Yes. Click 'Mark all as read' at the top of the Notifications page."}],
        "summary_bullets": ["Check team membership for group notice delivery.", "In-app alerts function independently of email.", "Clear unread badges with one click."],
        "keywords": ["notifications missing", "badge count", "unread", "alerts not showing"],
        "related_features": ["notifications", "team_notice"],
        "contextual_hint": "Resolve missing notification badges and unread counter drifts."
    },
    {
        "id": "servicenow_troubleshooting",
        "feature_key": "servicenow_troubleshooting",
        "slug": "troubleshooting-servicenow-failures",
        "title": "Troubleshooting: ServiceNow Connection & Sync Failures",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Resolving ServiceNow webhook timeouts, 401 unauthorized errors, and patch sync failures.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Provides systematic troubleshooting for ServiceNow integration failures, authentication blocks, and payload mapping errors.",
        "how_it_works": [
            "Inspect Admin > Integrations > ServiceNow Sync Events.",
            "Verify webhook payload format and sys_id presence.",
            "Test outbound PATCH connectivity."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators.",
        "important_rules": ["In Mock Mode, ServiceNow requests succeed synthetically for staging."],
        "common_problems": ["Invalid client secret or network firewall blocking outbound calls."],
        "troubleshooting": [
            {
                "problem": "ServiceNow sync event reports 'Connection Timeout' or 'HTTP 401'",
                "possible_causes": "ServiceNow instance URL unreachable or API credentials expired.",
                "what_to_check": "Navigate to Admin > Integrations and click 'Test Connection'.",
                "expected_behavior": "Returns detailed diagnostic probe result.",
                "resolution": "Re-enter ServiceNow Client Secret and test connection.",
                "escalation": "Verify network firewall permits HTTPS egress to ServiceNow."
            }
        ],
        "faqs": [{"question": "Do failed ServiceNow sync events retry automatically?", "answer": "Yes. Background workers retry failed sync events with exponential backoff up to 5 attempts."}],
        "summary_bullets": ["Use built-in 'Test Connection' probe.", "Inspect event logs in Admin > Integrations.", "Exponential backoff retry for transient drops."],
        "keywords": ["servicenow failure", "timeout", "sync error", "401 unauthorized", "webhook error"],
        "related_features": ["servicenow_integration", "diagnostics"],
        "contextual_hint": "Troubleshoot ServiceNow connection timeouts, 401 errors, and webhook drops."
    },
    {
        "id": "smtp_email_troubleshooting",
        "feature_key": "smtp_email_troubleshooting",
        "slug": "troubleshooting-smtp-email",
        "title": "Troubleshooting: SMTP Email Delivery Failures",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Resolving STARTTLS handshake failures, Gmail App Password rejections, and relay timeouts.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Provides step-by-step diagnostic resolution for SMTP connection rejections and missing email notifications.",
        "how_it_works": [
            "Open Admin > Settings > SMTP Configuration.",
            "Click 'Send Test Email' to execute live socket probe.",
            "Review specific error response code."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators.",
        "important_rules": ["Never claim email delivered without SMTP 250 OK code."],
        "common_problems": ["Port 587 blocked on local ISP or corporate proxy."],
        "troubleshooting": [
            {
                "problem": "Send Test Email fails with SMTPAuthenticationError (535)",
                "possible_causes": "Regular password used instead of App Password on 2FA-enabled account.",
                "what_to_check": "Email provider account security settings.",
                "expected_behavior": "App passwords bypass 2FA prompts.",
                "resolution": "Generate a new 16-character App Password and save in Settings.",
                "escalation": "Verify SMTP relay authorization with mail admin."
            }
        ],
        "faqs": [{"question": "Can we test email without sending to real users?", "answer": "Yes. The 'Send Test Email' tool delivers only to the admin's personal address."}],
        "summary_bullets": ["Live socket test via 'Send Test Email'.", "Use dedicated App Passwords.", "Inspect port 587 STARTTLS settings."],
        "keywords": ["smtp failure", "email failed", "535 authentication", "starttls", "app password"],
        "related_features": ["email_smtp", "notifications"],
        "contextual_hint": "Resolve SMTP authentication errors, port 587 blocks, and delivery drops."
    },
    {
        "id": "duplicate_assignment_troubleshooting",
        "feature_key": "duplicate_assignment_troubleshooting",
        "slug": "troubleshooting-duplicate-assignment",
        "title": "Troubleshooting: Duplicate Webhook & Double-Click Prevention",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "How IncidentFlow guarantees idempotency and database safety against duplicate webhooks or admin clicks.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Explains the multi-layer database protections that prevent duplicate active assignments when multiple admins trigger assignment or duplicate webhooks arrive.",
        "how_it_works": [
            "Layer 1: Idempotency check checks for existing active assignment immediately.",
            "Layer 2: Database partial unique index uq_active_incident_assignment permits exactly 1 active assignment per incident.",
            "Layer 3: Assignment history query skips past handlers in rotation."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators.",
        "important_rules": ["Database constraints strictly guarantee single active assignment."],
        "common_problems": ["Admin rapidly double-clicks 'Send Notice' button."],
        "troubleshooting": [
            {
                "problem": "Admin clicked 'Send Notice' twice in rapid succession",
                "possible_causes": "Browser latency or accidental double-click.",
                "what_to_check": "Inspect Admin > Assignments for the target incident.",
                "expected_behavior": "Second call detects active assignment and returns it idempotently without duplicating.",
                "resolution": "No action needed; system safely deduplicates automatically.",
                "escalation": "None."
            }
        ],
        "faqs": [{"question": "What happens if ServiceNow sends two identical webhooks?", "answer": "The second webhook matches on servicenow_sys_id and returns the existing incident idempotently."}],
        "summary_bullets": ["Database-level unique active index protection.", "Idempotent handling of duplicate webhooks.", "Safe against admin double-clicks."],
        "keywords": ["duplicate assignment", "idempotency", "double click", "concurrency", "unique constraint"],
        "related_features": ["automatic_assignment", "assignment_rotation"],
        "contextual_hint": "Learn how database constraints prevent duplicate assignments during retries."
    },
    {
        "id": "unassigned_incident_troubleshooting",
        "feature_key": "unassigned_incident_troubleshooting",
        "slug": "troubleshooting-unassigned-incidents",
        "title": "Troubleshooting: Incident Left Unassigned",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Diagnosing why an incident was not assigned: Sunday holiday, no shift coverage, or cycle completed.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Identifies the exact reason an incident remains in UNASSIGNED, QUEUED, or ALL_TEAM_MEMBERS_ASSIGNED state.",
        "how_it_works": [
            "Check 1: Sunday Holiday -> State QUEUED with SUNDAY_HOLIDAY_QUEUED.",
            "Check 2: All 10 Members Handled -> State ALL_TEAM_MEMBERS_ASSIGNED.",
            "Check 3: Automation Paused -> State UNASSIGNED with AUTO_ASSIGN_SKIPPED.",
            "Check 4: Shift Gap -> No scheduled shift covering arrival timestamp."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR"],
        "who_can_use_it_description": "Administrators.",
        "important_rules": ["Review the audit log for the incident ID to see the exact decision code."],
        "common_problems": ["Incident arriving on Sunday during holiday pause."],
        "troubleshooting": [
            {
                "problem": "Incident remains in UNASSIGNED state",
                "possible_causes": "Automation is PAUSED, or shift gap exists.",
                "what_to_check": "Navigate to Admin > Audit Logs and search the incident number.",
                "expected_behavior": "Audit event specifies exact reason code.",
                "resolution": "If automation is paused, resume it in Settings. If shift gap, adjust shift hours.",
                "escalation": "Manual assign if immediate remediation is required."
            }
        ],
        "faqs": [{"question": "Can I force assign an unassigned incident?", "answer": "Yes. Admins can click 'Assign' on the incident card to manually select a team member."}],
        "summary_bullets": ["Inspect audit log for exact reason code.", "Verify automation mode is not PAUSED.", "Check Sunday holiday status."],
        "keywords": ["unassigned", "queued", "not assigned", "all team members assigned", "sunday"],
        "related_features": ["automatic_assignment", "working_days", "shifts"],
        "contextual_hint": "Diagnose reasons why an incident was left unassigned or queued."
    },
    {
        "id": "team_activation_blocked_troubleshooting",
        "feature_key": "team_activation_blocked_troubleshooting",
        "slug": "troubleshooting-team-activation-blocked",
        "title": "Troubleshooting: Team Activation Blocked",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Resolving TEAM_ACTIVATION_BLOCKED violations (roster != 10, no leader, or missing shift coverage).",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Explains the 4 mandatory criteria for activating an operational team and how to resolve blocking errors.",
        "how_it_works": [
            "Endpoint POST /api/admin/teams/{id}/activate checks:",
            "1. Member count == 10 active employees.",
            "2. Exactly 1 active Group Leader.",
            "3. 100% active shift coverage across all 10 members.",
            "4. Team name and configuration present."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators.",
        "important_rules": ["Active teams must strictly fulfill all 4 criteria."],
        "common_problems": ["9 or 11 members configured in draft team."],
        "troubleshooting": [
            {
                "problem": "Clicking Activate Team returns HTTP 400 TEAM_ACTIVATION_BLOCKED",
                "possible_causes": "Roster count is not 10 or one member has no shift assigned.",
                "what_to_check": "Review the violations list displayed in the modal.",
                "expected_behavior": "Lists exact missing requirements.",
                "resolution": "Adjust roster to exactly 10 members, designate 1 leader, assign shifts to all.",
                "escalation": "Align staffing with team lead."
            }
        ],
        "faqs": [{"question": "Can a team remain in DRAFT status?", "answer": "Yes. Draft teams can have any number of members while configuration is being finalized."}],
        "summary_bullets": ["Must have exactly 10 active members.", "Must have exactly 1 Group Leader.", "100% shift coverage required."],
        "keywords": ["team activation", "activation blocked", "10 members", "group leader missing"],
        "related_features": ["teams", "employees", "group_leader"],
        "contextual_hint": "Fix team activation blocks and satisfy the 4-point validation gate."
    },
    {
        "id": "duplicate_employee_id_troubleshooting",
        "feature_key": "duplicate_employee_id_troubleshooting",
        "slug": "troubleshooting-duplicate-employee-id",
        "title": "Troubleshooting: Duplicate Employee ID Rejection",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Resolving DUPLICATE_EMPLOYEE_ID errors during employee creation or profile editing.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Explains the database-level uniqueness requirement for Employee IDs (e.g. DB001) and how to resolve conflicts.",
        "how_it_works": [
            "API checks Employee.employee_code for duplicates.",
            "Database unique index enforces globally unique values.",
            "Rejects duplicate creation with code DUPLICATE_EMPLOYEE_ID."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators.",
        "important_rules": ["Employee IDs are globally unique across all teams."],
        "common_problems": ["Re-using an existing employee code from another group."],
        "troubleshooting": [
            {
                "problem": "Cannot create employee: 'Employee ID already exists'",
                "possible_causes": "Target employee_code is already assigned to an existing record.",
                "what_to_check": "Search Admin > Employees for the target code.",
                "expected_behavior": "Database rejects duplicates with HTTP 400.",
                "resolution": "Use the next sequential code in the team series (e.g. DB008).",
                "escalation": "Audit employee code assignment roster."
            }
        ],
        "faqs": [{"question": "Can I edit an employee's ID?", "answer": "Yes, provided the new code is unique across the entire organization."}],
        "summary_bullets": ["Globally unique Employee IDs.", "Enforced by database unique constraint.", "Use next sequential number in team series."],
        "keywords": ["duplicate employee id", "employee code exists", "unique constraint"],
        "related_features": ["employee_ids", "employees"],
        "contextual_hint": "Resolve Employee ID collisions and assign sequential identifiers."
    },
    {
        "id": "task_catalog_precedence_troubleshooting",
        "feature_key": "task_catalog_precedence_troubleshooting",
        "slug": "troubleshooting-task-catalog-precedence",
        "title": "Troubleshooting: Task Instructions Precedence",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Understanding why ServiceNow work instructions override local Task Catalog templates.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Explains how IncidentFlow resolves task instructions when both ServiceNow and the local Task Catalog provide instructions.",
        "how_it_works": [
            "Rule 1: ServiceNow explicit instructions take precedence.",
            "Rule 2: If ServiceNow instructions are empty, local team catalog template is applied.",
            "Rule 3: Snapshot is frozen onto the assignment record."
        ],
        "who_can_use_it": ["ADMIN", "SUPERVISOR"],
        "who_can_use_it_description": "Administrators and assigned engineers.",
        "important_rules": ["ServiceNow instructions always override local templates."],
        "common_problems": ["Engineer expecting catalog text when ServiceNow provided custom text."],
        "troubleshooting": [
            {
                "problem": "Task instructions differ from the team catalog template",
                "possible_causes": "ServiceNow incident payload contained custom work instructions.",
                "what_to_check": "Inspect incident details in Admin > Incidents under 'Work Instructions'.",
                "expected_behavior": "ServiceNow instructions take precedence by design.",
                "resolution": "If catalog instructions are preferred, clear the custom field in ServiceNow.",
                "escalation": "Align process with ServiceNow dispatch team."
            }
        ],
        "faqs": [{"question": "Are catalog changes retroactive?", "answer": "No. Historical assignments retain their frozen task snapshots."}],
        "summary_bullets": ["ServiceNow instructions take top precedence.", "Catalog templates used as authoritative fallback.", "Snapshots ensure historical accuracy."],
        "keywords": ["task precedence", "work instructions", "catalog override", "sop"],
        "related_features": ["task_catalog", "my_work"],
        "contextual_hint": "Understand ServiceNow work instruction precedence over catalog templates."
    },
    {
        "id": "my_work_sync_troubleshooting",
        "feature_key": "my_work_sync_troubleshooting",
        "slug": "troubleshooting-my-work-sync",
        "title": "Troubleshooting: My Work Queue Synchronization",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Resolving task card visibility, status transition locks, and workload counter updates.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Assists engineers when task cards do not immediately update or appear in My Work.",
        "how_it_works": [
            "My Work queries GET /api/me/work.",
            "Filters: assignment.employee_id == current_user.employee.id AND is_active == True.",
            "Status updates broadcast MY_WORK_UPDATED over WebSockets."
        ],
        "who_can_use_it": ["ADMIN", "EMPLOYEE"],
        "who_can_use_it_description": "Engineers and Admins.",
        "important_rules": ["Only active assignments appear in the active workbench."],
        "common_problems": ["Completed tasks disappear from active view: check 'Completed Work' tab."],
        "troubleshooting": [
            {
                "problem": "Assigned incident does not appear in My Work",
                "possible_causes": "Logged in with a different user account or assignment held by another teammate.",
                "what_to_check": "Check header user avatar to verify logged-in identity.",
                "expected_behavior": "Only the designated personal assignee sees the active card.",
                "resolution": "Log in with the assigned engineer's account.",
                "escalation": "Verify assignment record in Admin > Assignments."
            }
        ],
        "faqs": [{"question": "Where do completed incidents go?", "answer": "Completed tasks move to the 'Completed Work' tab in My Work."}],
        "summary_bullets": ["Active workbench shows is_active == True.", "Completed items archived in history tab.", "Single-owner visibility."],
        "keywords": ["my work sync", "task missing", "card not showing", "workbench"],
        "related_features": ["my_work", "team_notice"],
        "contextual_hint": "Troubleshoot My Work task card visibility and status synchronization."
    },
    {
        "id": "upload_failure_troubleshooting",
        "feature_key": "upload_failure_troubleshooting",
        "slug": "troubleshooting-media-uploads",
        "title": "Troubleshooting: Image & Audio Upload Failures",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Resolving media attachment rejections, file size limits, and audio recording permissions.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Addresses media upload errors in chat, such as file size exceeded, unsupported format, or browser microphone access blocked.",
        "how_it_works": [
            "Client validates mime-type (image/png, image/jpeg, audio/webm, audio/mp4).",
            "Server checks size limits (5MB for images, 10MB for audio).",
            "Files are stored securely in backend/media/ directory."
        ],
        "who_can_use_it": ["ADMIN", "EMPLOYEE"],
        "who_can_use_it_description": "All chat users.",
        "important_rules": ["Disallowed executable extensions (.exe, .sh) are rejected immediately."],
        "common_problems": ["Microphone permission blocked in browser settings."],
        "troubleshooting": [
            {
                "problem": "Cannot record voice note: 'Microphone access denied'",
                "possible_causes": "Browser site permissions block audio capture.",
                "what_to_check": "Click the lock icon in the browser address bar.",
                "expected_behavior": "Browser prompts for microphone access.",
                "resolution": "Set Microphone to 'Allow' and refresh the page.",
                "escalation": "Check operating system privacy settings for microphone."
            }
        ],
        "faqs": [{"question": "What is the maximum image size?", "answer": "5 Megabytes per image."}],
        "summary_bullets": ["Size limits: 5MB image, 10MB audio.", "Browser microphone permissions required for voice notes.", "Strict extension whitelisting."],
        "keywords": ["upload failure", "voice note error", "microphone access", "file size exceeded"],
        "related_features": ["chat_system"],
        "contextual_hint": "Resolve chat attachment upload errors and browser microphone permissions."
    },
    {
        "id": "sunday_holiday_troubleshooting",
        "feature_key": "sunday_holiday_troubleshooting",
        "slug": "troubleshooting-sunday-holiday-queuing",
        "title": "Troubleshooting: Sunday Holiday Queuing Behavior",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Why incidents arriving on Sunday are held in QUEUED state and how work resumes on Monday.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Explains Sunday automated assignment pausing and verifies that work is safely held rather than lost.",
        "how_it_works": [
            "Incident arrival on Sunday checks now.weekday() == 6.",
            "System logs SUNDAY_HOLIDAY_QUEUED and sets state to QUEUED.",
            "Work automatically resumes on Monday."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators.",
        "important_rules": ["Sunday is the only default holiday; Saturday is a normal working day."],
        "common_problems": ["User expecting automatic assignment on Sunday."],
        "troubleshooting": [
            {
                "problem": "Incidents not assigned automatically on Sunday",
                "possible_causes": "Expected Sunday holiday policy.",
                "what_to_check": "Check incident state for 'QUEUED' and audit log for 'SUNDAY_HOLIDAY_QUEUED'.",
                "expected_behavior": "Assignment pauses until Monday.",
                "resolution": "If emergency assignment is required, Admin can manually assign the incident.",
                "escalation": "None needed; this is expected behavior."
            }
        ],
        "faqs": [{"question": "Can we override Sunday holiday policy?", "answer": "Admins can perform manual assignment at any time on Sunday."}],
        "summary_bullets": ["Sunday is the default holiday.", "Incidents securely queued, never dropped.", "Work resumes on Monday."],
        "keywords": ["sunday holiday", "queued", "sunday pause", "weekend policy"],
        "related_features": ["working_days", "automatic_assignment"],
        "contextual_hint": "Understand Sunday automated assignment pausing and queue resumption."
    },
    {
        "id": "cross_team_assignment_troubleshooting",
        "feature_key": "cross_team_assignment_troubleshooting",
        "slug": "troubleshooting-cross-team-assignment-blocked",
        "title": "Troubleshooting: Cross-Team Assignment Blocked",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Why assigning an employee from another team is rejected and how to preserve team isolation.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Explains the hard business rule preventing incidents from being assigned to engineers outside the incident's designated team.",
        "how_it_works": [
            "API endpoint validates that target employee's team_id matches the incident's assignment_group.",
            "If teams differ, raises HTTP 400 with CROSS_TEAM_ASSIGNMENT_BLOCKED.",
            "Protects operational domain expertise and SLA ownership."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators.",
        "important_rules": ["Cross-team assignment is strictly prohibited server-side."],
        "common_problems": ["Selecting engineer from wrong dropdown in manual assignment modal."],
        "troubleshooting": [
            {
                "problem": "Manual assign fails: 'Cross-team assignment is strictly prohibited'",
                "possible_causes": "Target engineer belongs to a different operational team.",
                "what_to_check": "Compare incident assignment group with employee's assigned team.",
                "expected_behavior": "Rejects with HTTP 400 CROSS_TEAM_ASSIGNMENT_BLOCKED.",
                "resolution": "Select a candidate belonging to the matching team, or re-route the incident in ServiceNow.",
                "escalation": "Update incident assignment group if incorrectly categorized."
            }
        ],
        "faqs": [{"question": "Can an engineer belong to two teams?", "answer": "No. Each active employee belongs to exactly one team."}],
        "summary_bullets": ["Strict domain isolation.", "Cross-team assignment rejected server-side.", "Re-route incident group in ServiceNow if necessary."],
        "keywords": ["cross-team", "assignment blocked", "domain isolation", "wrong team"],
        "related_features": ["incidents", "teams", "employees"],
        "contextual_hint": "Resolve cross-team assignment blocks and maintain group isolation."
    },
    {
        "id": "midnight_shift_troubleshooting",
        "feature_key": "midnight_shift_troubleshooting",
        "slug": "troubleshooting-midnight-crossing-shifts",
        "title": "Troubleshooting: Shifts Crossing Midnight",
        "category_id": "troubleshooting",
        "category_name": "Troubleshooting",
        "summary": "Configuring and verifying overnight shifts (e.g. 22:00–06:00) with timezone-aware calculations.",
        "status": "DOCUMENTED",
        "version": "2.4.0",
        "updated_at": "September 2026",
        "what_it_does": "Ensures overnight shifts that cross calendar day boundaries correctly resolve active coverage during early morning hours (e.g. 00:30).",
        "how_it_works": [
            "When start_time > end_time (e.g. 22:00 to 06:00), shift is identified as an overnight shift.",
            "ShiftService checks whether local time is >= start_time OR < end_time.",
            "Timestamps are stored in UTC, and shift intervals are evaluated in Asia/Kolkata."
        ],
        "who_can_use_it": ["ADMIN"],
        "who_can_use_it_description": "Administrators.",
        "important_rules": ["Always specify timezones explicitly (Asia/Kolkata default)."],
        "common_problems": ["Incorrectly treating 00:30 as an unassigned gap."],
        "troubleshooting": [
            {
                "problem": "Incidents arriving at 01:00 marked unassigned during night shift",
                "possible_causes": "Night shift defined as 22:00 to 23:59 instead of continuous overnight 22:00 to 06:00.",
                "what_to_check": "Inspect Admin > Shifts for Shift C start and end times.",
                "expected_behavior": "Continuous overnight calculation includes hours 00:00 to 06:00.",
                "resolution": "Set Night Shift start_time to 22:00 and end_time to 06:00.",
                "escalation": "Verify ShiftService.get_active_shift logic."
            }
        ],
        "faqs": [{"question": "Does daylight saving time affect shifts?", "answer": "Asia/Kolkata (IST) does not observe DST, maintaining stable +05:30 offset year-round."}],
        "summary_bullets": ["Timezone-aware overnight shift calculations.", "Evaluates hours crossing midnight seamlessly.", "Stored in UTC, calculated in local team timezone."],
        "keywords": ["midnight shift", "overnight", "cross midnight", "shift boundary", "timezone"],
        "related_features": ["shifts", "automatic_assignment"],
        "contextual_hint": "Configure continuous overnight shifts crossing calendar midnight boundaries."
    }
]

WHAT_IS_NEW = [
    {
        "id": "new_admin_help_center",
        "title": "Admin Help Center & Knowledge Base",
        "date": "September 2026",
        "version": "2.4.0",
        "tag": "NEW",
        "article_slug": "admin-dashboard",
        "summary": "Complete, production-quality Help Center with interactive search, feature summaries, FAQ doubt assistants, and real-time coverage auditing."
    },
    {
        "id": "new_authoritative_assignment_rules",
        "title": "Schedule-Driven Assignment & History Deduplication",
        "date": "September 2026",
        "version": "2.3.0",
        "tag": "NEW",
        "article_slug": "automatic-assignment-workflow",
        "summary": "Eliminated availability/presence assignment gates. Shift schedule is now the sole authority, backed by sequential rotation and ALL_TEAM_MEMBERS_ASSIGNED cycle completion."
    },
    {
        "id": "new_mandatory_10_member_teams",
        "title": "Mandatory 10-Employee Team Invariant",
        "date": "September 2026",
        "version": "2.2.0",
        "tag": "NEW",
        "article_slug": "employee-management",
        "summary": "Enforced hard server-side requirement that all active operational teams must contain exactly 10 members, 1 Group Leader, and 100% shift coverage."
    },
    {
        "id": "new_global_search",
        "title": "Global Present-Page Search & Command Palette",
        "date": "September 2026",
        "version": "2.1.0",
        "tag": "NEW",
        "article_slug": "global-present-page-search",
        "summary": "Persistent search in the global header supporting Cmd + K, current-page filtering, and cross-category authorized search."
    },
    {
        "id": "new_admin_leader_chat",
        "title": "Admin ↔ Group Leader Private Channels",
        "date": "September 2026",
        "version": "2.0.0",
        "tag": "NEW",
        "article_slug": "admin-group-leader-private-chat",
        "summary": "Confidential communication pipeline connecting executive Administrators directly with active Group Leaders."
    }
]


class HelpService:
    @staticmethod
    def _normalize_article(raw: Dict[str, Any]) -> Dict[str, Any]:
        art = dict(raw)
        # 1. who_can_use_it: List[str]
        roles = art.get("who_can_use_it")
        if isinstance(roles, list):
            art["who_can_use_it"] = [str(r).strip() for r in roles if str(r).strip()]
        elif isinstance(roles, str):
            who_desc = roles
            parsed = []
            upper = roles.upper()
            if "ADMIN" in upper:
                parsed.append("ADMIN")
            if "SUPERVISOR" in upper:
                parsed.append("SUPERVISOR")
            if "LEADER" in upper:
                parsed.append("GROUP_LEADER")
            if "EMPLOYEE" in upper or "ENGINEER" in upper:
                parsed.append("EMPLOYEE")
            art["who_can_use_it"] = parsed if parsed else ["ADMIN"]
            if not art.get("who_can_use_it_description"):
                art["who_can_use_it_description"] = who_desc
        else:
            art["who_can_use_it"] = ["ADMIN"]

        # 2. how_it_works: List[str]
        hiw = art.get("how_it_works", [])
        if isinstance(hiw, list):
            art["how_it_works"] = [str(item).strip() for item in hiw if str(item).strip()]
        elif isinstance(hiw, str):
            art["how_it_works"] = [line.strip("• ").strip() for line in hiw.split("\n") if line.strip()]
        else:
            art["how_it_works"] = []

        # 3. common_problems: List[Dict[str, str]]
        cps = art.get("common_problems", [])
        norm_cps = []
        for cp in cps:
            if isinstance(cp, dict):
                norm_cps.append({
                    "problem": cp.get("problem", ""),
                    "cause": cp.get("cause") or cp.get("possible_causes", "Operational condition"),
                    "resolution": cp.get("resolution", "")
                })
            elif isinstance(cp, str):
                parts = cp.split(":", 1)
                if len(parts) == 2:
                    norm_cps.append({"problem": parts[0].strip(), "cause": "Operational condition", "resolution": parts[1].strip()})
                else:
                    norm_cps.append({"problem": cp, "cause": "Operational condition", "resolution": "Refer to operational manual or admin settings."})
        art["common_problems"] = norm_cps

        # 4. troubleshooting_steps: List[str]
        tb_steps = art.get("troubleshooting_steps", [])
        if not tb_steps and "troubleshooting" in art:
            tb_steps = []
            for tb in art.get("troubleshooting", []):
                if isinstance(tb, dict):
                    prob = tb.get("problem", "")
                    fix = tb.get("resolution", "")
                    if prob and fix:
                        tb_steps.append(f"{prob} — Resolution: {fix}")
                    elif prob:
                        tb_steps.append(prob)
                elif isinstance(tb, str):
                    tb_steps.append(tb)
        art["troubleshooting_steps"] = tb_steps

        # 5. faqs: List[Dict[str, str]]
        raw_faqs = art.get("faqs", [])
        norm_faqs = []
        for f in raw_faqs:
            if isinstance(f, dict):
                q = f.get("question") or f.get("q", "")
                a = f.get("answer") or f.get("a", "")
                if q and a:
                    norm_faqs.append({"question": q, "answer": a})
        art["faqs"] = norm_faqs

        if not isinstance(art.get("important_rules"), list):
            art["important_rules"] = []
        if not isinstance(art.get("related_features"), list):
            art["related_features"] = []
        if not isinstance(art.get("tags"), list):
            art["tags"] = art.get("keywords", [])

        return art

    @staticmethod
    def get_categories() -> List[Dict[str, Any]]:
        categories = []
        for cat in HELP_CATEGORIES:
            count = sum(1 for a in HELP_ARTICLES if a["category_id"] == cat["id"])
            categories.append({
                **cat,
                "article_count": count
            })
        return categories

    @staticmethod
    def get_articles(
        category_id: Optional[str] = None,
        status: Optional[str] = None,
        query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        results = HELP_ARTICLES
        if category_id:
            results = [a for a in results if a["category_id"] == category_id]
        if status:
            results = [a for a in results if a.get("status") == status]
        if query and query.strip():
            q = query.strip().lower()
            results = [
                a for a in results
                if q in a["title"].lower()
                or q in a["summary"].lower()
                or q in a.get("what_it_does", "").lower()
                or any(q in kw.lower() for kw in a.get("keywords", []))
            ]
        return [HelpService._normalize_article(a) for a in results]

    @staticmethod
    def get_article(slug: str) -> Optional[Dict[str, Any]]:
        slug_clean = slug.strip().lower()
        for a in HELP_ARTICLES:
            if a["slug"] == slug_clean or a["id"] == slug_clean:
                return HelpService._normalize_article(a)
        return None

    @staticmethod
    def search(query: str, limit: int = 20) -> Dict[str, Any]:
        q = (query or "").strip().lower()
        if not q:
            return {"query": "", "total_count": 0, "results": []}

        tokens = [t for t in re.split(r'[\s\-_,]+', q) if len(t) > 1]

        scored_articles = []
        for article in HELP_ARTICLES:
            score = 0
            title_lower = article["title"].lower()
            summary_lower = article["summary"].lower()
            what_lower = article.get("what_it_does", "").lower()
            keywords = [kw.lower() for kw in article.get("keywords", [])]
            trouble_text = " ".join(
                f"{tb.get('problem', '')} {tb.get('possible_causes', '')} {tb.get('resolution', '')}"
                for tb in article.get("troubleshooting", [])
            ).lower()

            # Exact full phrase matches
            if q == title_lower:
                score += 120
            elif q in title_lower:
                score += 60

            if q in summary_lower:
                score += 40
            if q in what_lower:
                score += 20
            if q in trouble_text:
                score += 50

            for kw in keywords:
                if q == kw:
                    score += 50
                elif q in kw:
                    score += 30

            # Token-based matches
            matched_tokens = 0
            for t in tokens:
                token_matched = False
                if t in title_lower:
                    score += 25
                    token_matched = True
                if any(t in kw for kw in keywords):
                    score += 20
                    token_matched = True
                if t in summary_lower:
                    score += 10
                    token_matched = True
                if t in trouble_text:
                    score += 15
                    token_matched = True
                if t in what_lower:
                    score += 5
                    token_matched = True
                if token_matched:
                    matched_tokens += 1

            # Bonus if all query tokens matched
            if tokens and matched_tokens == len(tokens):
                score += 40

            if score > 0:
                scored_articles.append((score, article))

        scored_articles.sort(key=lambda x: -x[0])
        top_results = [item[1] for item in scored_articles[:limit]]


        return {
            "query": query,
            "total_count": len(top_results),
            "results": [
                {
                    "id": a["id"],
                    "slug": a["slug"],
                    "title": a["title"],
                    "category_id": a["category_id"],
                    "category_name": a["category_name"],
                    "summary": a["summary"],
                    "status": a.get("status", "DOCUMENTED"),
                    "version": a.get("version", "2.4.0"),
                    "updated_at": a.get("updated_at", "September 2026")
                }
                for a in top_results
            ]
        }

    @staticmethod
    def get_whats_new() -> List[Dict[str, Any]]:
        return WHAT_IS_NEW

    @staticmethod
    def get_coverage_audit() -> Dict[str, Any]:
        """
        Section 24: Automatic Help Coverage Audit.
        Compares ACTUAL ADMIN FEATURES against DOCUMENTED HELP ARTICLES.
        """
        documented_feature_keys = set(a.get("feature_key") for a in HELP_ARTICLES if a.get("feature_key"))
        actual_features = set(ACTUAL_ADMIN_FEATURES)

        missing_features = sorted(list(actual_features - documented_feature_keys))
        documented_count = len(actual_features & documented_feature_keys)
        total_features = len(actual_features)
        coverage_pct = round((documented_count / total_features) * 100, 1) if total_features else 100.0

        is_complete = len(missing_features) == 0

        return {
            "total_admin_features": total_features,
            "documented_features": documented_count,
            "missing_features": missing_features,
            "help_coverage_percentage": coverage_pct,
            "status": "COMPLETE" if is_complete else "INCOMPLETE",
            "audit_timestamp": "September 2026",
            "features_directory": [
                {
                    "feature_key": feat,
                    "is_documented": feat in documented_feature_keys,
                    "article_slug": next((a["slug"] for a in HELP_ARTICLES if a.get("feature_key") == feat), None)
                }
                for feat in sorted(list(actual_features))
            ]
        }

    @staticmethod
    def get_contextual_help(feature_key: str) -> Optional[Dict[str, Any]]:
        fk = feature_key.strip().lower()
        for a in HELP_ARTICLES:
            if a.get("feature_key") == fk or a["slug"] == fk or a["id"] == fk:
                return {
                    "title": a["title"],
                    "slug": a["slug"],
                    "summary": a["summary"],
                    "hint": a.get("contextual_hint", a["summary"]),
                    "important_rules": a.get("important_rules", [])[:2]
                }
        return None

    @staticmethod
    def summarize_article(slug: str) -> Dict[str, Any]:
        article = HelpService.get_article(slug)
        if not article:
            return {"error": "Article not found", "slug": slug}

        return {
            "title": article["title"],
            "slug": article["slug"],
            "summary_title": f"{article['title']} — Summary",
            "bullets": article.get("summary_bullets", [article["summary"]]),
            "key_takeaway": article["summary"],
            "important_rules": article.get("important_rules", [])
        }
