"""
Modelo ORM — tabla `boot_metrics`.
Métricas del proceso de arranque del sistema operativo por dispositivo.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BootMetric(Base):
    __tablename__ = "boot_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(nullable=False)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Fuente de datos: 'event_log' | 'wmi'
    data_source: Mapped[str] = mapped_column(String(15), nullable=False)

    # Timestamp del último arranque (tratado como UTC en POC)
    last_boot_time: Mapped[datetime] = mapped_column(nullable=False)

    # NULL si la fuente es WMI (Win32_OperatingSystem no expone la duración)
    boot_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    device: Mapped["Device"] = relationship(back_populates="boot_metrics", lazy="noload")  # noqa: F821
