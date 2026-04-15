"""
Modelo ORM — tabla `health_boot_time_metrics`.
Métrica de tiempo de arranque reportada por health_monitor.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HealthBootTimeMetric(Base):
    __tablename__ = "health_boot_time_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(nullable=False)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    last_boot_time: Mapped[datetime | None] = mapped_column(nullable=True)
    boot_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped["Device"] = relationship(back_populates="health_boot_time_metrics", lazy="noload")  # noqa: F821
