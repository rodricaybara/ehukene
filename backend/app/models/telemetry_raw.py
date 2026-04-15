"""
Modelo ORM — tabla `telemetry_raw`.
Almacén de auditoría: guarda el payload completo de cada envío del agente.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TelemetryRaw(Base):
    __tablename__ = "telemetry_raw"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False, index=True
    )
    # Timestamp declarado por el agente en el payload; base de la deduplicación diaria
    agent_timestamp: Mapped[datetime] = mapped_column(nullable=False, index=True)
    # Timestamp de recepción en el backend (no el timestamp del agente)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    device: Mapped["Device"] = relationship(back_populates="telemetry_raw", lazy="noload")  # noqa: F821
