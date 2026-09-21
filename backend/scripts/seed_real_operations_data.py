"""
IncidentFlow — Real Production Operations Data Seeder
Seeds:
- 10 Real Operational Groups with work domains & ServiceNow group mappings
- 100 Employees (10 per group) with realistic internal test identities
- Admin-managed Task Catalog (4+ task templates per group)
- 3 Shifts covering 24/7 (Morning 06-14, Evening 14-22, Night 22-06 overnight) in Asia/Kolkata
- Rotating shift assignments with normal coverage of 1-2 active workers per group
- Idempotent: safe to run multiple times without duplicating records
"""
import asyncio
import uuid
from datetime import time, date, datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, update
from app.core.database import async_session_maker, Base, engine
from app.core.security import hash_password
from app.models.user import User
from app.models.team import Team
from app.models.employee import Employee
from app.models.skill import Skill, EmployeeSkill
from app.models.shift import Shift, ShiftAssignment
from app.models.presence import PresenceRecord
from app.models.task_template import TaskTemplate
from app.models.settings import SystemSetting
from app.models.team_rotation import TeamRotation

# ---------------------------------------------------------------------------
# 10 Groups Definition
# ---------------------------------------------------------------------------
GROUPS_SPEC = [
    {
        "slug": "mdm_l3",
        "name": "MDM L3",
        "code_prefix": "MDM",
        "work_domain": "Master Data Management",
        "description": "Enterprise master data entity resolution, golden record governance and syndication.",
        "sn_group": "sn_mdm_l3_ops",
        "tasks": [
            ("Validate master data record", "Verify attribute uniqueness, business rules, and foreign key integrity.", "P3"),
            ("Investigate data synchronization failure", "Diagnose batch sync failure between SAP/MDM and downstream data lake.", "P2"),
            ("Correct master-data mapping", "Fix schema attribute mapping drift and re-trigger pipeline ingest.", "P3"),
            ("Validate MDM integration", "Perform health probe on REST and Kafka MDM publication endpoints.", "P3"),
        ],
        "skills": ["MDM", "SQL", "Data Governance", "Python", "ETL"]
    },
    {
        "slug": "db_l2",
        "name": "Database L2",
        "code_prefix": "DB",
        "work_domain": "Database Operations & Support",
        "description": "High availability database administration, clustering, connection pool and replica support.",
        "sn_group": "sn_database_l2_ops",
        "tasks": [
            ("Investigate database connectivity", "Probe listener availability, verify active socket limits, and test latency.", "P2"),
            ("Check database service health", "Review query lock graph, deadlocks, and buffer cache hit ratio.", "P3"),
            ("Analyze database errors", "Inspect error logs for ORA/PG deadlocks, corrupt blocks, or tablespace exhaustion.", "P2"),
            ("Validate connection pool", "Inspect pgpool/HikariCP pool saturation and recycle idle connections.", "P3"),
        ],
        "skills": ["SQL", "PostgreSQL", "Oracle", "Performance Tuning", "Replication"]
    },
    {
        "slug": "net_l2",
        "name": "Network L2",
        "code_prefix": "NET",
        "work_domain": "Network Operations & Support",
        "description": "Enterprise routing, switching, SD-WAN, BGP peering and interface latency troubleshooting.",
        "sn_group": "sn_network_l2_ops",
        "tasks": [
            ("Investigate network connectivity", "Trace packet path across core gateways, check MTU and firewall rules.", "P2"),
            ("Check interface status", "Inspect switch port flap counters, CRC errors, and duplex mismatches.", "P3"),
            ("Validate routing", "Verify BGP/OSPF peer convergence and route table advertisements.", "P2"),
            ("Analyze packet-loss alert", "Perform continuous probe across WAN transit to isolate transit hop drops.", "P2"),
        ],
        "skills": ["Routing", "Switching", "BGP", "Firewalls", "SD-WAN"]
    },
    {
        "slug": "linux_l2",
        "name": "Linux L2",
        "code_prefix": "LIN",
        "work_domain": "Linux / Server Operations",
        "description": "RHEL, Ubuntu and Debian server performance, systemd services, kernel alerts and storage.",
        "sn_group": "sn_linux_l2_ops",
        "tasks": [
            ("Check server health", "Evaluate CPU load averages, iowait percentages, and thermal throttling.", "P3"),
            ("Investigate service failure", "Analyze journalctl logs, core dumps, and restart failed systemd unit.", "P2"),
            ("Analyze system logs", "Grep /var/log/messages for kernel OOM-killer invocations or disk I/O timeouts.", "P2"),
            ("Check disk/resource utilization", "Inspect LVM volume utilization, inodes, and clean temp directories.", "P3"),
        ],
        "skills": ["Linux", "Bash", "Kernel", "Systemd", "LVM"]
    },
    {
        "slug": "win_l2",
        "name": "Windows L2",
        "code_prefix": "WIN",
        "work_domain": "Windows Infrastructure Support",
        "description": "Active Directory, Group Policy, Windows Server roles, IIS, and Windows cluster support.",
        "sn_group": "sn_windows_l2_ops",
        "tasks": [
            ("Investigate Windows service", "Diagnose hung service, check process handle leaks, and cycle safely.", "P3"),
            ("Check event logs", "Filter System and Application event logs for Event IDs 7000, 1000, and 4625.", "P3"),
            ("Validate server availability", "Test RPC, WinRM, and WMI connectivity to target server instance.", "P3"),
            ("Troubleshoot authentication/service issue", "Verify Kerberos ticket issuance, SPNs, and clock drift.", "P2"),
        ],
        "skills": ["Windows Server", "Active Directory", "PowerShell", "IIS", "Hyper-V"]
    },
    {
        "slug": "cloud_l2",
        "name": "Cloud Operations L2",
        "code_prefix": "CLOUD",
        "work_domain": "Cloud Infrastructure & Operations",
        "description": "AWS, GCP and Azure cloud resources, autoscaling groups, IAM permissions and VPC transit.",
        "sn_group": "sn_cloud_ops_l2",
        "tasks": [
            ("Check cloud resource health", "Review cloud provider status dashboard and regional metric alarms.", "P3"),
            ("Investigate deployment/resource failure", "Analyze cloud-init logs, Terraform apply states, and instance lifecycle.", "P2"),
            ("Validate service availability", "Verify Cloud Load Balancer target group health and SSL termination.", "P2"),
            ("Analyze cloud alert", "Inspect CloudWatch / Stackdriver metrics for billing or API rate-limit alarms.", "P3"),
        ],
        "skills": ["AWS", "GCP", "Kubernetes", "Terraform", "Docker"]
    },
    {
        "slug": "app_l2",
        "name": "Application Support L2",
        "code_prefix": "APP",
        "work_domain": "Application Support & Troubleshooting",
        "description": "Tier 2 enterprise application runtime, API gateways, microservices and middleware logs.",
        "sn_group": "sn_app_support_l2",
        "tasks": [
            ("Investigate application error", "Examine stack traces, identify unhandled HTTP 500 exceptions and request IDs.", "P2"),
            ("Check application logs", "Correlate distributed trace spans across upstream gateway and downstream services.", "P3"),
            ("Validate service health", "Perform synthetic health check probes against /health and /ready endpoints.", "P3"),
            ("Troubleshoot application failure", "Inspect heap memory dumps, garbage collection pauses, and thread pool exhaustion.", "P2"),
        ],
        "skills": ["Java", "Node.js", "Python", "APM", "REST APIs"]
    },
    {
        "slug": "sec_l2",
        "name": "Security Operations L2",
        "code_prefix": "SEC",
        "work_domain": "Security Monitoring & Incident Response",
        "description": "SOC tier 2 SIEM monitoring, malware isolation, credential compromise and firewall security events.",
        "sn_group": "sn_security_ops_l2",
        "tasks": [
            ("Investigate security alert", "Triage high-confidence SIEM detection, verify source IP reputation and blast radius.", "P1"),
            ("Validate suspicious activity", "Analyze user behavior analytics (UBA) anomaly on anomalous geo-logins.", "P2"),
            ("Review security event", "Correlate EDR endpoint events with network telemetry to identify lateral movement.", "P2"),
            ("Escalate confirmed security incident", "Execute containment playbook, isolate host from VLAN, and notify CISO team.", "P1"),
        ],
        "skills": ["SIEM", "EDR", "Incident Response", "Network Security", "Threat Hunting"]
    },
    {
        "slug": "storage_l2",
        "name": "Storage & Backup L2",
        "code_prefix": "STOR",
        "work_domain": "Storage, Backup & Recovery Operations",
        "description": "SAN/NAS storage arrays, snapshot schedules, tape/cloud backup pools and recovery verification.",
        "sn_group": "sn_storage_backup_l2",
        "tasks": [
            ("Investigate storage alert", "Inspect SAN LUN latency, multipath failover state, and deduplication engine.", "P2"),
            ("Validate backup status", "Review catalog for overnight backup job completion and verify image hash.", "P3"),
            ("Check storage capacity", "Analyze thin-provisioning exhaustion projection and expand storage pool.", "P3"),
            ("Investigate backup failure", "Identify VSS writer timeout or network transport bottleneck on failed node.", "P2"),
        ],
        "skills": ["SAN", "NAS", "Backup Exec", "NetApp", "Disaster Recovery"]
    },
    {
        "slug": "mon_l2",
        "name": "Monitoring & Batch L2",
        "code_prefix": "MON",
        "work_domain": "Monitoring, Alerts & Batch Operations",
        "description": "Enterprise alert triage, Prometheus/Grafana, batch workload schedulers, AutoSys and cron jobs.",
        "sn_group": "sn_monitoring_batch_l2",
        "tasks": [
            ("Investigate monitoring alert", "Correlate telemetry storm with recent deployments or infrastructure changes.", "P3"),
            ("Check batch job status", "Inspect scheduler queue, dependencies, and upstream trigger readiness.", "P3"),
            ("Validate scheduled job", "Verify completion code (RC=0) and downstream output artifact availability.", "P3"),
            ("Investigate failed batch execution", "Extract job stderr, identify missing input files, and re-run with override.", "P2"),
        ],
        "skills": ["Prometheus", "Grafana", "AutoSys", "Cron", "Alerting"]
    },
    {
        "slug": "devops_l2",
        "name": "DevOps & SRE L2",
        "code_prefix": "DEVOPS",
        "work_domain": "CI/CD, Build & Reliability Engineering",
        "description": "Deployment pipeline failures, container orchestrator nodes, Helm chart drifts and canary releases.",
        "sn_group": "sn_devops_sre_l2",
        "tasks": [
            ("Investigate pipeline failure", "Review runner logs, flaky test containers, and artifact registry cache.", "P2"),
            ("Check cluster node status", "Inspect node pressure, kubelet eviction status, and daemonsets.", "P2"),
            ("Validate deployment rollout", "Check replica set status, readiness probe health, and traffic splitting.", "P3"),
            ("Analyze ingress errors", "Inspect ingress controller access logs for HTTP 502/504 spikes.", "P2"),
        ],
        "skills": ["Kubernetes", "CI/CD", "Docker", "Helm", "SRE"]
    },
    {
        "slug": "iam_l2",
        "name": "Identity & Access L2",
        "code_prefix": "IAM",
        "work_domain": "Identity, Single Sign-On & Access Management",
        "description": "Okta, Azure AD SSO, OAuth/SAML token issuance, directory sync and privileged access.",
        "sn_group": "sn_iam_l2",
        "tasks": [
            ("Investigate SSO login failure", "Review SAML assertion response, clock skew, and attribute contract.", "P2"),
            ("Check directory synchronization", "Inspect SCIM provisioning queue and sync failure dead-letter queue.", "P3"),
            ("Validate MFA service", "Probe Duo/Okta Verify push notification delivery latency.", "P2"),
            ("Troubleshoot access permission", "Review RBAC role bindings, group claims, and conditional access policies.", "P3"),
        ],
        "skills": ["SAML", "OAuth", "Okta", "Active Directory", "RBAC"]
    },
    {
        "slug": "msg_l2",
        "name": "Messaging & Collaboration L2",
        "code_prefix": "MSG",
        "work_domain": "Email, Messaging & Collaboration Systems",
        "description": "Exchange Online, SMTP relays, mail flow rules, Teams/Slack webhooks and spam filtering.",
        "sn_group": "sn_messaging_collab_l2",
        "tasks": [
            ("Investigate mail flow bottleneck", "Examine transport queue length, MX record health, and TLS negotiation.", "P2"),
            ("Check spam filter quarantine", "Review false-positive quarantine rate and SPF/DKIM/DMARC alignment.", "P3"),
            ("Validate SMTP relay", "Perform synthetic mail injection probe through authenticated relay host.", "P3"),
            ("Troubleshoot webhook delivery", "Inspect collaboration webhook gateway rate-limiting and retry queues.", "P3"),
        ],
        "skills": ["SMTP", "Exchange", "SPF/DKIM", "Email Security", "Webhooks"]
    },
    {
        "slug": "api_l2",
        "name": "API Gateway L2",
        "code_prefix": "API",
        "work_domain": "API Gateways & Service Mesh",
        "description": "Kong, Envoy, Apigee API traffic management, rate-limiting, TLS termination and mutual TLS.",
        "sn_group": "sn_api_gateway_l2",
        "tasks": [
            ("Investigate gateway rate-limiting", "Review consumer tier quotas, burst limits, and Redis counter latency.", "P2"),
            ("Check upstream service latency", "Profile p99 latency across upstream target services.", "P2"),
            ("Validate certificate rotation", "Verify TLS certificate expiry across edge proxy routes.", "P3"),
            ("Analyze API error rate", "Inspect HTTP 4xx/5xx status distribution across public endpoints.", "P2"),
        ],
        "skills": ["API Gateway", "Envoy", "Kong", "mTLS", "Traffic Management"]
    },
    {
        "slug": "data_l2",
        "name": "Data Platform L2",
        "code_prefix": "DATA",
        "work_domain": "Data Pipelines, Kafka & Stream Processing",
        "description": "Kafka consumer lag, Spark streaming jobs, Snowflake/BigQuery queries and data lake partitions.",
        "sn_group": "sn_data_platform_l2",
        "tasks": [
            ("Investigate Kafka consumer lag", "Inspect consumer partition rebalance, offset commits, and broker load.", "P2"),
            ("Check streaming pipeline", "Review Flink/Spark executor task failures and checkpoint timeouts.", "P2"),
            ("Validate data lake ingest", "Verify parquet file compaction and S3 partition discovery.", "P3"),
            ("Analyze slow query alert", "Profile analytical query plan, spilling to disk, and warehouse compute size.", "P3"),
        ],
        "skills": ["Kafka", "Spark", "Data Pipelines", "SQL", "Stream Processing"]
    },
]

# ---------------------------------------------------------------------------
# First and Last Names for Realistic 150 Employees
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "Aarav", "Aditi", "Amit", "Ananya", "Arjun", "Bhavna", "Chetan", "Deepak",
    "Divya", "Gaurav", "Harsh", "Ishaan", "Kavita", "Kiran", "Manish", "Meera",
    "Naveen", "Neha", "Nikhil", "Pooja", "Pranav", "Priya", "Rahul", "Rajesh",
    "Ravi", "Rohan", "Sanjay", "Shreya", "Sneha", "Suresh", "Tanvi", "Varun",
    "Vikram", "Yash", "Zoya", "Alok", "Anita", "Ashwin", "Dev", "Gayatri"
]
LAST_NAMES = [
    "Kumar", "Patel", "Reddy", "Sharma", "Verma", "Singh", "Nair", "Iyer",
    "Joshi", "Mehta", "Rao", "Deshmukh", "Chopra", "Bhatia", "Saxena", "Menon"
]


async def seed_real_operations():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        # ------------------------------------------------------------------
        # 1. Admin & Supervisor Accounts
        # ------------------------------------------------------------------
        default_pwd_hash = hash_password("pvcharan12345")
        admin_pwd_hash = hash_password("pvcharan12345PV")
        super_pwd_hash = hash_password("pvcharan12345PV")

        # Primary Admin Account
        pvc_admin_res = await session.execute(select(User).where(User.email == "pvcharan975@gmail.com"))
        pvc_admin = pvc_admin_res.scalar_one_or_none()
        if not pvc_admin:
            pvc_admin = User(
                email="pvcharan975@gmail.com",
                hashed_password=admin_pwd_hash,
                full_name="Administrator (pvcharan975)",
                role="ADMIN",
                is_active=True
            )
            session.add(pvc_admin)
        else:
            pvc_admin.role = "ADMIN"
            pvc_admin.is_active = True
            pvc_admin.hashed_password = admin_pwd_hash

        admin_res = await session.execute(select(User).where(User.email == "admin@incidentflow.dev"))
        admin = admin_res.scalar_one_or_none()
        if not admin:
            admin = User(
                email="admin@incidentflow.dev",
                hashed_password=admin_pwd_hash,
                full_name="Administrator (Ops Lead)",
                role="ADMIN",
                is_active=True
            )
            session.add(admin)
        else:
            admin.role = "ADMIN"
            admin.is_active = True
            admin.hashed_password = admin_pwd_hash

        sup_res = await session.execute(select(User).where(User.email == "supervisor@incidentflow.dev"))
        sup = sup_res.scalar_one_or_none()
        if not sup:
            session.add(User(
                email="supervisor@incidentflow.dev",
                hashed_password=super_pwd_hash,
                full_name="Operations Supervisor",
                role="SUPERVISOR",
                is_active=True
            ))
        else:
            sup.role = "SUPERVISOR"
            sup.is_active = True
            sup.hashed_password = super_pwd_hash

        # ------------------------------------------------------------------
        # 2. Shifts Configuration (Asia/Kolkata, 24/7 Coverage)
        # ------------------------------------------------------------------
        shifts_spec = [
            {"name": "Morning Shift (Shift A)", "start_time": time(6, 0), "end_time": time(14, 0), "is_overnight": False},
            {"name": "Evening Shift (Shift B)", "start_time": time(14, 0), "end_time": time(22, 0), "is_overnight": False},
            {"name": "Night Shift (Shift C)", "start_time": time(22, 0), "end_time": time(6, 0), "is_overnight": True},
        ]
        shifts = {}
        for s in shifts_spec:
            res = await session.execute(select(Shift).where(Shift.name == s["name"]))
            existing = res.scalar_one_or_none()
            if not existing:
                existing = Shift(
                    name=s["name"],
                    start_time=s["start_time"],
                    end_time=s["end_time"],
                    timezone="Asia/Kolkata",
                    is_overnight=s["is_overnight"],
                    is_active=True
                )
                session.add(existing)
                await session.flush()
            shifts[s["name"]] = existing

        # ------------------------------------------------------------------
        # 3. Global Skills Catalog
        # ------------------------------------------------------------------
        all_skill_names = set()
        for g in GROUPS_SPEC:
            all_skill_names.update(g["skills"])

        skills_map = {}
        for sname in all_skill_names:
            res = await session.execute(select(Skill).where(Skill.name == sname))
            sk = res.scalar_one_or_none()
            if not sk:
                sk = Skill(name=sname, description=f"Technical capability in {sname}", is_active=True)
                session.add(sk)
                await session.flush()
            skills_map[sname] = sk

        # ------------------------------------------------------------------
        # 4. 10 Groups + 10 Employees Per Group (100 total) + Task Catalog
        # ------------------------------------------------------------------
        tz = ZoneInfo("Asia/Kolkata")
        today = datetime.now(tz).date()
        now_time = datetime.now(tz).time()

        # Determine which shift is currently active
        curr_active_shift_name = "Night Shift (Shift C)"
        if time(6, 0) <= now_time < time(14, 0):
            curr_active_shift_name = "Morning Shift (Shift A)"
        elif time(14, 0) <= now_time < time(22, 0):
            curr_active_shift_name = "Evening Shift (Shift B)"

        name_cursor = 0
        total_employees_seeded = 0

        for g_idx, g_spec in enumerate(GROUPS_SPEC, start=1):
            # 4a. Create or update Team
            t_res = await session.execute(select(Team).where(Team.name == g_spec["name"]))
            team = t_res.scalar_one_or_none()
            if not team:
                team = Team(
                    name=g_spec["name"],
                    description=g_spec["description"],
                    work_domain=g_spec["work_domain"],
                    servicenow_group_id=g_spec["sn_group"],
                    is_active=True
                )
                session.add(team)
                await session.flush()
            else:
                team.work_domain = g_spec["work_domain"]
                team.description = g_spec["description"]
                team.servicenow_group_id = g_spec["sn_group"]
                team.is_active = True
                await session.flush()

            # 4b. Seed Task Catalog for this group
            for t_title, t_desc, t_prio in g_spec["tasks"]:
                task_res = await session.execute(
                    select(TaskTemplate).where(
                        TaskTemplate.team_id == team.id,
                        TaskTemplate.title == t_title
                    )
                )
                if not task_res.scalar_one_or_none():
                    session.add(TaskTemplate(
                        team_id=team.id,
                        title=t_title,
                        description=t_desc,
                        priority=t_prio,
                        is_active=True
                    ))

            # 4c. Create exactly 10 Employees for this group
            team_emp_ids = []
            for emp_num in range(1, 11):
                if g_spec["slug"] == "db_l2" and emp_num == 1:
                    email = "ravi@incidentflow.dev"
                    full_name = f"Ravi Kumar ({g_spec['name']} #1)"
                elif g_spec["slug"] == "db_l2" and emp_num == 2:
                    email = "kiran@incidentflow.dev"
                    full_name = f"Kiran Patel ({g_spec['name']} #2)"
                elif g_spec["slug"] == "db_l2" and emp_num == 3:
                    email = "suresh@incidentflow.dev"
                    full_name = f"Suresh Patel ({g_spec['name']} #3)"
                else:
                    email = f"{g_spec['slug']}_{emp_num:02d}@incidentflow.dev"
                    fname = FIRST_NAMES[name_cursor % len(FIRST_NAMES)]
                    lname = LAST_NAMES[(name_cursor // len(FIRST_NAMES)) % len(LAST_NAMES)]
                    full_name = f"{fname} {lname} ({g_spec['name']} #{emp_num})"
                    name_cursor += 1

                # User account
                u_res = await session.execute(select(User).where(User.email == email))
                u = u_res.scalar_one_or_none()
                if not u:
                    u = User(
                        email=email,
                        hashed_password=default_pwd_hash,
                        full_name=full_name,
                        role="EMPLOYEE",
                        is_active=True
                    )
                    session.add(u)
                    await session.flush()
                else:
                    u.is_active = True
                    u.full_name = full_name
                    u.role = "EMPLOYEE"
                    u.hashed_password = default_pwd_hash

                # Canonical employee code: exactly Prefix + 3-digit number (e.g. DB001..DB010)
                canonical_emp_code = f"{g_spec['code_prefix']}{emp_num:03d}"

                # Free up canonical code if held by a different employee
                code_conflict = (await session.execute(
                    select(Employee).where(
                        Employee.employee_code == canonical_emp_code,
                        Employee.user_id != u.id
                    )
                )).scalar_one_or_none()
                if code_conflict:
                    code_conflict.employee_code = f"OLD_{canonical_emp_code}_{str(code_conflict.id)[:6]}"
                    await session.flush()

                # Employee record
                e_res = await session.execute(select(Employee).where(Employee.user_id == u.id))
                emp = e_res.scalar_one_or_none()
                if not emp:
                    emp = Employee(
                        user_id=u.id,
                        team_id=team.id,
                        employee_code=canonical_emp_code,
                        availability_status="AVAILABLE",
                        is_present=True,
                        is_group_leader=(emp_num == 1)
                    )
                    session.add(emp)
                    await session.flush()
                else:
                    emp.team_id = team.id
                    emp.employee_code = canonical_emp_code
                    emp.availability_status = "AVAILABLE"
                    emp.is_present = True
                    emp.is_group_leader = (emp_num == 1)

                team_emp_ids.append(emp.id)
                total_employees_seeded += 1

                # Link primary skills
                for sname in g_spec["skills"][:3]:
                    sk = skills_map[sname]
                    esk_res = await session.execute(
                        select(EmployeeSkill).where(
                            EmployeeSkill.employee_id == emp.id,
                            EmployeeSkill.skill_id == sk.id
                        )
                    )
                    if not esk_res.scalar_one_or_none():
                        session.add(EmployeeSkill(employee_id=emp.id, skill_id=sk.id, proficiency_level=2))

                # --------------------------------------------------------------
                # 4d. Mandatory Shift Coverage Across All 10 Employees
                # --------------------------------------------------------------
                # Emp 1, 2, 3, 4 -> Shift A (Morning 06-14)
                # Emp 5, 6, 7    -> Shift B (Evening 14-22)
                # Emp 8, 9, 10   -> Shift C (Night 22-06)
                if emp_num in (1, 2, 3, 4):
                    assigned_shift = shifts["Morning Shift (Shift A)"]
                elif emp_num in (5, 6, 7):
                    assigned_shift = shifts["Evening Shift (Shift B)"]
                else:
                    assigned_shift = shifts["Night Shift (Shift C)"]

                sa_res = await session.execute(
                    select(ShiftAssignment).where(
                        ShiftAssignment.shift_id == assigned_shift.id,
                        ShiftAssignment.employee_id == emp.id,
                        ShiftAssignment.date == today
                    )
                )
                sa = sa_res.scalar_one_or_none()
                if not sa:
                    sa = ShiftAssignment(
                        shift_id=assigned_shift.id,
                        employee_id=emp.id,
                        date=today,
                        is_active=True
                    )
                    session.add(sa)
                    await session.flush()
                else:
                    sa.is_active = True

                # All active employees are compulsorily available and present
                emp.is_present = True
                emp.availability_status = "AVAILABLE"

                p_res = await session.execute(
                    select(PresenceRecord).where(
                        PresenceRecord.employee_id == emp.id,
                        PresenceRecord.date == today
                    )
                )
                if not p_res.scalar_one_or_none():
                    session.add(PresenceRecord(
                        employee_id=emp.id,
                        shift_assignment_id=sa.id,
                        status="CHECKED_IN",
                        checked_in_at=datetime.now(timezone.utc),
                        date=today
                    ))

            # Enforce exactly 10 active employees: unassign any extra employees from this team
            if team_emp_ids:
                await session.execute(
                    update(Employee)
                    .where(
                        Employee.team_id == team.id,
                        ~Employee.id.in_(team_emp_ids)
                    )
                    .values(team_id=None)
                )

            # Ensure TeamRotation record exists
            tr_res = await session.execute(select(TeamRotation).where(TeamRotation.team_id == team.id))
            tr = tr_res.scalar_one_or_none()
            if not tr:
                tr = TeamRotation(
                    team_id=team.id,
                    current_position=1,
                    cycle_number=1,
                    last_assigned_employee_id=None,
                    last_incident_id=None,
                    last_idempotency_key=None,
                )
                session.add(tr)

        # Deactivate any teams not in GROUPS_SPEC (e.g. legacy Analytics team)
        active_team_names = [g["name"] for g in GROUPS_SPEC]
        await session.execute(
            update(Team)
            .where(~Team.name.in_(active_team_names))
            .values(is_active=False)
        )

        await session.commit()
        print(f"Successfully seeded {len(GROUPS_SPEC)} Operational Groups, {total_employees_seeded} Employees, Task Catalogs, and Shift Coverage!")


if __name__ == "__main__":
    asyncio.run(seed_real_operations())
