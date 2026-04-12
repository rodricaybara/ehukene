"""
Modelo ORM — tabla `software_usage`.
Métricas de instalación y uso de software por dispositivo y programa.
Una fila por target por envío del agente.
"""

import uuid
from datetime import datetime

from sqlalchemy import UUID, Boolean, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SoftwareUsage(Base):
    __tablename__ = "software_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(nullable=False)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Identificador del programa (ej. "adobe_acrobat_pro")
    software_name: Mapped[str] = mapped_column(String(100), nullable=False)

    installed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Último uso detectado vía Prefetch (NULL si no hay datos)
    # Tratado como UTC en POC (el agente envía hora local)
    last_execution: Mapped[datetime | None] = mapped_column(nullable=True)

    # Conteos por ventana temporal
    executions_30d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    executions_60d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    executions_90d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    device: Mapped["Device"] = relationship(back_populates="software_usages", lazy="noload")  # noqa: F821
