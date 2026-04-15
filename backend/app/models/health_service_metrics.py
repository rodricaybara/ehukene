"""
Modelo ORM — tabla `health_service_metrics`.
Una fila por servicio monitorizado en cada ejecución de health_monitor.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, ForeignKey, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HealthServiceMetric(Base):
    __tablename__ = "health_service_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(nullable=False)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    startup_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    device: Mapped["Device"] = relationship(back_populates="health_service_metrics", lazy="noload")  # noqa: F821
