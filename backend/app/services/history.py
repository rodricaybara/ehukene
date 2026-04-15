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
from app.models.health_boot_time_metrics import HealthBootTimeMetric
from app.models.health_cpu_metrics import HealthCpuMetric
from app.models.health_disk_metrics import HealthDiskMetric
from app.models.health_domain_metrics import HealthDomainMetric
from app.models.health_event_metrics import HealthEventMetric
from app.models.health_memory_metrics import HealthMemoryMetric
from app.models.health_service_metrics import HealthServiceMetric
from app.models.health_uptime_metrics import HealthUptimeMetric
from app.models.software_usage import SoftwareUsage
from app.schemas.device import (
    LastHealthBootTimeMetrics,
    LastHealthCpuMetrics,
    LastHealthDiskMetrics,
    LastHealthDomainMetrics,
    LastHealthEventSourceItem,
    LastHealthEventsMetrics,
    LastHealthMemoryMetrics,
    LastHealthMonitorMetrics,
    LastHealthSampleEventItem,
    LastHealthServiceItem,
    LastHealthUptimeMetrics,
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
    HealthBootTimeHistoryItem,
    HealthCpuHistoryItem,
    HealthDiskHistoryItem,
    HealthDomainHistoryItem,
    HealthEventsHistoryItem,
    HealthEventSourceHistoryItem,
    HealthMemoryHistoryItem,
    HealthSampleEventHistoryItem,
    HealthServiceHistoryItem,
    HealthUptimeHistoryItem,
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

    health_cpu_row = (
        await db.execute(
            select(HealthCpuMetric)
            .where(HealthCpuMetric.device_id == device_id)
            .order_by(HealthCpuMetric.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    health_memory_row = (
        await db.execute(
            select(HealthMemoryMetric)
            .where(HealthMemoryMetric.device_id == device_id)
            .order_by(HealthMemoryMetric.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    health_disk_row = (
        await db.execute(
            select(HealthDiskMetric)
            .where(HealthDiskMetric.device_id == device_id)
            .order_by(HealthDiskMetric.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    health_events_row = (
        await db.execute(
            select(HealthEventMetric)
            .where(HealthEventMetric.device_id == device_id)
            .order_by(HealthEventMetric.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    health_domain_row = (
        await db.execute(
            select(HealthDomainMetric)
            .where(HealthDomainMetric.device_id == device_id)
            .order_by(HealthDomainMetric.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    health_uptime_row = (
        await db.execute(
            select(HealthUptimeMetric)
            .where(HealthUptimeMetric.device_id == device_id)
            .order_by(HealthUptimeMetric.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    health_boot_row = (
        await db.execute(
            select(HealthBootTimeMetric)
            .where(HealthBootTimeMetric.device_id == device_id)
            .order_by(HealthBootTimeMetric.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    health_services_ts = (
        await db.execute(
            select(HealthServiceMetric.recorded_at)
            .where(HealthServiceMetric.device_id == device_id)
            .order_by(HealthServiceMetric.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    health_services: list[LastHealthServiceItem] = []
    if health_services_ts:
        service_rows = (
            await db.execute(
                select(HealthServiceMetric).where(
                    HealthServiceMetric.device_id == device_id,
                    HealthServiceMetric.recorded_at == health_services_ts,
                )
            )
        ).scalars().all()
        health_services = [
            LastHealthServiceItem(
                service_name=r.service_name,
                display_name=r.display_name,
                state=r.state,
                startup_type=r.startup_type,
                tier=r.tier,
                status=r.status,
                recorded_at=r.recorded_at,
            )
            for r in service_rows
        ]

    health_monitor = None
    if any(
        row is not None
        for row in (
            health_cpu_row,
            health_memory_row,
            health_disk_row,
            health_events_row,
            health_domain_row,
            health_uptime_row,
            health_boot_row,
        )
    ) or health_services:
        health_monitor = LastHealthMonitorMetrics(
            cpu=(
                LastHealthCpuMetrics(
                    load_percentage=float(health_cpu_row.load_percentage)
                    if health_cpu_row and health_cpu_row.load_percentage is not None
                    else None,
                    status=health_cpu_row.status,
                    error_msg=health_cpu_row.error_msg,
                    recorded_at=health_cpu_row.recorded_at,
                )
                if health_cpu_row
                else None
            ),
            memory=(
                LastHealthMemoryMetrics(
                    total_kb=health_memory_row.total_kb,
                    free_kb=health_memory_row.free_kb,
                    usage_pct=float(health_memory_row.usage_pct)
                    if health_memory_row.usage_pct is not None
                    else None,
                    status=health_memory_row.status,
                    error_msg=health_memory_row.error_msg,
                    recorded_at=health_memory_row.recorded_at,
                )
                if health_memory_row
                else None
            ),
            disk=(
                LastHealthDiskMetrics(
                    drive=health_disk_row.drive,
                    total_gb=float(health_disk_row.total_gb)
                    if health_disk_row and health_disk_row.total_gb is not None
                    else None,
                    free_gb=float(health_disk_row.free_gb)
                    if health_disk_row and health_disk_row.free_gb is not None
                    else None,
                    free_pct=float(health_disk_row.free_pct)
                    if health_disk_row and health_disk_row.free_pct is not None
                    else None,
                    status=health_disk_row.status,
                    error_msg=health_disk_row.error_msg,
                    recorded_at=health_disk_row.recorded_at,
                )
                if health_disk_row
                else None
            ),
            events=(
                LastHealthEventsMetrics(
                    critical_count=health_events_row.critical_count,
                    error_count=health_events_row.error_count,
                    filtered_count=health_events_row.filtered_count,
                    top_sources=[
                        LastHealthEventSourceItem(**item) for item in health_events_row.top_sources
                    ],
                    sample_events=[
                        LastHealthSampleEventItem(
                            event_id=item["event_id"],
                            provider=item["provider"],
                            level=item["level"],
                            time_created=datetime.strptime(
                                item["time_created"], "%Y-%m-%dT%H:%M:%SZ"
                            ),
                        )
                        for item in health_events_row.sample_events
                    ],
                    status=health_events_row.status,
                    error_msg=health_events_row.error_msg,
                    recorded_at=health_events_row.recorded_at,
                )
                if health_events_row
                else None
            ),
            domain=(
                LastHealthDomainMetrics(
                    secure_channel=health_domain_row.secure_channel,
                    status=health_domain_row.status,
                    error_msg=health_domain_row.error_msg,
                    recorded_at=health_domain_row.recorded_at,
                )
                if health_domain_row
                else None
            ),
            uptime=(
                LastHealthUptimeMetrics(
                    last_boot=health_uptime_row.last_boot,
                    days=float(health_uptime_row.days)
                    if health_uptime_row.days is not None
                    else None,
                    status=health_uptime_row.status,
                    error_msg=health_uptime_row.error_msg,
                    recorded_at=health_uptime_row.recorded_at,
                )
                if health_uptime_row
                else None
            ),
            boot_time=(
                LastHealthBootTimeMetrics(
                    last_boot_time=health_boot_row.last_boot_time,
                    boot_duration_seconds=health_boot_row.boot_duration_seconds,
                    source=health_boot_row.source,
                    status=health_boot_row.status,
                    error_msg=health_boot_row.error_msg,
                    recorded_at=health_boot_row.recorded_at,
                )
                if health_boot_row
                else None
            ),
            services=health_services,
        )

    return LastMetrics(
        battery=last_battery,
        software_usage=last_software,
        boot_time=last_boot,
        disk_usage=last_disk_usage,
        health_monitor=health_monitor,
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


async def get_health_cpu_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[HealthCpuHistoryItem]:
    rows = (
        await db.execute(
            select(HealthCpuMetric)
            .where(
                HealthCpuMetric.device_id == device_id,
                HealthCpuMetric.recorded_at >= from_dt,
                HealthCpuMetric.recorded_at <= to_dt,
            )
            .order_by(HealthCpuMetric.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        HealthCpuHistoryItem(
            recorded_at=r.recorded_at,
            load_percentage=float(r.load_percentage) if r.load_percentage is not None else None,
            status=r.status,
            error_msg=r.error_msg,
        )
        for r in rows
    ]


async def get_health_memory_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[HealthMemoryHistoryItem]:
    rows = (
        await db.execute(
            select(HealthMemoryMetric)
            .where(
                HealthMemoryMetric.device_id == device_id,
                HealthMemoryMetric.recorded_at >= from_dt,
                HealthMemoryMetric.recorded_at <= to_dt,
            )
            .order_by(HealthMemoryMetric.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        HealthMemoryHistoryItem(
            recorded_at=r.recorded_at,
            total_kb=r.total_kb,
            free_kb=r.free_kb,
            usage_pct=float(r.usage_pct) if r.usage_pct is not None else None,
            status=r.status,
            error_msg=r.error_msg,
        )
        for r in rows
    ]


async def get_health_disk_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[HealthDiskHistoryItem]:
    rows = (
        await db.execute(
            select(HealthDiskMetric)
            .where(
                HealthDiskMetric.device_id == device_id,
                HealthDiskMetric.recorded_at >= from_dt,
                HealthDiskMetric.recorded_at <= to_dt,
            )
            .order_by(HealthDiskMetric.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        HealthDiskHistoryItem(
            recorded_at=r.recorded_at,
            drive=r.drive,
            total_gb=float(r.total_gb) if r.total_gb is not None else None,
            free_gb=float(r.free_gb) if r.free_gb is not None else None,
            free_pct=float(r.free_pct) if r.free_pct is not None else None,
            status=r.status,
            error_msg=r.error_msg,
        )
        for r in rows
    ]


async def get_health_events_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[HealthEventsHistoryItem]:
    rows = (
        await db.execute(
            select(HealthEventMetric)
            .where(
                HealthEventMetric.device_id == device_id,
                HealthEventMetric.recorded_at >= from_dt,
                HealthEventMetric.recorded_at <= to_dt,
            )
            .order_by(HealthEventMetric.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        HealthEventsHistoryItem(
            recorded_at=r.recorded_at,
            critical_count=r.critical_count,
            error_count=r.error_count,
            filtered_count=r.filtered_count,
            top_sources=[HealthEventSourceHistoryItem(**item) for item in r.top_sources],
            sample_events=[
                HealthSampleEventHistoryItem(
                    event_id=item["event_id"],
                    provider=item["provider"],
                    level=item["level"],
                    time_created=datetime.strptime(item["time_created"], "%Y-%m-%dT%H:%M:%SZ"),
                )
                for item in r.sample_events
            ],
            status=r.status,
            error_msg=r.error_msg,
        )
        for r in rows
    ]


async def get_health_domain_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[HealthDomainHistoryItem]:
    rows = (
        await db.execute(
            select(HealthDomainMetric)
            .where(
                HealthDomainMetric.device_id == device_id,
                HealthDomainMetric.recorded_at >= from_dt,
                HealthDomainMetric.recorded_at <= to_dt,
            )
            .order_by(HealthDomainMetric.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        HealthDomainHistoryItem(
            recorded_at=r.recorded_at,
            secure_channel=r.secure_channel,
            status=r.status,
            error_msg=r.error_msg,
        )
        for r in rows
    ]


async def get_health_uptime_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[HealthUptimeHistoryItem]:
    rows = (
        await db.execute(
            select(HealthUptimeMetric)
            .where(
                HealthUptimeMetric.device_id == device_id,
                HealthUptimeMetric.recorded_at >= from_dt,
                HealthUptimeMetric.recorded_at <= to_dt,
            )
            .order_by(HealthUptimeMetric.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        HealthUptimeHistoryItem(
            recorded_at=r.recorded_at,
            last_boot=r.last_boot,
            days=float(r.days) if r.days is not None else None,
            status=r.status,
            error_msg=r.error_msg,
        )
        for r in rows
    ]


async def get_health_boot_time_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[HealthBootTimeHistoryItem]:
    rows = (
        await db.execute(
            select(HealthBootTimeMetric)
            .where(
                HealthBootTimeMetric.device_id == device_id,
                HealthBootTimeMetric.recorded_at >= from_dt,
                HealthBootTimeMetric.recorded_at <= to_dt,
            )
            .order_by(HealthBootTimeMetric.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        HealthBootTimeHistoryItem(
            recorded_at=r.recorded_at,
            last_boot_time=r.last_boot_time,
            boot_duration_seconds=r.boot_duration_seconds,
            source=r.source,
            status=r.status,
            error_msg=r.error_msg,
        )
        for r in rows
    ]


async def get_health_services_history(
    device_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
    limit: int,
    db: AsyncSession,
) -> list[HealthServiceHistoryItem]:
    rows = (
        await db.execute(
            select(HealthServiceMetric)
            .where(
                HealthServiceMetric.device_id == device_id,
                HealthServiceMetric.recorded_at >= from_dt,
                HealthServiceMetric.recorded_at <= to_dt,
            )
            .order_by(HealthServiceMetric.recorded_at.desc(), HealthServiceMetric.service_name.asc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        HealthServiceHistoryItem(
            recorded_at=r.recorded_at,
            service_name=r.service_name,
            display_name=r.display_name,
            state=r.state,
            startup_type=r.startup_type,
            tier=r.tier,
            status=r.status,
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
    o una de las métricas health_*
    se devuelve solo esa.
    """
    battery:  list[BatteryHistoryItem]  = []
    boot:     list[BootHistoryItem]     = []
    software: list[SoftwareHistoryItem] = []
    disk:     list[DiskUsageHistoryItem] = []
    health_cpu: list[HealthCpuHistoryItem] = []
    health_memory: list[HealthMemoryHistoryItem] = []
    health_disk: list[HealthDiskHistoryItem] = []
    health_events: list[HealthEventsHistoryItem] = []
    health_domain: list[HealthDomainHistoryItem] = []
    health_uptime: list[HealthUptimeHistoryItem] = []
    health_boot_time: list[HealthBootTimeHistoryItem] = []
    health_services: list[HealthServiceHistoryItem] = []

    if metric in (None, "battery"):
        battery = await get_battery_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "boot_time"):
        boot = await get_boot_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "software_usage"):
        software = await get_software_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "disk_usage"):
        disk = await get_disk_usage_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "health_cpu"):
        health_cpu = await get_health_cpu_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "health_memory"):
        health_memory = await get_health_memory_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "health_disk"):
        health_disk = await get_health_disk_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "health_events"):
        health_events = await get_health_events_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "health_domain"):
        health_domain = await get_health_domain_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "health_uptime"):
        health_uptime = await get_health_uptime_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "health_boot_time"):
        health_boot_time = await get_health_boot_time_history(device_id, from_dt, to_dt, limit, db)
    if metric in (None, "health_services"):
        health_services = await get_health_services_history(device_id, from_dt, to_dt, limit, db)

    return HistoryData(
        battery=battery,
        boot_time=boot,
        software_usage=software,
        disk_usage=disk,
        health_cpu=health_cpu,
        health_memory=health_memory,
        health_disk=health_disk,
        health_events=health_events,
        health_domain=health_domain,
        health_uptime=health_uptime,
        health_boot_time=health_boot_time,
        health_services=health_services,
    )
