"""
Modelo ORM — tabla `devices`.
Registro de cada dispositivo conocido por el sistema.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, Boolean, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Última versión del agente reportada en el payload
    agent_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Relaciones (usadas para eager load en consultas de detalle)
    telemetry_raw: Mapped[list["TelemetryRaw"]] = relationship(  # noqa: F821
        back_populates="device", lazy="noload"
    )
    battery_metrics: Mapped[list["BatteryMetric"]] = relationship(  # noqa: F821
        back_populates="device", lazy="noload"
    )
    software_usages: Mapped[list["SoftwareUsage"]] = relationship(  # noqa: F821
        back_populates="device", lazy="noload"
    )
    boot_metrics: Mapped[list["BootMetric"]] = relationship(  # noqa: F821
        back_populates="device", lazy="noload"
    )
    disk_usages: Mapped[list["DiskUsage"]] = relationship(  # noqa: F821
        back_populates="device", lazy="noload"
    )
