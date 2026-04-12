# EHUkene — Cambios al contrato v1.2
## Derivados de la implementación del plugin `boot_time`

**Versión resultante:** 1.3
**Fecha:** 2026-03-30
**Afecta a:** `ehukene_contratos_v1_2.md`

---

## Cambio 1 — Privilegios del plugin `boot_time` (§1.5)

**Sección:** `1.5 › Plugin: boot_time`

**Antes:**
```
Privilegios mínimos   : Usuario estándar
```

**Después:**
```
Privilegios mínimos   : Administrador local
```

**Motivo:** La fuente primaria del plugin es el canal
`Microsoft-Windows-Diagnostics-Performance/Operational`, cuya lectura mediante
`Get-WinEvent` requiere permisos de administrador local. El agente ya se ejecuta
con privilegios elevados por requisito de los plugins `battery` y
`software_usage`, por lo que este cambio no tiene impacto operativo.

---

## Cambio 2 — Fuente de datos del plugin `boot_time` (§1.5)

**Sección:** `1.5 › Plugin: boot_time`

**Antes:** el contrato v1.2 no especificaba la fuente de datos ni la estrategia
de fallback del plugin; solo describía los campos de retorno.

**Después:** añadir el bloque de fuentes antes de la tabla de campos:

```
Fuente principal : Event Log — Event ID 100,
                   canal Microsoft-Windows-Diagnostics-Performance/Operational
                   (Get-WinEvent vía subprocess PowerShell)
Fallback         : WMI — Win32_OperatingSystem.LastBootUpTime
                   (Get-WmiObject vía subprocess PowerShell)
```

**Estrategia:**

```
1. Event Log (Event ID 100) → last_boot_time + boot_duration_seconds
        ↓ si el canal no está disponible, no tiene eventos ID 100, o falla
2. WMI (Win32_OperatingSystem) → last_boot_time solo, boot_duration_seconds=None
        ↓ si falla
3. Devuelve None
```

**Motivo:** la implementación real usa dos fuentes con responsabilidades
distintas. El Event ID 100 proporciona ambos campos desde un único evento,
eliminando la necesidad de correlacionar fuentes independientes. WMI actúa
como fallback exclusivo para `last_boot_time` cuando el Event Log no está
disponible.

---

## Cambio 3 — Invariante del plugin `boot_time` (§1.5)

**Sección:** `1.5 › Plugin: boot_time › Invariantes`

**Antes:**
```
- El plugin nunca devuelve None completo: si WMI está disponible,
  devuelve el dict con al menos last_boot_time.
```

**Después:**
```
- El plugin nunca devuelve None completo: si el Event Log o WMI están
  disponibles, devuelve el dict con al menos last_boot_time.
- boot_duration_seconds es None cuando la fuente es WMI (dato no
  disponible vía Win32_OperatingSystem).
```

**Motivo:** el invariante original solo mencionaba WMI. Con la fuente primaria
siendo el Event Log, el invariante debe reflejar que cualquiera de las dos
fuentes es suficiente para garantizar `last_boot_time`. Se añade además el
invariante explícito sobre `boot_duration_seconds=None` en el fallback WMI,
que antes estaba implícito en la descripción del campo.

---

## Cambio 4 — Tabla `boot_metrics`: columna `data_source` (§3.6)

**Sección:** `3.6 › Tabla: boot_metrics`

**Antes:**
```sql
CREATE TABLE boot_metrics (
    id                      BIGSERIAL   PRIMARY KEY,
    device_id               UUID        NOT NULL REFERENCES devices(id),
    recorded_at             TIMESTAMP   NOT NULL,
    received_at             TIMESTAMP   NOT NULL DEFAULT NOW(),
    last_boot_time          TIMESTAMP   NOT NULL,
    boot_duration_seconds   INTEGER     NULL CHECK (boot_duration_seconds > 0)
);
```

**Después:**
```sql
CREATE TABLE boot_metrics (
    id                      BIGSERIAL       PRIMARY KEY,
    device_id               UUID            NOT NULL REFERENCES devices(id),
    recorded_at             TIMESTAMP       NOT NULL,
    received_at             TIMESTAMP       NOT NULL DEFAULT NOW(),
    data_source             VARCHAR(15)     NOT NULL,   -- 'event_log' | 'wmi'
    last_boot_time          TIMESTAMP       NOT NULL,
    boot_duration_seconds   INTEGER         NULL CHECK (boot_duration_seconds > 0)
);

CREATE INDEX idx_boot_device_time ON boot_metrics (device_id, recorded_at DESC);
```

Restricciones actualizadas:

| Campo | Restricción |
|---|---|
| `data_source` | Solo `'event_log'` o `'wmi'`. Validado en aplicación antes de insertar. |
| `last_boot_time` | Almacenado en UTC. El backend convierte desde la hora local del agente. |
| `boot_duration_seconds` | `NULL` si `data_source = 'wmi'` o si el dato no estaba disponible. Si presente, estrictamente mayor que 0. |

**Motivo:** siguiendo el patrón de `battery_metrics.data_source`, registrar la
fuente de cada registro permite a los dashboards filtrar o ponderar los datos
según su procedencia y detectar equipos donde el Event Log no está disponible.

---

## Resumen para el Apéndice C del contrato

Añadir las siguientes filas al apéndice de cambios al pasar de v1.2 a v1.3:

| Cambio | Sección | Motivo |
|---|---|---|
| Privilegios de `boot_time` elevados a administrador local | 1.5 | `Get-WinEvent` sobre el canal Diagnostics-Performance requiere permisos elevados |
| Fuente primaria de `boot_time` definida: Event ID 100 con fallback WMI | 1.5 | El contrato v1.2 no especificaba las fuentes; la implementación las hace explícitas |
| Invariantes de `boot_time` ampliados: mención del Event Log y `boot_duration_seconds=None` en fallback WMI | 1.5 | Refleja el comportamiento real de las dos fuentes |
| Columna `data_source` añadida a `boot_metrics` | 3.6 | Trazabilidad de la fuente de cada registro, en línea con `battery_metrics` |
