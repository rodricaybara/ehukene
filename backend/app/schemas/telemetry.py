"""
Schemas Pydantic — payload del agente (POST /api/telemetry).

Valida el payload completo que envía el agente según el contrato v1.3.
La validación es estricta: tipos, rangos y formatos se verifican aquí
antes de tocar la base de datos.
"""

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Métricas de batería
# ---------------------------------------------------------------------------

_VALID_BATTERY_SOURCES = {"powercfg", "wmi"}


class BatteryMetrics(BaseModel):
    battery_source: str
    battery_name: str | None = None
    battery_manufacturer: str | None = None
    battery_serial: str | None = None
    battery_chemistry: str | None = None
    battery_design_capacity_wh: float
    battery_full_charge_capacity_wh: float
    battery_health_percent: float
    battery_status: int | None = None

    @field_validator("battery_source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if v not in _VALID_BATTERY_SOURCES:
            raise ValueError(f"battery_source debe ser 'powercfg' o 'wmi', recibido: {v!r}")
        return v

    @field_validator("battery_design_capacity_wh")
    @classmethod
    def validate_design(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"battery_design_capacity_wh debe ser > 0, recibido: {v}")
        return v

    @field_validator("battery_full_charge_capacity_wh")
    @classmethod
    def validate_full(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"battery_full_charge_capacity_wh debe ser >= 0, recibido: {v}")
        return v

    @field_validator("battery_health_percent")
    @classmethod
    def validate_health(cls, v: float) -> float:
        if not (0.0 <= v <= 150.0):
            raise ValueError(
                f"battery_health_percent debe estar en [0.0, 150.0], recibido: {v}"
            )
        return v

    @model_validator(mode="after")
    def validate_wmi_null_fields(self) -> "BatteryMetrics":
        """Cuando la fuente es WMI, los campos de identificación deben ser None."""
        if self.battery_source == "wmi":
            for field in ("battery_name", "battery_manufacturer", "battery_serial", "battery_chemistry"):
                if getattr(self, field) is not None:
                    raise ValueError(
                        f"Cuando battery_source='wmi', {field} debe ser null"
                    )
        return self

    @model_validator(mode="after")
    def validate_powercfg_status(self) -> "BatteryMetrics":
        """Cuando la fuente es powercfg, battery_status debe ser None."""
        if self.battery_source == "powercfg" and self.battery_status is not None:
            raise ValueError("Cuando battery_source='powercfg', battery_status debe ser null")
        return self


# ---------------------------------------------------------------------------
# Métricas de uso de software — un dict por target
# ---------------------------------------------------------------------------

_ISO8601_LOCAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class SoftwareUsageItem(BaseModel):
    name: str = Field(..., max_length=100)
    installed: bool
    version: str | None = None
    last_execution: str | None = None  # ISO 8601 hora local "YYYY-MM-DDTHH:MM:SS"
    executions_last_30d: int = Field(..., ge=0)
    executions_last_60d: int = Field(..., ge=0)
    executions_last_90d: int = Field(..., ge=0)

    @field_validator("last_execution")
    @classmethod
    def validate_last_execution(cls, v: str | None) -> str | None:
        if v is not None and not _ISO8601_LOCAL.match(v):
            raise ValueError(
                f"last_execution debe ser ISO 8601 'YYYY-MM-DDTHH:MM:SS', recibido: {v!r}"
            )
        return v

    @model_validator(mode="after")
    def validate_not_installed(self) -> "SoftwareUsageItem":
        if not self.installed:
            if self.version is not None:
                raise ValueError("Si installed=false, version debe ser null")
            if any([self.executions_last_30d, self.executions_last_60d, self.executions_last_90d]):
                raise ValueError("Si installed=false, todos los conteos deben ser 0")
        return self

    @model_validator(mode="after")
    def validate_count_order(self) -> "SoftwareUsageItem":
        if not (self.executions_last_30d <= self.executions_last_60d <= self.executions_last_90d):
            raise ValueError(
                "Invariante de orden: executions_last_30d <= executions_last_60d <= executions_last_90d"
            )
        return self


# ---------------------------------------------------------------------------
# Métricas de arranque
# ---------------------------------------------------------------------------

class BootTimeMetrics(BaseModel):
    last_boot_time: str  # ISO 8601 hora local "YYYY-MM-DDTHH:MM:SS"
    boot_duration_seconds: int | None = None

    @field_validator("last_boot_time")
    @classmethod
    def validate_last_boot(cls, v: str) -> str:
        if not _ISO8601_LOCAL.match(v):
            raise ValueError(
                f"last_boot_time debe ser ISO 8601 'YYYY-MM-DDTHH:MM:SS', recibido: {v!r}"
            )
        return v

    @field_validator("boot_duration_seconds")
    @classmethod
    def validate_duration(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError(f"boot_duration_seconds debe ser > 0, recibido: {v}")
        return v


# ---------------------------------------------------------------------------
# Bloque metrics del payload
# ---------------------------------------------------------------------------

class MetricsBlock(BaseModel):
    """
    Diccionario de métricas del payload.
    Cada plugin presente como clave; los ausentes simplemente no aparecen.
    software_usage es list[dict] (un item por target).
    """
    battery: BatteryMetrics | None = None
    software_usage: list[SoftwareUsageItem] | None = None
    boot_time: BootTimeMetrics | None = None

    @model_validator(mode="after")
    def validate_not_all_none(self) -> "MetricsBlock":
        if all(v is None for v in (self.battery, self.software_usage, self.boot_time)):
            raise ValueError("metrics no puede estar vacío: al menos un plugin debe estar presente")
        # software_usage=[] (lista vacía) no cuenta como dato presente
        if (
            self.battery is None
            and self.boot_time is None
            and (self.software_usage is None or len(self.software_usage) == 0)
        ):
            raise ValueError("metrics no puede estar vacío: al menos un plugin debe aportar datos")
        return self


# ---------------------------------------------------------------------------
# Payload raíz
# ---------------------------------------------------------------------------

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_ISO8601_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_ASCII_ONLY = re.compile(r"^[\x20-\x7E]+$")


class TelemetryPayload(BaseModel):
    device_id: str = Field(..., max_length=255)
    timestamp: str  # ISO 8601 UTC: "YYYY-MM-DDTHH:MM:SSZ"
    agent_version: str
    username: str = Field(..., max_length=255)
    metrics: MetricsBlock

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        if not _ASCII_ONLY.match(v):
            raise ValueError("device_id solo puede contener caracteres ASCII imprimibles")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        if not _ISO8601_UTC.match(v):
            raise ValueError(
                f"timestamp debe ser ISO 8601 UTC 'YYYY-MM-DDTHH:MM:SSZ', recibido: {v!r}"
            )
        return v

    @field_validator("agent_version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if not _SEMVER.match(v):
            raise ValueError(
                f"agent_version debe ser semver 'MAJOR.MINOR.PATCH', recibido: {v!r}"
            )
        return v

    def parsed_timestamp(self) -> datetime:
        """Devuelve el timestamp del agente como objeto datetime (sin zona horaria)."""
        return datetime.strptime(self.timestamp, "%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Response de POST /api/telemetry
# ---------------------------------------------------------------------------

class TelemetryAccepted(BaseModel):
    status: str = "accepted"
    device_id: str
    received_at: datetime
