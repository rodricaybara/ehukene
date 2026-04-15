"""
Importa todos los modelos para que SQLAlchemy registre su metadata.
Este módulo debe importarse antes de crear tablas o usar el ORM.
"""

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

__all__ = [
    "Device",
    "TelemetryRaw",
    "BatteryMetric",
    "SoftwareUsage",
    "BootMetric",
    "DiskUsage",
    "HealthCpuMetric",
    "HealthMemoryMetric",
    "HealthDiskMetric",
    "HealthEventMetric",
    "HealthDomainMetric",
    "HealthUptimeMetric",
    "HealthBootTimeMetric",
    "HealthServiceMetric",
]
