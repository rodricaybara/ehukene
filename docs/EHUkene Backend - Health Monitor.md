# 🗄️ EHUkene Backend - Health Monitor

Vamos a diseñar el backend para esta nueva métrica. Analicemos primero qué tenemos que almacenar:

---

## 📊 Análisis de Datos a Almacenar

Del JSON que nos llega del agente, tenemos **8 tipos de métricas**:

### 1. **CPU** (simple)
```json
{
  "load_percentage": 12,
  "status": "ok"
}
```
→ Tabla: `cpu_metrics`

### 2. **Memoria** (simple)
```json
{
  "total_kb": 8264704,
  "free_kb": 1514588,
  "usage_pct": 81.67,
  "status": "warning"
}
```
→ Tabla: `memory_metrics`

### 3. **Disco** (simple)
```json
{
  "drive": "C:",
  "total_gb": 238.06,
  "free_gb": 15.6,
  "free_pct": 6.55,
  "status": "critical"
}
```
→ Tabla: `disk_metrics`

### 4. **Eventos** (compleja - con arrays)
```json
{
  "critical_count": 0,
  "error_count": 4,
  "filtered_count": 25,
  "top_sources": [...],
  "sample_events": [...],
  "status": "ok"
}
```
→ Tabla: `event_metrics` + JSONB para top_sources y sample_events

### 5. **Dominio** (simple)
```json
{
  "secure_channel": true,
  "status": "ok"
}
```
→ Tabla: `domain_metrics`

### 6. **Uptime** (simple)
```json
{
  "last_boot": "2026-04-14T07:23:42Z",
  "days": 0.3,
  "status": "ok"
}
```
→ Tabla: `uptime_metrics`

### 7. **Boot Time** ⭐ (nueva - simple)
```json
{
  "last_boot_time": "2026-04-02T10:54:57",
  "boot_duration_seconds": 115,
  "source": "event_log",
  "status": "ok"
}
```
→ Tabla: `boot_time_metrics` (ya existe en el sistema, pero hay que ajustarla)

### 8. **Servicios** (compleja - array de objetos)
```json
[
  {
    "name": "SepMasterService",
    "display_name": "SepMasterService",
    "state": "Running",
    "startup_type": "Auto",
    "tier": 1,
    "status": "ok"
  },
  ...
]
```
→ Tabla: `service_metrics` (una fila por servicio por envío)

---

## 🗃️ Propuesta de Esquema de Base de Datos

### Estrategia de diseño:

1. **Reutilizar la tabla `devices` existente** (UUID, hostname, etc.)
2. **Reutilizar `telemetry_raw`** para auditoría completa del payload
3. **Crear tablas específicas** para cada métrica del health_monitor
4. **No mezclar** con las métricas existentes (battery, software_usage, boot_time del otro plugin)

---

### Tabla 1: `health_cpu_metrics`

```sql
CREATE TABLE health_cpu_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,  -- timestamp del agente
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    load_percentage     SMALLINT        NOT NULL CHECK (load_percentage BETWEEN 0 AND 100),
    status              VARCHAR(20)     NOT NULL  -- ok, warning, critical, error
);

CREATE INDEX idx_health_cpu_device_time ON health_cpu_metrics (device_id, recorded_at DESC);
```

---

### Tabla 2: `health_memory_metrics`

```sql
CREATE TABLE health_memory_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    total_kb            BIGINT          NOT NULL CHECK (total_kb > 0),
    free_kb             BIGINT          NOT NULL CHECK (free_kb >= 0),
    usage_pct           NUMERIC(5,2)    NOT NULL CHECK (usage_pct BETWEEN 0 AND 100),
    status              VARCHAR(20)     NOT NULL
);

CREATE INDEX idx_health_memory_device_time ON health_memory_metrics (device_id, recorded_at DESC);
```

---

### Tabla 3: `health_disk_metrics`

```sql
CREATE TABLE health_disk_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    drive               VARCHAR(10)     NOT NULL,  -- "C:", "D:", etc.
    total_gb            NUMERIC(10,2)   NOT NULL CHECK (total_gb > 0),
    free_gb             NUMERIC(10,2)   NOT NULL CHECK (free_gb >= 0),
    free_pct            NUMERIC(5,2)    NOT NULL CHECK (free_pct BETWEEN 0 AND 100),
    status              VARCHAR(20)     NOT NULL
);

CREATE INDEX idx_health_disk_device_time ON health_disk_metrics (device_id, recorded_at DESC);
```

---

### Tabla 4: `health_event_metrics`

```sql
CREATE TABLE health_event_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    critical_count      INTEGER         NOT NULL CHECK (critical_count >= 0),
    error_count         INTEGER         NOT NULL CHECK (error_count >= 0),
    filtered_count      INTEGER         NOT NULL CHECK (filtered_count >= 0),
    top_sources         JSONB           NULL,  -- [{"provider": "...", "count": N}, ...]
    sample_events       JSONB           NULL,  -- [{"event_id": N, "provider": "...", ...}, ...]
    status              VARCHAR(20)     NOT NULL
);

CREATE INDEX idx_health_event_device_time ON health_event_metrics (device_id, recorded_at DESC);
```

**Nota:** `top_sources` y `sample_events` en JSONB porque son arrays variables.

---

### Tabla 5: `health_domain_metrics`

```sql
CREATE TABLE health_domain_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    secure_channel      BOOLEAN         NOT NULL,
    status              VARCHAR(20)     NOT NULL
);

CREATE INDEX idx_health_domain_device_time ON health_domain_metrics (device_id, recorded_at DESC);
```

---

### Tabla 6: `health_uptime_metrics`

```sql
CREATE TABLE health_uptime_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_boot           TIMESTAMP       NOT NULL,
    days                NUMERIC(5,1)    NOT NULL CHECK (days >= 0),
    status              VARCHAR(20)     NOT NULL
);

CREATE INDEX idx_health_uptime_device_time ON health_uptime_metrics (device_id, recorded_at DESC);
```

---

### Tabla 7: `health_boot_time_metrics`

**IMPORTANTE:** Ya existe `boot_metrics` en el sistema (del plugin boot_time original). Creamos una tabla separada para el health_monitor.

```sql
CREATE TABLE health_boot_time_metrics (
    id                      BIGSERIAL       PRIMARY KEY,
    device_id               UUID            NOT NULL REFERENCES devices(id),
    recorded_at             TIMESTAMP       NOT NULL,
    received_at             TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_boot_time          TIMESTAMP       NULL,  -- puede ser null si error
    boot_duration_seconds   INTEGER         NULL CHECK (boot_duration_seconds > 0),
    source                  VARCHAR(20)     NULL,  -- "event_log", "wmi", null si error
    status                  VARCHAR(20)     NOT NULL  -- optimal, ok, degraded, critical, unknown, error
);

CREATE INDEX idx_health_boot_time_device_time ON health_boot_time_metrics (device_id, recorded_at DESC);
```

---

### Tabla 8: `health_service_metrics`

**Una fila por servicio por envío**. Si hay 11 servicios monitorizados, se insertan 11 filas cada vez.

```sql
CREATE TABLE health_service_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    service_name        VARCHAR(100)    NOT NULL,
    display_name        VARCHAR(255)    NULL,
    state               VARCHAR(50)     NOT NULL,  -- Running, Stopped, NotFound, Error
    startup_type        VARCHAR(50)     NULL,      -- Auto, Manual, Disabled, null
    tier                SMALLINT        NOT NULL CHECK (tier BETWEEN 0 AND 3),
    status              VARCHAR(20)     NOT NULL   -- ok, warning, critical, not_available, error
);

CREATE INDEX idx_health_service_device_time ON health_service_metrics (device_id, recorded_at DESC);
CREATE INDEX idx_health_service_device_name ON health_service_metrics (device_id, service_name, recorded_at DESC);
```

---

## 🏗️ Estructura de Código Backend

Siguiendo el patrón existente del proyecto:

```
ehukene-backend/
├── app/
│   ├── models/
│   │   ├── health_cpu_metrics.py
│   │   ├── health_memory_metrics.py
│   │   ├── health_disk_metrics.py
│   │   ├── health_event_metrics.py
│   │   ├── health_domain_metrics.py
│   │   ├── health_uptime_metrics.py
│   │   ├── health_boot_time_metrics.py
│   │   └── health_service_metrics.py
│   │
│   ├── schemas/
│   │   └── health_telemetry.py        # Validación del payload completo
│   │
│   ├── routers/
│   │   └── health_telemetry.py        # POST /api/health/telemetry
│   │
│   └── services/
│       └── health_ingest.py           # Lógica de inserción en las 8 tablas
│
└── migrations/
    └── health_monitor_tables.sql      # DDL de todas las tablas
```

---

## 📝 Propuesta de Implementación

1. **DDL (SQL)** - Crear el script de migración con todas las tablas
2. **Models (SQLAlchemy)** - Los 8 modelos ORM
3. **Schemas (Pydantic)** - Validación del payload de entrada
4. **Service (ingest)** - Lógica para insertar en las 8 tablas
5. **Router** - Endpoint `POST /api/health/telemetry`







