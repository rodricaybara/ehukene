-- =============================================================================
-- EHUkene — telemetry_raw.agent_timestamp
-- Corrección de deduplicación diaria · 2026-04-15
--
-- Aplicar manualmente:
--   psql -U ehukene -d ehukene -f migrations/add_agent_timestamp_to_telemetry_raw.sql
-- =============================================================================

ALTER TABLE telemetry_raw
    ADD COLUMN IF NOT EXISTS agent_timestamp TIMESTAMP NULL;

UPDATE telemetry_raw
SET agent_timestamp = received_at
WHERE agent_timestamp IS NULL;

ALTER TABLE telemetry_raw
    ALTER COLUMN agent_timestamp SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_telemetry_raw_device_agent_time
    ON telemetry_raw (device_id, agent_timestamp DESC);
