"""
Modelo ORM — tabla `battery_metrics`.
Métricas de salud y estado de la batería por dispositivo.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, ForeignKey, Numeric, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BatteryMetric(Base):
    __tablename__ = "battery_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    # recorded_at: timestamp del agente (tratado como UTC en POC)
    recorded_at: Mapped[datetime] = mapped_column(nullable=False)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Fuente de datos: 'powercfg' | 'wmi'
    data_source: Mapped[str] = mapped_column(String(10), nullable=False)

    # Campos solo disponibles vía powercfg (NULL cuando fuente es wmi)
    battery_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    battery_manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    battery_serial: Mapped[str | None] = mapped_column(String(50), nullable=True)
    battery_chemistry: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Capacidades en Wh con 3 decimales (contrato v1.1+)
    design_capacity_wh: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    full_charge_capacity_wh: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    health_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    # NULL cuando la fuente es powercfg
    battery_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    device: Mapped["Device"] = relationship(back_populates="battery_metrics", lazy="noload")  # noqa: F821
