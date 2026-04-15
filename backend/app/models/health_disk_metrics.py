"""
Modelo ORM — tabla `health_disk_metrics`.
Métrica del disco del sistema reportada por health_monitor.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HealthDiskMetric(Base):
    __tablename__ = "health_disk_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(nullable=False)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    drive: Mapped[str | None] = mapped_column(String(10), nullable=True)
    total_gb: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    free_gb: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    free_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped["Device"] = relationship(back_populates="health_disk_metrics", lazy="noload")  # noqa: F821
