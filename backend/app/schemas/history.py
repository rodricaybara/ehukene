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


class DiskUsageHistoryItem(BaseModel):
    recorded_at: datetime
    drive_letter: str
    volume_name: str | None
    filesystem: str | None
    total_capacity_gb: float
    free_capacity_gb: float
    used_capacity_gb: float
    used_percent: float


class HealthCpuHistoryItem(BaseModel):
    recorded_at: datetime
    load_percentage: float | None
    status: str
    error_msg: str | None


class HealthMemoryHistoryItem(BaseModel):
    recorded_at: datetime
    total_kb: int | None
    free_kb: int | None
    usage_pct: float | None
    status: str
    error_msg: str | None


class HealthDiskHistoryItem(BaseModel):
    recorded_at: datetime
    drive: str | None
    total_gb: float | None
    free_gb: float | None
    free_pct: float | None
    status: str
    error_msg: str | None


class HealthEventSourceHistoryItem(BaseModel):
    provider: str
    count: int


class HealthSampleEventHistoryItem(BaseModel):
    event_id: int
    provider: str
    level: str
    time_created: datetime


class HealthEventsHistoryItem(BaseModel):
    recorded_at: datetime
    critical_count: int
    error_count: int
    filtered_count: int
    top_sources: list[HealthEventSourceHistoryItem] = []
    sample_events: list[HealthSampleEventHistoryItem] = []
    status: str
    error_msg: str | None


class HealthDomainHistoryItem(BaseModel):
    recorded_at: datetime
    secure_channel: bool
    status: str
    error_msg: str | None


class HealthUptimeHistoryItem(BaseModel):
    recorded_at: datetime
    last_boot: datetime | None
    days: float | None
    status: str
    error_msg: str | None


class HealthBootTimeHistoryItem(BaseModel):
    recorded_at: datetime
    last_boot_time: datetime | None
    boot_duration_seconds: int | None
    source: str | None
    status: str
    error_msg: str | None


class HealthServiceHistoryItem(BaseModel):
    recorded_at: datetime
    service_name: str
    display_name: str | None
    state: str
    startup_type: str | None
    tier: int
    status: str


class HistoryData(BaseModel):
    battery: list[BatteryHistoryItem] = []
    boot_time: list[BootHistoryItem] = []
    software_usage: list[SoftwareHistoryItem] = []
    disk_usage: list[DiskUsageHistoryItem] = []
    health_cpu: list[HealthCpuHistoryItem] = []
    health_memory: list[HealthMemoryHistoryItem] = []
    health_disk: list[HealthDiskHistoryItem] = []
    health_events: list[HealthEventsHistoryItem] = []
    health_domain: list[HealthDomainHistoryItem] = []
    health_uptime: list[HealthUptimeHistoryItem] = []
    health_boot_time: list[HealthBootTimeHistoryItem] = []
    health_services: list[HealthServiceHistoryItem] = []


class HistoryResponse(BaseModel):
    device_id: uuid.UUID
    from_: datetime
    to: datetime
    history: HistoryData

    model_config = {"populate_by_name": True}
