"""
Router — GET /api/devices/{device_id}/history
Histórico de métricas de un dispositivo por rango de fechas.
"""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device
from app.schemas.history import HistoryResponse
from app.services.auth import require_auth
from app.services.history import get_history

router = APIRouter(prefix="/api/devices", tags=["history"])

_VALID_METRICS = {"battery", "software_usage", "boot_time", "disk_usage"}


@router.get(
    "/{device_id}/history",
    response_model=HistoryResponse,
    summary="Histórico de métricas de un dispositivo",
)
async def device_history(
    device_id: uuid.UUID,
    metric: str | None = Query(
        default=None,
        description="Filtrar por tipo: battery, software_usage, boot_time, disk_usage. Sin valor = todas.",
    ),
    from_: datetime | None = Query(
        default=None,
        alias="from",
        description="Fecha inicio (ISO 8601). Por defecto: hace 30 días.",
    ),
    to: datetime | None = Query(
        default=None,
        description="Fecha fin (ISO 8601). Por defecto: ahora.",
    ),
    limit: int = Query(
        default=90,
        ge=1,
        le=365,
        description="Máximo de resultados por métrica.",
    ),
    _auth: Device = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> HistoryResponse:

    # Validar el parámetro metric si se proporciona
    if metric is not None and metric not in _VALID_METRICS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "VALIDATION_ERROR",
                "detail": f"metric debe ser uno de: {', '.join(sorted(_VALID_METRICS))}",
            },
        )

    # Verificar que el dispositivo existe
    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "detail": f"Dispositivo '{device_id}' no encontrado"},
        )

    # Defaults del rango temporal
    now = datetime.utcnow()
    from_dt = from_ if from_ is not None else (now - timedelta(days=30))
    to_dt   = to    if to    is not None else now

    if from_dt >= to_dt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "VALIDATION_ERROR",
                "detail": "'from' debe ser anterior a 'to'",
            },
        )

    history_data = await get_history(device.id, metric, from_dt, to_dt, limit, db)

    return HistoryResponse(
        device_id=device.id,
        from_=from_dt,
        to=to_dt,
        history=history_data,
    )
