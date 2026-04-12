# EHUkene Backend API — Documentación de implementación

**Versión:** 1.0
**Fecha:** 2026-03-31
**Contratos de referencia:** `ehukene_contratos__v1_4.md`
**Estado:** POC — listo para despliegue

---

## Índice

1. [Contexto](#1-contexto)
2. [Stack tecnológico](#2-stack-tecnológico)
3. [Estructura de ficheros](#3-estructura-de-ficheros)
4. [Arquitectura interna](#4-arquitectura-interna)
5. [Endpoints](#5-endpoints)
6. [Modelo de datos](#6-modelo-de-datos)
7. [Autenticación](#7-autenticación)
8. [Validación de payload](#8-validación-de-payload)
9. [Deduplicación diaria](#9-deduplicación-diaria)
10. [Gestión de errores](#10-gestión-de-errores)
11. [Rate limiting](#11-rate-limiting)
12. [Tests](#12-tests)
13. [Configuración y despliegue](#13-configuración-y-despliegue)
14. [Decisiones de diseño](#14-decisiones-de-diseño)

---

## 1. Contexto

El backend de EHUkene recibe métricas de los agentes Windows desplegados en el parque de equipos, las valida, las almacena en PostgreSQL y las expone mediante endpoints de consulta para los dashboards de Grafana y Metabase.

El sistema complementa Ivanti EPM cubriendo tres métricas que esta herramienta no recoge: degradación de batería, uso real de software (Adobe Acrobat Pro) y tiempo de arranque del sistema.

---

## 2. Stack tecnológico

| Componente | Tecnología | Versión mínima | Motivo |
|---|---|---|---|
| Framework web | FastAPI | 0.111 | Tipado, validación automática, documentación OpenAPI |
| Servidor ASGI | Uvicorn | 0.29 | Par natural de FastAPI; soporte async nativo |
| ORM | SQLAlchemy | 2.0 | API async moderna, soporte para múltiples dialectos |
| Driver PostgreSQL | asyncpg | 0.29 | Driver async nativo, el más rápido disponible |
| Validación | Pydantic | 2.0 | Integrado con FastAPI; validación de invariantes del contrato |
| Configuración | pydantic-settings | 2.0 | Lectura de `.env` con tipado estático |
| Rate limiting | slowapi | 0.1.9 | Wrapper de `limits` para Starlette/FastAPI |
| Base de datos | PostgreSQL | 14+ | Motor principal para producción |
| Tests (BD) | SQLite + aiosqlite | — | BD en memoria para tests sin PostgreSQL real |

### Dependencias (`requirements.txt`)

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
sqlalchemy>=2.0.0
asyncpg>=0.29.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
slowapi>=0.1.9
python-dotenv>=1.0.0
```

---

## 3. Estructura de ficheros

```
ehukene-backend/
│
├── .env.example                        # Variables de entorno — copiar a .env y ajustar
├── .gitignore
├── requirements.txt
├── pytest.ini
│
├── app/
│   ├── main.py                         # Arranque FastAPI, routers, middleware, error handlers
│   ├── config.py                       # Settings via pydantic-settings
│   ├── database.py                     # Engine async, SessionLocal, dependencia get_db
│   │
│   ├── models/                         # ORM — SQLAlchemy 2.0 declarativo
│   │   ├── __init__.py                 # Importa todos los modelos (registra metadata)
│   │   ├── device.py                   # Tabla devices
│   │   ├── telemetry_raw.py            # Tabla telemetry_raw (JSONB + agent_timestamp)
│   │   ├── battery_metrics.py          # Tabla battery_metrics
│   │   ├── software_usage.py           # Tabla software_usage
│   │   └── boot_metrics.py             # Tabla boot_metrics
│   │
│   ├── schemas/                        # Pydantic — validación de request/response
│   │   ├── telemetry.py                # Payload completo del agente + invariantes de contrato
│   │   ├── device.py                   # Register, DeviceListItem, DeviceDetail, LastMetrics
│   │   └── history.py                  # HistoryResponse y tipos por métrica
│   │
│   ├── routers/                        # Un fichero por endpoint o grupo de endpoints
│   │   ├── register.py                 # POST /api/devices/register
│   │   ├── telemetry.py                # POST /api/telemetry
│   │   ├── devices.py                  # GET /api/devices  ·  GET /api/devices/{id}
│   │   └── history.py                  # GET /api/devices/{id}/history
│   │
│   ├── services/                       # Lógica de negocio — sin dependencias de HTTP
│   │   ├── auth.py                     # API Key: generación, hash SHA-256, require_auth
│   │   ├── ingest.py                   # Deduplicación + escritura en todas las tablas
│   │   └── history.py                  # Queries de last_metrics e histórico por rango
│   │
│   └── middleware/
│       └── rate_limit.py               # Instancia de slowapi Limiter + handler 429
│
├── migrations/
│   ├── init.sql                        # Schema completo listo para aplicar con psql
│   └── note_v1_4_boot_source.sql       # Nota de cambio semántico (sin DDL ejecutable)
│
└── tests/
    ├── conftest.py                     # Fixtures: SQLite en memoria, cliente HTTP, device
    ├── test_schemas.py                 # 32 tests — validación Pydantic e invariantes
    └── test_api.py                     # 26 tests — integración HTTP extremo a extremo
```

---

## 4. Arquitectura interna

### Flujo de una petición

```
Cliente (agente / dashboard)
        │
        ▼
   NGINX (reverse proxy, TLS)
        │
        ▼
   Uvicorn (ASGI)
        │
        ▼
   PayloadSizeLimitMiddleware   ← rechaza > 1 MB antes de leer el body
        │
        ▼
   Router FastAPI
        │
        ├── Dependencia: require_auth()   ← valida API Key → devuelve Device
        │
        ├── Pydantic: valida el body       ← tipos, rangos, invariantes del contrato
        │
        └── Handler del endpoint
                │
                ├── services/auth.py       ← autenticación
                ├── services/ingest.py     ← escritura en BD
                └── services/history.py   ← lecturas de BD
                        │
                        ▼
                 AsyncSession (SQLAlchemy)
                        │
                        ▼
                   PostgreSQL
```

### Separación de responsabilidades

Los **routers** solo validan la autenticación, comprueban el tamaño del payload y delegan en los servicios. No contienen lógica de negocio ni queries directas.

Los **services** contienen toda la lógica: deduplicación, inserción, consulta de histórico. No tienen dependencias de FastAPI ni de HTTP — son funciones Python puras que reciben una `AsyncSession`.

Los **schemas** Pydantic validan no solo los tipos sino los invariantes del contrato (por ejemplo, que `battery_status` sea `None` cuando `battery_source` es `"powercfg"`, o que `executions_last_30d ≤ executions_last_60d ≤ executions_last_90d`). Si el payload viola cualquier invariante, el rechazo ocurre antes de tocar la base de datos.

---

## 5. Endpoints

### `POST /api/devices/register`

Registro inicial de un dispositivo nuevo. Devuelve la API Key en claro — **única vez que se expone**. El backend almacena únicamente su hash SHA-256.

**Sin autenticación** en POC. Proteger con IP whitelist en Fase 2.

**Request:**
```json
{
  "hostname": "HOSTNAME-001",
  "requested_by": "sysadmin@dominio.local"
}
```

**Response 201:**
```json
{
  "device_id": "uuid",
  "hostname": "HOSTNAME-001",
  "api_key": "64-char-hex-string",
  "created_at": "2026-03-28T08:00:00"
}
```

**Errores:** `409 DUPLICATE_HOSTNAME` si el hostname ya existe. `422 VALIDATION_ERROR` si el hostname está vacío o contiene caracteres no ASCII.

---

### `POST /api/telemetry`

Recepción de métricas del agente. Es el endpoint central del sistema.

**Autenticación:** cabecera `X-API-Key`.

**Validaciones en orden:**

1. API Key válida y activa → `401 UNAUTHORIZED`
2. `device_id` del payload coincide con el hostname asociado a la key → `403 FORBIDDEN`
3. Pydantic valida tipos, rangos e invariantes → `422 VALIDATION_ERROR`
4. Tamaño del payload ≤ 1 MB → `413 PAYLOAD_TOO_LARGE`
5. No existe registro para este dispositivo en la ventana de deduplicación → `409 DUPLICATE_SUBMISSION`

**Efectos al aceptar:**
- Actualiza `devices.last_seen` y `devices.agent_version`
- Inserta en `telemetry_raw` (auditoría completa)
- Inserta en las tablas tipadas de los plugins presentes en `metrics`

**Response 200:**
```json
{
  "status": "accepted",
  "device_id": "HOSTNAME-001",
  "received_at": "2026-03-28T08:15:02Z"
}
```

---

### `GET /api/devices`

Listado paginado de dispositivos registrados.

**Autenticación:** requerida. En POC cualquier key válida. En Fase 2 se distinguirá entre keys de dispositivo y keys de administración.

**Query params:** `active` (bool, default `true`), `limit` (int, 1-1000, default 100), `offset` (int, default 0).

**Response 200:**
```json
{
  "total": 7000,
  "limit": 100,
  "offset": 0,
  "devices": [
    {
      "device_id": "uuid",
      "hostname": "HOSTNAME-001",
      "first_seen": "2026-01-10T09:00:00",
      "last_seen": "2026-03-28T08:15:00",
      "active": true,
      "agent_version": "1.1.0"
    }
  ]
}
```

---

### `GET /api/devices/{device_id}`

Detalle de un dispositivo con sus últimas métricas conocidas.

**Response 200:**
```json
{
  "device_id": "uuid",
  "hostname": "HOSTNAME-001",
  "first_seen": "2026-01-10T09:00:00",
  "last_seen": "2026-03-28T08:15:00",
  "active": true,
  "agent_version": "1.1.0",
  "last_metrics": {
    "battery": {
      "health_percent": 73.0,
      "battery_status": 2,
      "recorded_at": "2026-03-28T08:15:00"
    },
    "software_usage": [...],
    "boot_time": {
      "last_boot_time": "2026-03-28T07:58:00",
      "boot_duration_seconds": 42,
      "recorded_at": "2026-03-28T08:15:00"
    }
  }
}
```

**Errores:** `404 NOT_FOUND` si el UUID no existe.

---

### `GET /api/devices/{device_id}/history`

Histórico de métricas de un dispositivo por rango temporal.

**Query params:**

| Parámetro | Tipo | Descripción | Defecto |
|---|---|---|---|
| `metric` | string | `battery`, `software_usage` o `boot_time`. Sin valor = todas. | todas |
| `from` | datetime ISO 8601 | Inicio del rango | hace 30 días |
| `to` | datetime ISO 8601 | Fin del rango | ahora |
| `limit` | int (1-365) | Máximo de resultados por métrica | 90 |

**Errores:** `404 NOT_FOUND`, `422 VALIDATION_ERROR` si `metric` no es válido o si `from ≥ to`.

---

### `GET /health`

Endpoint de salud para NGINX y monitorización. Sin autenticación. No aparece en la documentación OpenAPI.

```json
{ "status": "ok", "version": "1.0.0" }
```

---

## 6. Modelo de datos

### `devices`

Registro de cada dispositivo conocido. La API Key se almacena únicamente como hash SHA-256 — nunca en claro.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `UUID` | PK generada automáticamente |
| `hostname` | `VARCHAR(255)` | Único. Nombre del equipo. |
| `api_key_hash` | `VARCHAR(64)` | SHA-256 hex de la API Key |
| `first_seen` | `TIMESTAMP` | Primera conexión |
| `last_seen` | `TIMESTAMP` | Última conexión — actualizado en cada telemetría |
| `active` | `BOOLEAN` | Si el dispositivo está activo |
| `agent_version` | `VARCHAR(20)` | Última versión del agente reportada |

### `telemetry_raw`

Almacén de auditoría. Guarda el payload completo de cada envío. La columna `agent_timestamp` almacena el timestamp del propio agente (del campo `timestamp` del payload) y es la que se usa para la deduplicación diaria.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `BIGSERIAL` | PK |
| `device_id` | `UUID` | FK a `devices` |
| `agent_timestamp` | `TIMESTAMP` | Timestamp del agente — usado para deduplicación |
| `received_at` | `TIMESTAMP` | Timestamp de recepción en el backend |
| `payload` | `JSONB` | Payload completo del agente |

### `battery_metrics`

| Campo | Tipo | Descripción |
|---|---|---|
| `data_source` | `VARCHAR(10)` | `'powercfg'` o `'wmi'` |
| `battery_name` | `VARCHAR(100)` | NULL cuando fuente es `wmi` |
| `design_capacity_wh` | `NUMERIC(10,3)` | Capacidad original en Wh. CHECK > 0 |
| `full_charge_capacity_wh` | `NUMERIC(10,3)` | Capacidad actual en Wh. CHECK >= 0 |
| `health_percent` | `NUMERIC(5,2)` | `(full / design) × 100`. CHECK [0, 150] |
| `battery_status` | `SMALLINT` | NULL cuando fuente es `powercfg` |

### `software_usage`

Una fila por target de software por envío del agente.

| Campo | Tipo | Descripción |
|---|---|---|
| `software_name` | `VARCHAR(100)` | Identificador del programa (`"adobe_acrobat_pro"`) |
| `installed` | `BOOLEAN` | Si está instalado |
| `version` | `VARCHAR(50)` | NULL si no instalado |
| `last_execution` | `TIMESTAMP` | Último uso detectado vía Prefetch |
| `executions_30d` | `INTEGER` | Conteo últimos 30 días. CHECK >= 0 |
| `executions_60d` | `INTEGER` | Conteo últimos 60 días. CHECK >= 0 |
| `executions_90d` | `INTEGER` | Conteo últimos 90 días. CHECK >= 0 |

### `boot_metrics`

| Campo | Tipo | Descripción |
|---|---|---|
| `data_source` | `VARCHAR(15)` | `'event_log'` o `'wmi'` |
| `last_boot_time` | `TIMESTAMP` | Timestamp del último arranque |
| `boot_duration_seconds` | `INTEGER` | NULL cuando fuente es `wmi`. CHECK > 0 |

---

## 7. Autenticación

Cada dispositivo tiene una API Key única generada con `secrets.token_hex(32)` (256 bits de entropía). Se almacena en `devices.api_key_hash` como su hash SHA-256 en hex.

El agente la envía en cada petición en la cabecera:

```
X-API-Key: <64-char-hex-key>
```

La dependencia `require_auth` (en `services/auth.py`) calcula el SHA-256 de la key recibida, busca el hash en BD y devuelve el `Device` correspondiente. Cualquier petición sin key o con key inválida recibe `401 UNAUTHORIZED`.

La rotación de keys se hace registrando el dispositivo de nuevo con el endpoint de registro — pendiente de implementar en Fase 2 sin downtime.

---

## 8. Validación de payload

Los schemas Pydantic en `schemas/telemetry.py` validan el payload completo antes de tocar la base de datos. Además de los tipos básicos, se comprueban los invariantes del contrato v1.4:

**Plugin battery:**
- `battery_source` debe ser `"powercfg"` o `"wmi"`
- `battery_health_percent` en rango `[0.0, 150.0]`
- `battery_design_capacity_wh > 0`
- Cuando `battery_source="wmi"`: `battery_name`, `battery_manufacturer`, `battery_serial` y `battery_chemistry` deben ser `null`
- Cuando `battery_source="powercfg"`: `battery_status` debe ser `null`

**Plugin software_usage:**
- Si `installed=false`: `version` debe ser `null` y todos los conteos deben ser `0`
- Invariante de orden: `executions_last_30d ≤ executions_last_60d ≤ executions_last_90d`
- `last_execution`, si presente, en formato ISO 8601 `"YYYY-MM-DDTHH:MM:SS"`

**Plugin boot_time:**
- `boot_source` debe ser `"event_log"` o `"wmi"`
- Cuando `boot_source="wmi"`: `boot_duration_seconds` debe ser `null`
- `boot_duration_seconds`, si presente, debe ser `> 0`

**Payload raíz:**
- `timestamp` en formato ISO 8601 UTC con sufijo `Z`: `"YYYY-MM-DDTHH:MM:SSZ"`
- `agent_version` en formato semver: `"MAJOR.MINOR.PATCH"`
- `metrics` no puede estar vacío: al menos un plugin debe aportar datos

---

## 9. Deduplicación diaria

El agente está diseñado para enviar una única telemetría por día. El backend actúa como segunda línea de defensa rechazando envíos duplicados.

**Lógica:** al recibir un payload, se comprueba si ya existe un registro en `telemetry_raw` para el mismo `device_id` cuyo `agent_timestamp` cae dentro de una ventana de ±12,5 horas centrada en el `timestamp` del payload entrante (ventana total de 25 horas, configurable en `.env` con `DEDUP_WINDOW_HOURS`).

**Por qué `agent_timestamp` y no `received_at`:** la ventana se calcula sobre el timestamp que el propio agente declara (no sobre cuándo llegó el paquete al servidor). Esto hace la deduplicación determinista e independiente del reloj del servidor, y funciona correctamente tanto en producción como en los tests.

Si se detecta duplicado → `409 DUPLICATE_SUBMISSION`.

---

## 10. Gestión de errores

Todos los errores siguen el mismo formato, sin excepciones:

```json
{
  "error": "CODIGO_DE_ERROR",
  "detail": "Descripción legible del problema"
}
```

Los routers usan `JSONResponse` directamente en lugar de lanzar `HTTPException` para garantizar este formato plano. El único caso donde FastAPI envuelve el error es en los `401` que vienen de la dependencia `require_auth`, donde el formato es `{"detail": {"error": "UNAUTHORIZED", "detail": "..."}}`.

| Código HTTP | `error` | Cuándo |
|---|---|---|
| `400` | `INVALID_PAYLOAD` | JSON no parseable o campo requerido ausente |
| `401` | `UNAUTHORIZED` | API Key ausente o inválida |
| `403` | `FORBIDDEN` | `device_id` no corresponde a la API Key |
| `404` | `NOT_FOUND` | Dispositivo no encontrado |
| `409` | `DUPLICATE_HOSTNAME` | Hostname ya registrado |
| `409` | `DUPLICATE_SUBMISSION` | Telemetría duplicada en la ventana diaria |
| `413` | `PAYLOAD_TOO_LARGE` | Payload supera 1 MB |
| `422` | `VALIDATION_ERROR` | Payload válido como JSON pero que incumple el esquema |
| `429` | `RATE_LIMIT_EXCEEDED` | Demasiadas peticiones por minuto |
| `500` | `INTERNAL_ERROR` | Error interno (sin detalles en producción) |

El manejador global de `RequestValidationError` transforma los errores de Pydantic al formato estándar, mostrando hasta 5 errores de validación en el campo `detail`.

En producción (`ENVIRONMENT=production`), el manejador de `500` no expone el mensaje de la excepción.

---

## 11. Rate limiting

Implementado con `slowapi` sobre el límite por IP remota. El valor por defecto es 60 peticiones/minuto, configurable en `.env` con `RATE_LIMIT_PER_MINUTE`.

Si el backend está detrás de NGINX, `slowapi` lee automáticamente la cabecera `X-Forwarded-For` para identificar la IP real del cliente.

---

## 12. Tests

**58 tests — 100% en verde.**

### Tests de schemas (`test_schemas.py`) — 32 tests

Validan la lógica de `schemas/telemetry.py` directamente, sin BD ni servidor HTTP. Cubren todos los invariantes del contrato v1.4 para los tres plugins.

Ejemplos:
- Payload completo con fuente `powercfg` y fallback `wmi`
- `health_percent` en límite 150.0 (aceptado) y 160.0 (rechazado)
- `battery_status != null` con `battery_source="powercfg"` (rechazado)
- `installed=false` con `version` no null (rechazado)
- Invariante de orden `30d ≤ 60d ≤ 90d` violado (rechazado)
- `boot_source="wmi"` con `boot_duration_seconds != null` (rechazado)

### Tests de integración (`test_api.py`) — 26 tests

Usan `httpx.AsyncClient` con `ASGITransport` (sin red real) y SQLite en memoria como BD. Cubren el flujo completo HTTP → validación → BD → respuesta.

**Fixture de BD:** cada test crea todas las tablas antes de ejecutarse y las destruye al terminar. Cada petición HTTP dentro de un test abre su propia sesión y hace commit, replicando exactamente el comportamiento de producción.

Ejemplos:
- Registro exitoso y hostname duplicado
- Telemetría completa aceptada, sin key (401), key inválida (401), device_id incorrecto (403)
- Envío duplicado rechazado (409)
- Detalle de dispositivo con y sin métricas
- Histórico con filtro por métrica y por rango temporal
- `from ≥ to` rechazado (422), métrica inválida rechazada (422)

### Ejecutar los tests

```bash
pip install pytest pytest-asyncio httpx aiosqlite
pytest tests/ -v
```

---

## 13. Configuración y despliegue

### Variables de entorno (`.env`)

| Variable | Descripción | Defecto |
|---|---|---|
| `DATABASE_URL` | Conexión PostgreSQL con driver asyncpg | `postgresql+asyncpg://ehukene:changeme@localhost:5432/ehukene` |
| `SECRET_KEY` | Secreto interno (mínimo 32 chars) | `change-this-in-production` |
| `RATE_LIMIT_PER_MINUTE` | Peticiones máximas por IP/minuto | `60` |
| `DEDUP_WINDOW_HOURS` | Ventana de deduplicación diaria en horas | `25` |
| `MAX_PAYLOAD_BYTES` | Tamaño máximo del payload en bytes | `1048576` (1 MB) |
| `ENVIRONMENT` | `development` o `production` | `development` |

En `development`, el ORM imprime todas las queries SQL en el log y la documentación OpenAPI (`/docs`, `/redoc`) está activa. En `production`, ambas se desactivan.

### Aplicar el schema de BD

```bash
psql -U ehukene -d ehukene -f migrations/init.sql
```

### Arranque en desarrollo

```bash
pip install -r requirements.txt
cp .env.example .env
# Editar .env con DATABASE_URL y SECRET_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Arranque en producción (detrás de NGINX)

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
```

### Configuración NGINX recomendada

```nginx
server {
    listen 443 ssl;
    server_name ehukene.dominio.local;

    ssl_certificate     /etc/ssl/certs/ehukene.crt;
    ssl_certificate_key /etc/ssl/private/ehukene.key;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Forwarded-For $remote_addr;
        proxy_read_timeout 30s;
    }
}
```

---

## 14. Decisiones de diseño

| Decisión | Elección | Motivo |
|---|---|---|
| **Async vs sync** | Async (asyncpg + SQLAlchemy async) | El parque puede generar ráfagas de envíos al inicio de jornada. Async evita bloquear el event loop durante las queries |
| **Driver PostgreSQL** | asyncpg | Único driver async nativo para PostgreSQL; mejor rendimiento que psycopg3 async en benchmarks |
| **Formato de errores** | `JSONResponse` directo en routers | Evita el wrapping `{"detail": {...}}` que añade FastAPI cuando se lanza `HTTPException`. El formato queda exactamente como define el contrato |
| **Deduplicación por `agent_timestamp`** | `telemetry_raw.agent_timestamp` | Comparar contra el timestamp del agente (no `received_at`) hace la ventana determinista e independiente del reloj del servidor. Evita edge cases cuando el servidor está en timezone diferente o hay latencia de red |
| **Columna `agent_timestamp` en `telemetry_raw`** | Campo dedicado | Alternativa descartada: extraerlo del JSONB con `payload->>'timestamp'`. Un campo nativo es más eficiente para el índice de deduplicación y más claro semánticamente |
| **Validación de invariantes en Pydantic** | `@model_validator` y `@field_validator` | Los invariantes del contrato se comprueban antes de tocar la BD, con mensajes de error precisos para el agente. Alternativa descartada: validar en el router o en el service, lo que complica las pruebas unitarias |
| **`JSONB` con `with_variant(JSON(), "sqlite")`** | Tipo adaptable por dialecto | Permite usar SQLite en memoria para los tests de integración sin cambiar el modelo ni los tests. En producción PostgreSQL usa JSONB nativo |
| **Tests con sesión por petición** | `override_get_db` abre sesión nueva por request | Replica exactamente el comportamiento de producción. La alternativa (sesión compartida por test) provocaba que la deduplicación no detectara el primer insert porque el commit no era visible en la misma transacción |
| **Sin Alembic en POC** | `init.sql` manual | El schema es estable en POC. Alembic se añadirá en Fase 2 cuando empiecen las migraciones incrementales |
| **Rate limiting por IP** | slowapi | Simple, sin estado externo. En Fase 2 se puede añadir rate limiting por API Key para proteger contra abuse de un dispositivo concreto |
| **Documentación OpenAPI desactivada en producción** | `docs_url=None` | Reduce superficie de ataque. Los dashboards (Grafana, Metabase) acceden directamente a PostgreSQL, no a la API |
| **`boot_source` explícito en el plugin** | Campo declarado en el contrato v1.4 | La versión anterior del contrato omitía este campo y el backend lo infería de `boot_duration_seconds=None → fuente wmi`. La inferencia es frágil ante cambios futuros del plugin. El campo explícito es simétrico con `battery_source` y elimina la dependencia semántica |
