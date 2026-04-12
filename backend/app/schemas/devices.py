"""
Router — Consulta de dispositivos.
    GET /api/devices                    — listado paginado
    GET /api/devices/{device_id}        — detalle con last_metrics
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device
from app.schemas.device import (
    DeviceDetailResponse,
    DeviceListItem,
    DeviceListResponse,
    LastMetrics,
)
from app.services.auth import require_auth
from app.services.history import get_last_metrics

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get(
    "",
    response_model=DeviceListResponse,
    summary="Listar dispositivos registrados",
)
async def list_devices(
    active: bool = Query(default=True, description="Filtrar por estado activo"),
    limit: int = Query(default=100, ge=1, le=1000, description="Máximo de resultados"),
    offset: int = Query(default=0, ge=0, description="Desplazamiento para paginación"),
    _device: Device = Depends(require_auth),  # cualquier key válida en POC
    db: AsyncSession = Depends(get_db),
) -> DeviceListResponse:

    base_filter = Device.active.is_(active)

    # Total sin paginación
    total = (
        await db.execute(select(func.count(Device.id)).where(base_filter))
    ).scalar_one()

    # Página solicitada
    rows = (
        await db.execute(
            select(Device)
            .where(base_filter)
            .order_by(Device.hostname)
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return DeviceListResponse(
        total=total,
        limit=limit,
        offset=offset,
        devices=[
            DeviceListItem(
                device_id=d.id,
                hostname=d.hostname,
                first_seen=d.first_seen,
                last_seen=d.last_seen,
                active=d.active,
                agent_version=d.agent_version,
            )
            for d in rows
        ],
    )


@router.get(
    "/{device_id}",
    response_model=DeviceDetailResponse,
    summary="Detalle de un dispositivo con sus últimas métricas",
)
async def get_device(
    device_id: uuid.UUID,
    _auth: Device = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> DeviceDetailResponse:

    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "detail": f"Dispositivo '{device_id}' no encontrado"},
        )

    last_metrics: LastMetrics = await get_last_metrics(device.id, db)

    return DeviceDetailResponse(
        device_id=device.id,
        hostname=device.hostname,
        first_seen=device.first_seen,
        last_seen=device.last_seen,
        active=device.active,
        agent_version=device.agent_version,
        last_metrics=last_metrics,
    )
