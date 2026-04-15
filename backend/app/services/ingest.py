"""
Servicio de ingesta — EHUkene Backend.

Contiene toda la lógica de negocio que se ejecuta al recibir un payload
de telemetría válido y autenticado:
    1. Verificar deduplicación diaria
    2. Actualizar devices.last_seen y devices.agent_version
    3. Insertar en telemetry_raw
    4. Insertar en las tablas tipadas (battery_metrics, software_usage, boot_metrics)

Las funciones de este módulo reciben una sesión ya abierta y no hacen
commit — la transacción la gestiona el caller (habitualmente el router
a través de get_db).
"""

from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.battery_metrics import BatteryMetric
from app.models.boot_metrics import BootMetric
from app.models.device import Device
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
from app.models.telemetry_raw import TelemetryRaw
from app.schemas.telemetry import TelemetryPayload


# ---------------------------------------------------------------------------
# Deduplicación
# ---------------------------------------------------------------------------

async def is_duplicate(
    device_id,
    agent_timestamp: datetime,
    db: AsyncSession,
) -> bool:
    """
    Comprueba si ya existe un registro de telemetry_raw para este dispositivo
    dentro de la ventana de deduplicación configurada en torno al timestamp
    del agente.

    La ventana es ±DEDUP_WINDOW_HOURS/2 centrada en el timestamp del agente,
    lo que en la práctica cubre "el mismo día" con margen ante medianoche.
    """
    half = timedelta(hours=settings.dedup_window_hours / 2)
    window_start = agent_timestamp - half
    window_end   = agent_timestamp + half

    result = await db.execute(
        select(
            exists().where(
                TelemetryRaw.device_id == device_id,
                TelemetryRaw.received_at >= window_start,
                TelemetryRaw.received_at <= window_end,
            )
        )
    )
    return result.scalar()


# ---------------------------------------------------------------------------
# Actualización del dispositivo
# ---------------------------------------------------------------------------

async def update_device_seen(
    device: Device,
    agent_version: str,
    db: AsyncSession,
) -> None:
    """Actualiza last_seen y agent_version del dispositivo."""
    device.last_seen = datetime.utcnow()
    device.agent_version = agent_version
    db.add(device)


# ---------------------------------------------------------------------------
# Inserción en telemetry_raw
# ---------------------------------------------------------------------------

async def insert_raw(
    device: Device,
    payload: TelemetryPayload,
    raw_dict: dict,
    db: AsyncSession,
) -> None:
    """Inserta el payload completo en telemetry_raw como JSONB de auditoría."""
    raw = TelemetryRaw(
        device_id=device.id,
        payload=raw_dict,
    )
    db.add(raw)


# ---------------------------------------------------------------------------
# Inserción en tablas tipadas
# ---------------------------------------------------------------------------

async def insert_battery(
    device: Device,
    payload: TelemetryPayload,
    db: AsyncSession,
) -> None:
    """Inserta métricas de batería si el plugin está presente en el payload."""
    b = payload.metrics.battery
    if b is None:
        return

    record = BatteryMetric(
        device_id=device.id,
        recorded_at=payload.parsed_timestamp(),
        data_source=b.battery_source,
        battery_name=b.battery_name,
        battery_manufacturer=b.battery_manufacturer,
        battery_serial=b.battery_serial,
        battery_chemistry=b.battery_chemistry,
        design_capacity_wh=b.battery_design_capacity_wh,
        full_charge_capacity_wh=b.battery_full_charge_capacity_wh,
        health_percent=b.battery_health_percent,
        battery_status=b.battery_status,
    )
    db.add(record)


async def insert_software_usage(
    device: Device,
    payload: TelemetryPayload,
    db: AsyncSession,
) -> None:
    """
    Inserta una fila por cada target en software_usage.
    Si el plugin devolvió lista vacía no se inserta nada
    (situación válida según el contrato: sin targets configurados).
    """
    items = payload.metrics.software_usage
    if not items:
        return

    agent_ts = payload.parsed_timestamp()

    for item in items:
        # Convertir last_execution (str ISO local) a datetime si está presente
        last_exec: datetime | None = None
        if item.last_execution:
            last_exec = datetime.strptime(item.last_execution, "%Y-%m-%dT%H:%M:%S")

        record = SoftwareUsage(
            device_id=device.id,
            recorded_at=agent_ts,
            software_name=item.name,
            installed=item.installed,
            version=item.version,
            last_execution=last_exec,
            executions_30d=item.executions_last_30d,
            executions_60d=item.executions_last_60d,
            executions_90d=item.executions_last_90d,
        )
        db.add(record)


async def insert_boot_metrics(
    device: Device,
    payload: TelemetryPayload,
    db: AsyncSession,
) -> None:
    """Inserta métricas de arranque si el plugin está presente en el payload."""
    bt = payload.metrics.boot_time
    if bt is None:
        return

    last_boot = datetime.strptime(bt.last_boot_time, "%Y-%m-%dT%H:%M:%S")

    record = BootMetric(
        device_id=device.id,
        recorded_at=payload.parsed_timestamp(),
        # Inferimos la fuente: si boot_duration_seconds es None, vino de WMI
        data_source="wmi" if bt.boot_duration_seconds is None else "event_log",
        last_boot_time=last_boot,
        boot_duration_seconds=bt.boot_duration_seconds,
    )
    db.add(record)


async def insert_disk_usage(
    device: Device,
    payload: TelemetryPayload,
    db: AsyncSession,
) -> None:
    """
    Inserta una fila por cada unidad lógica en disk_usage.
    Si el plugin devolvió lista vacía no se inserta nada.
    """
    items = payload.metrics.disk_usage
    if not items:
        return

    agent_ts = payload.parsed_timestamp()

    for item in items:
        record = DiskUsage(
            device_id=device.id,
            recorded_at=agent_ts,
            data_source=item.disk_source,
            drive_letter=item.drive_letter,
            volume_name=item.volume_name,
            filesystem=item.filesystem,
            total_capacity_gb=item.total_capacity_gb,
            free_capacity_gb=item.free_capacity_gb,
            used_capacity_gb=item.used_capacity_gb,
            used_percent=item.used_percent,
        )
        db.add(record)


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def _parse_local_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")


async def insert_health_monitor(
    device: Device,
    payload: TelemetryPayload,
    db: AsyncSession,
) -> None:
    """Inserta las métricas tipadas del plugin health_monitor."""
    hm = payload.metrics.health_monitor
    if hm is None:
        return

    agent_ts = payload.parsed_timestamp()
    metrics = hm.metrics

    cpu = metrics["cpu"]
    db.add(
        HealthCpuMetric(
            device_id=device.id,
            recorded_at=agent_ts,
            load_percentage=cpu.load_percentage,
            status=cpu.status,
            error_msg=cpu.error_msg,
        )
    )

    memory = metrics["memory"]
    db.add(
        HealthMemoryMetric(
            device_id=device.id,
            recorded_at=agent_ts,
            total_kb=memory.total_kb,
            free_kb=memory.free_kb,
            usage_pct=memory.usage_pct,
            status=memory.status,
            error_msg=memory.error_msg,
        )
    )

    disk = metrics["disk"]
    db.add(
        HealthDiskMetric(
            device_id=device.id,
            recorded_at=agent_ts,
            drive=disk.drive,
            total_gb=disk.total_gb,
            free_gb=disk.free_gb,
            free_pct=disk.free_pct,
            status=disk.status,
            error_msg=disk.error_msg,
        )
    )

    events = metrics["events"]
    db.add(
        HealthEventMetric(
            device_id=device.id,
            recorded_at=agent_ts,
            critical_count=events.critical_count,
            error_count=events.error_count,
            filtered_count=events.filtered_count,
            top_sources=[item.model_dump(mode="json") for item in events.top_sources],
            sample_events=[item.model_dump(mode="json") for item in events.sample_events],
            status=events.status,
            error_msg=events.error_msg,
        )
    )

    domain = metrics["domain"]
    db.add(
        HealthDomainMetric(
            device_id=device.id,
            recorded_at=agent_ts,
            secure_channel=domain.secure_channel,
            status=domain.status,
            error_msg=domain.error_msg,
        )
    )

    uptime = metrics["uptime"]
    db.add(
        HealthUptimeMetric(
            device_id=device.id,
            recorded_at=agent_ts,
            last_boot=_parse_utc_timestamp(uptime.last_boot),
            days=uptime.days,
            status=uptime.status,
            error_msg=uptime.error_msg,
        )
    )

    boot = metrics["boot_time"]
    db.add(
        HealthBootTimeMetric(
            device_id=device.id,
            recorded_at=agent_ts,
            last_boot_time=_parse_local_timestamp(boot.last_boot_time),
            boot_duration_seconds=boot.boot_duration_seconds,
            source=boot.source,
            status=boot.status,
            error_msg=boot.error_msg,
        )
    )

    services = metrics["services"]
    for item in services:
        db.add(
            HealthServiceMetric(
                device_id=device.id,
                recorded_at=agent_ts,
                service_name=item.name,
                display_name=item.display_name,
                state=item.state,
                startup_type=item.startup_type,
                tier=item.tier,
                status=item.status,
            )
        )


# ---------------------------------------------------------------------------
# Función principal de ingesta
# ---------------------------------------------------------------------------

async def ingest_telemetry(
    device: Device,
    payload: TelemetryPayload,
    raw_dict: dict,
    db: AsyncSession,
) -> None:
    """
    Orquesta la ingesta completa de un payload de telemetría.
    Debe llamarse dentro de una transacción activa (get_db se encarga del commit).
    """
    await update_device_seen(device, payload.agent_version, db)
    await insert_raw(device, payload, raw_dict, db)
    await insert_battery(device, payload, db)
    await insert_software_usage(device, payload, db)
    await insert_boot_metrics(device, payload, db)
    await insert_disk_usage(device, payload, db)
    await insert_health_monitor(device, payload, db)
