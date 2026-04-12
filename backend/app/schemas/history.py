"""
Schemas Pydantic — histórico de métricas por dispositivo.
GET /api/devices/{device_id}/history
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class BatteryHistoryItem(BaseModel):
    recorded_at: datetime
    health_percent: float
    battery_status: int | None


class BootHistoryItem(BaseModel):
    recorded_at: datetime
    last_boot_time: datetime
    boot_duration_seconds: int | None


class SoftwareHistoryItem(BaseModel):
    recorded_at: datetime
    software_name: str
    installed: bool
    version: str | None
    last_execution: datetime | None
    executions_30d: int
    executions_60d: int
    executions_90d: int


class HistoryData(BaseModel):
    battery: list[BatteryHistoryItem] = []
    boot_time: list[BootHistoryItem] = []
    software_usage: list[SoftwareHistoryItem] = []


class HistoryResponse(BaseModel):
    device_id: uuid.UUID
    from_: datetime
    to: datetime
    history: HistoryData

    model_config = {"populate_by_name": True}
