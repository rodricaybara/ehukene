"""
Configuración de SQLAlchemy async para EHUkene.

Exporta:
    - engine          : AsyncEngine conectado a PostgreSQL via asyncpg
    - AsyncSessionLocal : fábrica de sesiones async
    - Base            : clase base declarativa para los modelos ORM
    - get_db          : dependencia FastAPI que gestiona el ciclo de vida de la sesión
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# pool_pre_ping verifica la conexión antes de usarla; evita errores tras
# períodos de inactividad en los que el servidor cierra la conexión.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=(settings.environment == "development"),  # SQL en log solo en dev
)

# ---------------------------------------------------------------------------
# Fábrica de sesiones
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # evita lazy loads tras commit en contexto async
    autoflush=False,
    autocommit=False,
)

# ---------------------------------------------------------------------------
# Base declarativa
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Dependencia FastAPI
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependencia inyectable en los routers.
    Gestiona apertura, commit/rollback y cierre de la sesión.

    Uso:
        @router.post("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
