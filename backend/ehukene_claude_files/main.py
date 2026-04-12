"""
EHUkene Backend — Punto de entrada.

Arranca FastAPI, registra routers, middleware de rate limiting
y manejadores de error globales.

Arranque en desarrollo:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Arranque en producción (detrás de NGINX):
    uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.middleware.rate_limit import limiter, rate_limit_handler
from app.routers import devices, history, register, telemetry


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nada que hacer en POC (las tablas se crean con init.sql)
    yield
    # Shutdown: cerrar el engine async correctamente
    from app.database import engine
    await engine.dispose()


# ---------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------

app = FastAPI(
    title="EHUkene API",
    description=(
        "Backend de telemetría e inventario para equipos Windows. "
        "Complementa Ivanti EPM cubriendo métricas de batería, "
        "uso de software y tiempo de arranque."
    ),
    version="1.0.0",
    lifespan=lifespan,
    # En producción no exponer la documentación interactiva
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


# ---------------------------------------------------------------------------
# Middleware de tamaño de payload
# ---------------------------------------------------------------------------

class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Rechaza peticiones cuyo Content-Length supera MAX_PAYLOAD_BYTES
    antes de leer el cuerpo. Complementa la comprobación del router.
    """
    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and int(cl) > settings.max_payload_bytes:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "error": "PAYLOAD_TOO_LARGE",
                    "detail": f"El payload supera el límite de {settings.max_payload_bytes} bytes",
                },
            )
        return await call_next(request)


app.add_middleware(PayloadSizeLimitMiddleware)


# ---------------------------------------------------------------------------
# Manejadores de error globales
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Transforma los errores de validación de Pydantic (422) al formato
    estándar del contrato: {"error": "VALIDATION_ERROR", "detail": "..."}.
    """
    # Extraer el primer error con su ubicación para un mensaje legible
    errors = exc.errors()
    detail_parts = []
    for err in errors[:5]:  # máximo 5 errores en la respuesta
        loc = " → ".join(str(l) for l in err["loc"] if l != "body")
        detail_parts.append(f"{loc}: {err['msg']}" if loc else err["msg"])

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "VALIDATION_ERROR",
            "detail": "; ".join(detail_parts),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Captura excepciones no manejadas y devuelve 500 sin exponer detalles internos.
    En desarrollo sí se expone el mensaje para facilitar el debug.
    """
    detail = str(exc) if not settings.is_production else "Error interno del servidor"
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "INTERNAL_ERROR", "detail": detail},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(register.router)
app.include_router(telemetry.router)
app.include_router(devices.router)
app.include_router(history.router)


# ---------------------------------------------------------------------------
# Endpoint de salud — sin autenticación, útil para NGINX / monitorización
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"], include_in_schema=False)
async def health_check() -> dict:
    return {"status": "ok", "version": "1.0.0"}
