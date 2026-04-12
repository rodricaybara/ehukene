"""
Schemas Pydantic — dispositivos.
Cubre registro, listado y detalle con last_metrics.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    hostname: str = Field(
        ...,
        max_length=255,
        pattern=r"^[\x20-\x7E]+$",
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
    api_key: str
    created_at: datetime


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


class LastDiskUsageItem(BaseModel):
    drive_letter: str
    volume_name: str | None
    filesystem: str | None
    total_capacity_gb: float
    free_capacity_gb: float
    used_capacity_gb: float
    used_percent: float
    recorded_at: datetime


class LastMetrics(BaseModel):
    battery: LastBatteryMetrics | None = None
    software_usage: list[LastSoftwareUsageItem] = Field(default_factory=list)
    boot_time: LastBootMetrics | None = None
    disk_usage: list[LastDiskUsageItem] = Field(default_factory=list)


class DeviceDetailResponse(BaseModel):
    device_id: uuid.UUID
    hostname: str
    first_seen: datetime
    last_seen: datetime
    active: bool
    agent_version: str | None
    last_metrics: LastMetrics
