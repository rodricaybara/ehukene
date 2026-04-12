"""
Router — POST /api/telemetry
Recepción de métricas del agente.

Flujo de validaciones (en el orden del contrato §4.3):
    1. API Key válida y activa                          → 401
    2. device_id del payload coincide con la key        → 403
    3. JSON válido con campos requeridos                → 400 / 422 (Pydantic)
    4. Tamaño del payload ≤ MAX_PAYLOAD_BYTES           → 413
    5. No existe registro duplicado en la ventana diaria → 409
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.device import Device
from app.schemas.telemetry import TelemetryAccepted, TelemetryPayload
from app.services.auth import require_auth
from app.services.ingest import ingest_telemetry, is_duplicate

router = APIRouter(prefix="/api", tags=["telemetry"])


@router.post(
    "/telemetry",
    response_model=TelemetryAccepted,
    status_code=status.HTTP_200_OK,
    summary="Recibir métricas del agente",
)
async def receive_telemetry(
    request: Request,
    payload: TelemetryPayload,
    device: Device = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> TelemetryAccepted:

    # 2. El device_id del payload debe coincidir con el hostname del dispositivo
    #    autenticado. El agente envía su hostname como device_id.
    if payload.device_id.lower() != device.hostname.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "FORBIDDEN",
                "detail": "El device_id del payload no corresponde a la API Key presentada",
            },
        )

    # 4. Verificar tamaño del payload (el body ya fue parseado por Pydantic,
    #    pero comprobamos el Content-Length si está disponible para el 413).
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_payload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "PAYLOAD_TOO_LARGE",
                "detail": f"El payload supera el límite de {settings.max_payload_bytes} bytes",
            },
        )

    # 5. Deduplicación diaria
    agent_ts = payload.parsed_timestamp()
    if await is_duplicate(device.id, agent_ts, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "DUPLICATE_SUBMISSION",
                "detail": "Ya existe un registro para este dispositivo en el período actual",
            },
        )

    # Ingesta: actualizar device, insertar raw y tablas tipadas
    raw_dict = payload.model_dump(mode="json")
    received_at = datetime.utcnow()

    await ingest_telemetry(device, payload, raw_dict, db)

    return TelemetryAccepted(
        status="accepted",
        device_id=payload.device_id,
        received_at=received_at,
    )
