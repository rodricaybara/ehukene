"""
Modelo ORM — tabla `disk_metrics`.
Métricas de ocupación por unidad lógica local y dispositivo.
Una fila por unidad por envío del agente.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, CheckConstraint, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DiskUsage(Base):
    __tablename__ = "disk_metrics"
    __table_args__ = (
        CheckConstraint("total_capacity_gb > 0", name="disk_metrics_total_positive"),
        CheckConstraint("free_capacity_gb >= 0", name="disk_metrics_free_nonnegative"),
        CheckConstraint("used_capacity_gb >= 0", name="disk_metrics_used_nonnegative"),
        CheckConstraint(
            "used_percent >= 0 AND used_percent <= 100",
            name="disk_metrics_percent_range",
        ),
        Index("idx_disk_device_time", "device_id", "recorded_at"),
        Index("idx_disk_device_drive", "device_id", "drive_letter", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(nullable=False)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    data_source: Mapped[str] = mapped_column(String(10), nullable=False)
    drive_letter: Mapped[str] = mapped_column(String(10), nullable=False)
    volume_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filesystem: Mapped[str | None] = mapped_column(String(20), nullable=True)
    total_capacity_gb: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    free_capacity_gb: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    used_capacity_gb: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    used_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    device: Mapped["Device"] = relationship(back_populates="disk_usages", lazy="noload")  # noqa: F821
