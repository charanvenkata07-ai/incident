import pytest
from datetime import time
from unittest.mock import MagicMock
from app.models.shift import Shift
from app.services.shift_service import ShiftService

@pytest.mark.asyncio
async def test_shift_boundary_daytime():
    service = ShiftService(db=MagicMock())
    shift = Shift(
        name="Morning Shift",
        start_time=time(9, 0, 0),
        end_time=time(12, 0, 0),
        is_overnight=False
    )
    
    # Exactly on start: 09:00:00 -> within shift
    assert await service.is_within_shift(shift, time(9, 0, 0)) is True
    # Inside: 10:17:00 -> within shift
    assert await service.is_within_shift(shift, time(10, 17, 0)) is True
    # Boundary: 11:59:59 -> within morning shift
    assert await service.is_within_shift(shift, time(11, 59, 59)) is True
    # Boundary: 12:00:00 -> outside morning shift (afternoon starts)
    assert await service.is_within_shift(shift, time(12, 0, 0)) is False
    # Before start: 08:59:59 -> outside
    assert await service.is_within_shift(shift, time(8, 59, 59)) is False

@pytest.mark.asyncio
async def test_shift_boundary_overnight():
    service = ShiftService(db=MagicMock())
    shift = Shift(
        name="Night Shift",
        start_time=time(22, 0, 0),
        end_time=time(6, 0, 0),
        is_overnight=True
    )
    
    # 22:00:00 -> within shift
    assert await service.is_within_shift(shift, time(22, 0, 0)) is True
    # 23:30:00 -> within shift
    assert await service.is_within_shift(shift, time(23, 30, 0)) is True
    # 02:00:00 -> within shift
    assert await service.is_within_shift(shift, time(2, 0, 0)) is True
    # 05:59:59 -> within shift
    assert await service.is_within_shift(shift, time(5, 59, 59)) is True
    # 06:00:00 -> outside shift
    assert await service.is_within_shift(shift, time(6, 0, 0)) is False
    # 15:00:00 -> outside shift
    assert await service.is_within_shift(shift, time(15, 0, 0)) is False
