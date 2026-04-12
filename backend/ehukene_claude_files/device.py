"""
Schemas Pydantic — dispositivos.
Cubre registro, listado y detalle con last_metrics.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# POST /api/devices/register
# ---------------------------------------------------------------------------

class DeviceRegisterRequest(BaseModel):
    hostname: str = Field(
        ...,
        max_length=255,
        pattern=r"^[\x20-\x7E]+$",  # solo ASCII imprimible
        description="Nombre del equipo. Solo ASCII.",
    )
    requested_by: str | None = Field(
        default=None,
        max_length=255,
        description="Usuario que solicita el registro. Solo informativo.",
    )


class DeviceRegisterResponse(BaseModel):
    device_id: uuid.UUID
    hostname: str
    api_key: str  # devuelta solo en esta respuesta, nunca más
    created_at: datetime


# ---------------------------------------------------------------------------
# GET /api/devices  — ítem de la lista
# ---------------------------------------------------------------------------

class DeviceListItem(BaseModel):
    device_id: uuid.UUID
    hostname: str
    first_seen: datetime
    last_seen: datetime
    active: bool
    agent_version: str | None

    model_config = {"from_attributes": True}


class DeviceListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    devices: list[DeviceListItem]


# ---------------------------------------------------------------------------
# GET /api/devices/{device_id}  — detalle con last_metrics
# ---------------------------------------------------------------------------

class LastBatteryMetrics(BaseModel):
    health_percent: float
    battery_status: int | None
    recorded_at: datetime


class LastSoftwareUsageItem(BaseModel):
    software_name: str
    installed: bool
    version: str | None
    last_execution: datetime | None
    executions_30d: int
    executions_60d: int
    executions_90d: int
    recorded_at: datetime


class LastBootMetrics(BaseModel):
    last_boot_time: datetime
    boot_duration_seconds: int | None
    recorded_at: datetime


class LastMetrics(BaseModel):
    battery: LastBatteryMetrics | None = None
    software_usage: list[LastSoftwareUsageItem] = Field(default_factory=list)
    boot_time: LastBootMetrics | None = None


class DeviceDetailResponse(BaseModel):
    device_id: uuid.UUID
    hostname: str
    first_seen: datetime
    last_seen: datetime
    active: bool
    agent_version: str | None
    last_metrics: LastMetrics
