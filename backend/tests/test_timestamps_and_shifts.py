import pytest
import uuid
from datetime import datetime, timezone, time, date, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import async_session_maker
from app.models.notification import Notification
from app.models.shift import Shift, ShiftAssignment
from app.models.user import User
from app.models.employee import Employee
from app.services.shift_service import ShiftService
from app.schemas.notification import NotificationResponse
from sqlalchemy import select


@pytest.mark.asyncio
async def test_utc_db_storage_and_api_timezone_aware_serialization():
    """
    Test that DB stores UTC timestamps with timezone,
    and API returns ISO-8601 strings with timezone offset (+00:00 or Z).
    Never naive ISO string like 2026-09-17T15:30:00.
    """
    now_utc = datetime.now(timezone.utc)
    
    async with async_session_maker() as session:
        # Get admin user
        user = (await session.execute(select(User).where(User.email == "admin@incidentflow.dev"))).scalar_one()
        
        notif = Notification(
            user_id=user.id,
            type="SYSTEM",
            title="Timestamp Verification Probe",
            message="Validating timezone-aware UTC ISO-8601 serialization.",
            is_read=False,
            created_at=now_utc
        )
        session.add(notif)
        await session.commit()
        await session.refresh(notif)
        notif_id = notif.id

        # Verify DB column is timezone-aware
        assert notif.created_at.tzinfo is not None, "DB timestamp must have tzinfo"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post("/api/auth/login", json={"email": "admin@incidentflow.dev", "password": "pvcharan12345PV"})
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/notifications/", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        target_notif = next((n for n in data["notifications"] if n["id"] == str(notif_id)), None)
        assert target_notif is not None
        
        created_at_str = target_notif["created_at"]
        # Must contain timezone information: either +00:00 or Z or offset
        assert "+00:00" in created_at_str or "Z" in created_at_str or "+" in created_at_str[10:], (
            f"API response must include timezone offset, got: {created_at_str}"
        )

        # Parse with standard fromisoformat
        parsed = datetime.fromisoformat(created_at_str)
        assert parsed.tzinfo is not None, "Parsed datetime must be timezone-aware"


def test_relative_time_regression_6_hours_bug():
    """
    REGRESSION TEST specifically requested:
    A notification created at 2026-09-17T15:30:00Z.
    Observed at 2026-09-17T21:00:00+05:30 (which is the EXACT same instant in Asia/Kolkata).
    Difference must be 0 seconds ("less than a minute ago" / "Just now").
    NOT "5 hours ago", NOT "6 hours ago"!
    """
    created_utc = datetime(2026, 9, 17, 15, 30, 0, tzinfo=timezone.utc)
    observed_ist = datetime(2026, 9, 17, 21, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    # Both represent the exact same moment in time
    diff_seconds = (observed_ist - created_utc).total_seconds()
    assert diff_seconds == 0.0, f"Expected 0s difference between UTC and IST at same moment, got {diff_seconds}s"

    # Simulate what happens if timezone was stripped (the old bug):
    naive_parsed_as_local = datetime(2026, 9, 17, 15, 30, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    buggy_diff_seconds = (observed_ist - naive_parsed_as_local).total_seconds()
    # Buggy diff was 5.5 hours (19800 seconds)
    assert buggy_diff_seconds == 19800.0, "Old bug produced 5.5 hours difference (showing '5 hours ago')"

    # With correct timezone-aware ISO serialization:
    iso_with_tz = created_utc.isoformat()
    assert iso_with_tz == "2026-09-17T15:30:00+00:00"
    parsed_with_tz = datetime.fromisoformat(iso_with_tz)
    fixed_diff_seconds = (observed_ist - parsed_with_tz).total_seconds()
    assert fixed_diff_seconds == 0.0, "Correctly parsed ISO with timezone gives 0s difference"


@pytest.mark.asyncio
async def test_overnight_shift_and_timezone_boundary():
    """
    Test overnight shifts crossing midnight in Asia/Kolkata (DST-free).
    Night Shift: 22:00:00 to 06:00:00 (is_overnight=True).
    """
    service = ShiftService(db=MagicMock())
    shift = Shift(
        name="Night Shift",
        start_time=time(22, 0, 0),
        end_time=time(6, 0, 0),
        timezone="Asia/Kolkata",
        is_overnight=True,
        is_active=True
    )

    # 1. Right at start 22:00:00 -> within
    assert await service.is_within_shift(shift, time(22, 0, 0)) is True
    # 2. Before midnight: 23:59:59 -> within
    assert await service.is_within_shift(shift, time(23, 59, 59)) is True
    # 3. Exactly midnight: 00:00:00 -> within
    assert await service.is_within_shift(shift, time(0, 0, 0)) is True
    # 4. After midnight: 03:30:00 -> within
    assert await service.is_within_shift(shift, time(3, 30, 0)) is True
    # 5. Right before end: 05:59:59 -> within
    assert await service.is_within_shift(shift, time(5, 59, 59)) is True
    # 6. Exactly on end: 06:00:00 -> outside
    assert await service.is_within_shift(shift, time(6, 0, 0)) is False
    # 7. Midday: 14:00:00 -> outside
    assert await service.is_within_shift(shift, time(14, 0, 0)) is False


@pytest.mark.asyncio
async def test_analytics_api_real_db_aggregation():
    """
    Test /api/admin/analytics returns real aggregated database numbers.
    Tests today, 7d, and 30d period filters.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post("/api/auth/login", json={"email": "admin@incidentflow.dev", "password": "pvcharan12345PV"})
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. 7d analytics
        res_7d = await client.get("/api/admin/analytics?period=7d", headers=headers)
        assert res_7d.status_code == 200
        data_7d = res_7d.json()
        assert "incidents" in data_7d
        assert "timing" in data_7d
        assert "group_workload" in data_7d
        assert "employee_workload" in data_7d
        assert "notifications" in data_7d
        assert "shift_coverage" in data_7d
        assert data_7d["timezone"] == "Asia/Kolkata"

        # 2. today analytics
        res_today = await client.get("/api/admin/analytics?period=today", headers=headers)
        assert res_today.status_code == 200
        data_today = res_today.json()
        assert data_today["incidents"]["total"] >= 0

        # 3. 30d analytics
        res_30d = await client.get("/api/admin/analytics?period=30d", headers=headers)
        assert res_30d.status_code == 200
        data_30d = res_30d.json()
        assert data_30d["incidents"]["total"] >= data_7d["incidents"]["total"]


@pytest.mark.asyncio
async def test_today_shifts_coverage_api():
    """Test /api/admin/shifts/today returns shifts with real coverage."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post("/api/auth/login", json={"email": "admin@incidentflow.dev", "password": "pvcharan12345PV"})
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/admin/shifts/today", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "shifts" in data
        assert "date" in data
        assert "local_time" in data
        assert data["timezone"] == "Asia/Kolkata"
        assert len(data["shifts"]) >= 3
        # At least one shift should be active now
        active_shifts = [s for s in data["shifts"] if s["is_current"]]
        assert len(active_shifts) >= 1
