"""
Servicio de autenticación — EHUkene Backend.

Gestiona la validación de API Keys de dispositivo.
Las keys se almacenan únicamente como hash SHA-256 en hex (64 chars).

Exports:
    - generate_api_key()   : genera una key segura y su hash
    - hash_api_key()       : hash SHA-256 hex de una key
    - get_device_by_key()  : resuelve una API Key al Device de BD
    - require_auth()       : dependencia FastAPI que autentica y devuelve el Device
"""

import hashlib
import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device

# FastAPI extrae la key de la cabecera X-API-Key
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def generate_api_key() -> tuple[str, str]:
    """
    Genera una API Key segura y su hash SHA-256.

    Returns:
        (api_key_plain, api_key_hash) — la key en claro solo se devuelve
        en el momento del registro; el backend almacena únicamente el hash.
    """
    key = secrets.token_hex(32)  # 64 chars hex → 256 bits de entropía
    return key, hash_api_key(key)


def hash_api_key(key: str) -> str:
    """Devuelve el hash SHA-256 en hex de una API Key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


async def get_device_by_key(
    key: str,
    db: AsyncSession,
) -> Device | None:
    """
    Busca el Device cuyo api_key_hash coincide con el hash de la key dada.
    Devuelve None si no existe o si el dispositivo está inactivo.
    """
    key_hash = hash_api_key(key)
    result = await db.execute(
        select(Device).where(
            Device.api_key_hash == key_hash,
            Device.active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def require_auth(
    raw_key: str | None = Depends(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """
    Dependencia FastAPI.
    Valida la API Key y devuelve el Device autenticado.
    Lanza 401 si la key falta o es inválida.
    """
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "detail": "Cabecera X-API-Key ausente"},
        )

    device = await get_device_by_key(raw_key, db)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "detail": "API Key inválida o revocada"},
        )

    return device
