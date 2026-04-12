"""
Rate limiting — EHUkene Backend.

Usa slowapi (wrapper de limits sobre Starlette/FastAPI).
El límite se configura en RATE_LIMIT_PER_MINUTE (.env).

Exports:
    - limiter       : instancia Limiter para decorar routers
    - rate_limit_handler : manejador de excepciones 429
    - RATE_LIMIT    : string de límite listo para usar en decoradores
"""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

# Identifica al cliente por IP remota.
# Si el backend está detrás de NGINX, get_remote_address leerá X-Forwarded-For
# automáticamente cuando slowapi esté configurado con forwarded=True.
limiter = Limiter(key_func=get_remote_address, default_limits=[])

# String de límite listo para decoradores: "60/minute"
RATE_LIMIT = f"{settings.rate_limit_per_minute}/minute"


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Manejador de 429 con el formato de error estándar del contrato."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "RATE_LIMIT_EXCEEDED",
            "detail": f"Demasiadas peticiones. Límite: {settings.rate_limit_per_minute} por minuto.",
        },
    )
