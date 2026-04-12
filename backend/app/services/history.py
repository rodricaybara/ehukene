"""
Servicio de histórico — EHUkene Backend.
Queries para GET /api/devices/{device_id}/history y GET /api/devices/{device_id}.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.battery_metrics import BatteryMetric
from app.models.boot_metrics import BootMetric
from app.models.disk_usage import DiskUsage
from app.models.software_usage import SoftwareUsage
from app.schemas.device import (
    LastBatteryMetrics,
    LastBootMetrics,
    LastDiskUsageItem,
    LastMetrics,
    LastSoftwareUsageItem,
)
from app.schemas.history import (
    BatteryHistoryItem,
    BootHistoryItem,
    DiskUsageHistoryItem,
    HistoryData,
    SoftwareHistoryItem,
)


# ---------------------------------------------------------------------------
# last_metrics para GET /api/devices/{device_id}
# ---------------------------------------------------------------------------

async def get_last_metrics(device_id: uuid.UUID, db: AsyncSession) -> LastMetrics:
    """Devuelve las últimas métricas conocidas de un dispositivo."""

    # Batería
    battery_row = (
        await db.execute(
            select(BatteryMetric)
            .where(BatteryMetric.device_id == device_id)
            .order_by(BatteryMetric.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    last_battery = None
    if battery_row:
        last_battery = LastBatteryMetrics(
            health_percent=float(battery_row.health_percent),
            battery_status=battery_row.battery_status,
            recorded_at=battery_row.recorded_at,
        )

    # Software — último registro por cada software_name
    # Se obtienen todos los registros del último recorded_at del dispositivo
    last_sw_ts = (
        await db.execute(
            select(SoftwareUsage.recorded_at)
            .where(SoftwareUsage.device_id == device_id)
            .order_by(SoftwareUsage.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    last_software: list[LastSoftwareUsageItem] = []
    if last_sw_ts:
        sw_rows = (
            await db.execute(
                select(SoftwareUsage).where(
                    SoftwareUsage.device_id == device_id,
                    SoftwareUsage.recorded_at == last_sw_ts,
                )
            )
        ).scalars().all()
        last_software = [
            LastSoftwareUsageItem(
                software_name=r.software_name,
                installed=r.installed,
                version=r.version,
                last_execution=r.last_execution,
                executions_30d=r.executions_30d,
                executions_60d=r.executions_60d,
                executions_90d=r.executions_90d,
                recorded_at=r.recorded_at,
            )
            for r in sw_rows
        ]

    # Boot time
    boot_row = (
        await db.execute(
            select(BootMetric)
            .where(BootMetric.device_id == device_id)
            .order_by(BootMetric.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    last_boot = None
    if boot_row:
        last_boot = LastBootMetrics(
            last_boot_time=boot_row.last_boot_time,
            boot_duration_seconds=boot_row.boot_duration_seconds,
            recorded_at=boot_row.recorded_at,
        )

    last_disk_ts = (
        await db.execute(
            select(DiskUsage.recorded_at)
            .where(DiskUsage.device_id == device_id)
            .order_by(DiskUsage.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    last_disk_usage: list[LastDiskUsageItem] = []
    if last_disk_ts:
        disk_rows = (
            await db.execute(
                select(DiskUsage).where(
                    DiskUsage.device_id == device_id,
                    DiskUsage.recorded_at == last_disk_ts,
                )
            )
        ).scalars().all()
        last_disk_usage = [
            LastDiskUsageItem(
                drive_letter=r.drive_letter,
                volume_name=r.volume_name,
                filesystem=r.filesystem,
                total_capacity_gb=float(r.total_capacity_gb),
                free_capacity_gb=float(r.free_capacity_gb),
                used_capacity_gb=float(r.used_capacity_gb),
                used_percent=float(r.used_percent),
                recorded_at=r.recorded_at,
            )
            for r in disk_rows
        ]

    return LastMetrics(
        battery=last_battery,
        software_usage=last_software,
        boot_time=last_boot,
        disk_usage=last_disk_usage,
    )


# ---------------------------------------------------------------------------
# Histórico por rango — GET /api/devices/{device_id}/history
# ---------------------------------------------------------------------------

async def get_battery_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[BatteryHistoryItem]:
    rows = (
        await db.execute(
            select(BatteryMetric)
            .where(
                BatteryMetric.device_id == device_id,
                BatteryMetric.recorded_at >= from_dt,
                BatteryMetric.recorded_at <= to_dt,
            )
            .order_by(BatteryMetric.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        BatteryHistoryItem(
            recorded_at=r.recorded_at,
            health_percent=float(r.health_percent),
            battery_status=r.battery_status,
        )
        for r in rows
    ]


async def get_boot_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[BootHistoryItem]:
    rows = (
        await db.execute(
            select(BootMetric)
            .where(
                BootMetric.device_id == device_id,
                BootMetric.recorded_at >= from_dt,
                BootMetric.recorded_at <= to_dt,
            )
            .order_by(BootMetric.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        BootHistoryItem(
            recorded_at=r.recorded_at,
            last_boot_time=r.last_boot_time,
            boot_duration_seconds=r.boot_duration_seconds,
        )
        for r in rows
    ]


async def get_software_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[SoftwareHistoryItem]:
    rows = (
        await db.execute(
            select(SoftwareUsage)
            .where(
                SoftwareUsage.device_id == device_id,
                SoftwareUsage.recorded_at >= from_dt,
                SoftwareUsage.recorded_at <= to_dt,
            )
            .order_by(SoftwareUsage.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        SoftwareHistoryItem(
            recorded_at=r.recorded_at,
            software_name=r.software_name,
            installed=r.installed,
            version=r.version,
            last_execution=r.last_execution,
            executions_30d=r.executions_30d,
            executions_60d=r.executions_60d,
            executions_90d=r.executions_90d,
        )
        for r in rows
    ]


async def get_disk_usage_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[DiskUsageHistoryItem]:
    rows = (
        await db.execute(
            select(DiskUsage)
            .where(
                DiskUsage.device_id == device_id,
                DiskUsage.recorded_at >= from_dt,
                DiskUsage.recorded_at <= to_dt,
            )
            .order_by(DiskUsage.recorded_at.desc(), DiskUsage.drive_letter.asc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        DiskUsageHistoryItem(
            recorded_at=r.recorded_at,
            drive_letter=r.drive_letter,
            volume_name=r.volume_name,
            filesystem=r.filesystem,
            total_capacity_gb=float(r.total_capacity_gb),
            free_capacity_gb=float(r.free_capacity_gb),
            used_capacity_gb=float(r.used_capacity_gb),
            used_percent=float(r.used_percent),
        )
        for r in rows
    ]


async def get_history(
    device_id: uuid.UUID,
    metric: str | None,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> HistoryData:
    """
    Recupera el histórico de métricas de un dispositivo.

    Si metric es None se devuelven todas las métricas.
    Si metric es uno de 'battery', 'boot_time', 'software_usage', 'disk_usage'
    se devuelve solo esa.
    """
    battery:  list[BatteryHistoryItem]  = []
    boot:     list[BootHistoryItem]     = []
    software: list[SoftwareHistoryItem] = []
    disk:     list[DiskUsageHistoryItem] = []

    if metric in (None, "battery"):
        battery = await get_battery_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "boot_time"):
        boot = await get_boot_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "software_usage"):
        software = await get_software_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "disk_usage"):
        disk = await get_disk_usage_history(device_id, from_dt, to_dt, limit, db)

    return HistoryData(battery=battery, boot_time=boot, software_usage=software, disk_usage=disk)
