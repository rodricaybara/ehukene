"""
Router — POST /api/devices/register
Registro inicial de un dispositivo nuevo.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device
from app.schemas.device import DeviceRegisterRequest, DeviceRegisterResponse
from app.services.auth import generate_api_key

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.post(
    "/register",
    response_model=DeviceRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un dispositivo nuevo",
    description=(
        "Crea un nuevo dispositivo y devuelve su API Key en claro. "
        "La key solo se expone en esta respuesta; el backend almacena únicamente su hash. "
        "Sin autenticación en POC — proteger con IP whitelist en Fase 2."
    ),
)
async def register_device(
    body: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> DeviceRegisterResponse:
    existing = (
        await db.execute(select(Device).where(Device.hostname == body.hostname))
    ).scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "DUPLICATE_HOSTNAME",
                "detail": f"Ya existe un dispositivo registrado con hostname '{body.hostname}'",
            },
        )

    api_key_plain, api_key_hash = generate_api_key()

    now = datetime.utcnow()
    device = Device(
        hostname=body.hostname,
        api_key_hash=api_key_hash,
        first_seen=now,
        last_seen=now,
        active=True,
    )
    db.add(device)
    await db.flush()

    return DeviceRegisterResponse(
        device_id=device.id,
        hostname=device.hostname,
        api_key=api_key_plain,
        created_at=now,
    )
