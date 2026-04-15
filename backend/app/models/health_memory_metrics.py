"""
Modelo ORM — tabla `health_memory_metrics`.
Métrica de memoria reportada por el plugin health_monitor.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, ForeignKey, Numeric, String, Text, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HealthMemoryMetric(Base):
    __tablename__ = "health_memory_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(nullable=False)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    total_kb: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    free_kb: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    usage_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped["Device"] = relationship(back_populates="health_memory_metrics", lazy="noload")  # noqa: F821
