-- =============================================================================
-- EHUkene — Inicialización de base de datos
-- Versión de contratos: 1.4
-- PostgreSQL 14+
--
-- Uso:
--   psql -U postgres -c "CREATE DATABASE ehukene;"
--   psql -U postgres -d ehukene -f ehukene_db_init.sql
-- =============================================================================

-- Extensión necesaria para gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- =============================================================================
-- Tabla: devices
-- Registro de cada dispositivo conocido por el sistema.
-- =============================================================================

CREATE TABLE IF NOT EXISTS devices (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    hostname        VARCHAR(255)    NOT NULL,
    api_key_hash    VARCHAR(64)     NOT NULL,       -- SHA-256 hex de la API Key
    first_seen      TIMESTAMP       NOT NULL,
    last_seen       TIMESTAMP       NOT NULL,
    active          BOOLEAN         NOT NULL DEFAULT TRUE,
    agent_version   VARCHAR(20)     NULL,           -- Última versión semver reportada

    CONSTRAINT chk_devices_seen CHECK (first_seen <= last_seen)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_hostname ON devices (hostname);
CREATE INDEX        IF NOT EXISTS idx_devices_active   ON devices (active);

COMMENT ON TABLE  devices                IS 'Registro de cada dispositivo conocido por el sistema.';
COMMENT ON COLUMN devices.api_key_hash   IS 'SHA-256 hex de la API Key. La key en claro no se almacena.';
COMMENT ON COLUMN devices.agent_version  IS 'Última versión semver reportada por el agente. NULL si aún no ha enviado ningún payload.';


-- =============================================================================
-- Tabla: telemetry_raw
-- Almacén de auditoría: guarda el payload completo de cada envío.
-- Retención: 12 meses. Candidato a particionado mensual con pg_partman (Fase 3).
-- =============================================================================

CREATE TABLE IF NOT EXISTS telemetry_raw (
    id          BIGSERIAL   PRIMARY KEY,
    device_id   UUID        NOT NULL REFERENCES devices(id),
    received_at TIMESTAMP   NOT NULL DEFAULT NOW(),
    payload     JSONB       NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telemetry_raw_device_time
    ON telemetry_raw (device_id, received_at DESC);

COMMENT ON TABLE  telemetry_raw             IS 'Payload completo de cada envío del agente. Fuente de auditoría y punto de extensión para métricas sin tabla tipada propia.';
COMMENT ON COLUMN telemetry_raw.received_at IS 'Momento de recepción en el backend, no el timestamp del agente.';
COMMENT ON COLUMN telemetry_raw.payload     IS 'JSON completo tal como lo envió el agente. Debe contener al menos device_id, timestamp y metrics.';


-- =============================================================================
-- Tabla: battery_metrics
-- Métricas de salud y estado de batería por dispositivo.
-- =============================================================================

CREATE TABLE IF NOT EXISTS battery_metrics (
    id                          BIGSERIAL       PRIMARY KEY,
    device_id                   UUID            NOT NULL REFERENCES devices(id),
    recorded_at                 TIMESTAMP       NOT NULL,       -- timestamp del agente (UTC)
    received_at                 TIMESTAMP       NOT NULL DEFAULT NOW(),
    data_source                 VARCHAR(10)     NOT NULL,       -- 'powercfg' | 'wmi'
    battery_name                VARCHAR(100)    NULL,           -- solo cuando data_source = 'powercfg'
    battery_manufacturer        VARCHAR(100)    NULL,           -- solo cuando data_source = 'powercfg'
    battery_serial              VARCHAR(50)     NULL,           -- solo cuando data_source = 'powercfg'
    battery_chemistry           VARCHAR(10)     NULL,           -- solo cuando data_source = 'powercfg'
    design_capacity_wh          NUMERIC(10, 3)  NOT NULL CHECK (design_capacity_wh > 0),
    full_charge_capacity_wh     NUMERIC(10, 3)  NOT NULL CHECK (full_charge_capacity_wh >= 0),
    health_percent              NUMERIC(5, 2)   NOT NULL CHECK (health_percent BETWEEN 0 AND 150),
    battery_status              SMALLINT        NULL,           -- NULL cuando data_source = 'powercfg'

    CONSTRAINT chk_battery_data_source
        CHECK (data_source IN ('powercfg', 'wmi'))
);

CREATE INDEX IF NOT EXISTS idx_battery_device_time
    ON battery_metrics (device_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_battery_health
    ON battery_metrics (device_id, health_percent);

COMMENT ON TABLE  battery_metrics                    IS 'Métricas de salud y estado de batería. Una fila por dispositivo por día.';
COMMENT ON COLUMN battery_metrics.data_source        IS 'Fuente de datos: powercfg (primaria) o wmi (fallback).';
COMMENT ON COLUMN battery_metrics.recorded_at        IS 'Timestamp de recogida de la métrica en el agente, convertido a UTC por el backend.';
COMMENT ON COLUMN battery_metrics.design_capacity_wh IS 'Capacidad de diseño original en Wh con 3 decimales. Estrictamente mayor que 0.';
COMMENT ON COLUMN battery_metrics.full_charge_capacity_wh IS 'Capacidad máxima actual en Wh con 3 decimales. Puede ser 0 en baterías muy degradadas.';
COMMENT ON COLUMN battery_metrics.health_percent     IS '(full_charge / design) * 100, redondeado a 2 decimales. Rango [0, 150].';
COMMENT ON COLUMN battery_metrics.battery_status     IS 'Código WMI de estado (rango esperado [1,11]). NULL cuando data_source = powercfg.';


-- =============================================================================
-- Tabla: software_usage
-- Métricas de instalación y uso de software monitorizado.
-- =============================================================================

CREATE TABLE IF NOT EXISTS software_usage (
    id              BIGSERIAL       PRIMARY KEY,
    device_id       UUID            NOT NULL REFERENCES devices(id),
    recorded_at     TIMESTAMP       NOT NULL,
    received_at     TIMESTAMP       NOT NULL DEFAULT NOW(),
    software_name   VARCHAR(100)    NOT NULL,
    installed       BOOLEAN         NOT NULL,
    version         VARCHAR(50)     NULL,
    last_execution  TIMESTAMP       NULL,
    executions_30d  INTEGER         NOT NULL DEFAULT 0 CHECK (executions_30d >= 0),
    executions_60d  INTEGER         NOT NULL DEFAULT 0 CHECK (executions_60d >= 0),
    executions_90d  INTEGER         NOT NULL DEFAULT 0 CHECK (executions_90d >= 0),

    -- El invariante 30d <= 60d <= 90d se valida en la capa de aplicación,
    -- no aquí, porque PostgreSQL no permite comparar columnas en un CHECK
    -- sin funciones adicionales que compliquen el esquema.
    CONSTRAINT chk_software_version_if_not_installed
        CHECK (installed = TRUE OR version IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_software_device_name_time
    ON software_usage (device_id, software_name, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_software_name_installed
    ON software_usage (software_name, installed);

COMMENT ON TABLE  software_usage                IS 'Métricas de instalación y uso de software monitorizado. Una fila por dispositivo por software por día.';
COMMENT ON COLUMN software_usage.software_name  IS 'Identificador del programa según software_targets.json. Ejemplo: adobe_acrobat_pro.';
COMMENT ON COLUMN software_usage.last_execution IS 'Almacenado en UTC. El backend convierte desde la hora local del agente.';
COMMENT ON COLUMN software_usage.executions_30d IS 'Número de ejecuciones detectadas vía Prefetch en los últimos 30 días.';
COMMENT ON COLUMN software_usage.executions_60d IS 'Número de ejecuciones detectadas vía Prefetch en los últimos 60 días.';
COMMENT ON COLUMN software_usage.executions_90d IS 'Número de ejecuciones detectadas vía Prefetch en los últimos 90 días. Invariante de aplicación: 30d <= 60d <= 90d.';


-- =============================================================================
-- Tabla: boot_metrics
-- Métricas del proceso de arranque del sistema.
-- =============================================================================

CREATE TABLE IF NOT EXISTS boot_metrics (
    id                      BIGSERIAL       PRIMARY KEY,
    device_id               UUID            NOT NULL REFERENCES devices(id),
    recorded_at             TIMESTAMP       NOT NULL,
    received_at             TIMESTAMP       NOT NULL DEFAULT NOW(),
    data_source             VARCHAR(15)     NOT NULL,   -- 'event_log' | 'wmi'
    last_boot_time          TIMESTAMP       NOT NULL,
    boot_duration_seconds   INTEGER         NULL CHECK (boot_duration_seconds > 0),

    CONSTRAINT chk_boot_data_source
        CHECK (data_source IN ('event_log', 'wmi')),

    -- boot_duration_seconds debe ser NULL cuando la fuente es WMI
    CONSTRAINT chk_boot_duration_wmi
        CHECK (data_source != 'wmi' OR boot_duration_seconds IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_boot_device_time
    ON boot_metrics (device_id, recorded_at DESC);

COMMENT ON TABLE  boot_metrics                        IS 'Métricas del proceso de arranque del sistema. Una fila por dispositivo por día.';
COMMENT ON COLUMN boot_metrics.data_source            IS 'Fuente: event_log (Event ID 100, incluye duración) o wmi (solo timestamp de arranque). Proviene del campo boot_source del payload del agente.';
COMMENT ON COLUMN boot_metrics.last_boot_time         IS 'Almacenado en UTC. El backend convierte desde la hora local del agente.';
COMMENT ON COLUMN boot_metrics.boot_duration_seconds  IS 'Duración total del arranque en segundos. NULL si data_source = wmi. Si presente, estrictamente mayor que 0.';


-- =============================================================================
-- Tabla: agent_versions  (Fase 2 — auto-update)
-- Manifiesto de versiones servido por GET /api/agent/version.
-- =============================================================================

CREATE TABLE IF NOT EXISTS agent_versions (
    id              SERIAL          PRIMARY KEY,
    version         VARCHAR(20)     NOT NULL,
    artifact_type   VARCHAR(20)     NOT NULL,   -- 'core' | 'plugin'
    artifact_name   VARCHAR(100)    NOT NULL,   -- 'agent' | nombre del plugin
    download_url    VARCHAR(500)    NOT NULL,
    checksum_sha256 VARCHAR(64)     NOT NULL,
    published_at    TIMESTAMP       NOT NULL DEFAULT NOW(),
    active          BOOLEAN         NOT NULL DEFAULT TRUE,

    CONSTRAINT chk_agent_versions_artifact_type
        CHECK (artifact_type IN ('core', 'plugin')),

    CONSTRAINT chk_agent_versions_checksum_len
        CHECK (length(checksum_sha256) = 64)
);

-- Solo puede haber una versión activa por artefacto
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_versions_active
    ON agent_versions (artifact_type, artifact_name, active)
    WHERE active = TRUE;

COMMENT ON TABLE  agent_versions                  IS 'Manifiesto de versiones para auto-actualización del agente. Fase 2.';
COMMENT ON COLUMN agent_versions.artifact_type    IS 'core (ejecutable principal) o plugin (módulo .py).';
COMMENT ON COLUMN agent_versions.artifact_name    IS 'agent para el core; nombre del plugin (p.ej. battery) para plugins.';
COMMENT ON COLUMN agent_versions.checksum_sha256  IS 'SHA-256 en hex del artefacto descargable. Exactamente 64 caracteres.';
COMMENT ON COLUMN agent_versions.active           IS 'Solo puede haber una versión activa por artefacto (garantizado por índice parcial único).';


-- =============================================================================
-- Rol de aplicación
-- Usuario con privilegios mínimos para el backend FastAPI.
-- Ajustar la contraseña antes del despliegue.
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ehukene_app') THEN
        CREATE ROLE ehukene_app LOGIN PASSWORD 'CAMBIAR_EN_PRODUCCION';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE ehukene TO ehukene_app;
GRANT USAGE   ON SCHEMA public     TO ehukene_app;

GRANT SELECT, INSERT, UPDATE ON TABLE
    devices,
    telemetry_raw,
    battery_metrics,
    software_usage,
    boot_metrics,
    agent_versions
TO ehukene_app;

-- Acceso a las secuencias generadas por BIGSERIAL / SERIAL
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehukene_app;
