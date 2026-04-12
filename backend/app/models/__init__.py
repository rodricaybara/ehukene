"""
Importa todos los modelos para que SQLAlchemy registre su metadata.
Este módulo debe importarse antes de crear tablas o usar el ORM.
"""

from app.models.battery_metrics import BatteryMetric
from app.models.boot_metrics import BootMetric
from app.models.device import Device
from app.models.disk_usage import DiskUsage
from app.models.software_usage import SoftwareUsage
from app.models.telemetry_raw import TelemetryRaw

__all__ = [
    "Device",
    "TelemetryRaw",
    "BatteryMetric",
    "SoftwareUsage",
    "BootMetric",
    "DiskUsage",
]
