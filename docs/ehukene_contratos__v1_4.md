# EHUkene — Contratos del Sistema
## Documento de referencia de diseño

**Versión:** 1.5  
**Estado:** Diseño  
**Fecha:** 2026-04-08  
**Relacionado con:** Documento técnico v1.0 · Features auto-update y CLI v1.0

> Este documento establece los contratos formales del sistema. Nada que no esté definido aquí debe implementarse. Cualquier desviación respecto a este documento es un bug de diseño, no de código.

---

## Índice

1. [Contrato de plugins — Interfaz `collect()`](#1-contrato-de-plugins)
2. [Payload del agente — Estructura de envío](#2-payload-del-agente)
3. [Modelo de datos — Esquema de base de datos](#3-modelo-de-datos)
4. [API Backend — Endpoints, request/response, errores](#4-api-backend)

---

## 1. Contrato de plugins

### 1.1 Reglas generales

Un plugin es un módulo Python ubicado en `agent/plugins/`. Para ser reconocido por el sistema debe cumplir **todas** las siguientes condiciones:

- El nombre del fichero coincide con el nombre del plugin declarado en `config.json`.
- Exporta exactamente una función pública: `collect()`.
- `collect()` no acepta argumentos.
- `collect()` devuelve `dict` o `None`. Nunca lanza excepciones al caller.
- `collect()` no tiene efectos secundarios observables fuera de la lectura de métricas (no escribe en disco, no envía datos, no modifica el registro).
- El tiempo máximo de ejecución de `collect()` es **30 segundos**. El `plugin_loader` cancelará la ejecución pasado ese tiempo y tratará el resultado como `None`.

### 1.2 Firma

```python
def collect() -> dict | None:
    ...
```

### 1.3 Valor de retorno

| Caso | Valor devuelto | Comportamiento del collector |
|---|---|---|
| Éxito | `dict` con al menos una clave | Se incluye en el payload de envío |
| Equipo no aplica (p.ej. sin batería) | `None` | Se omite silenciosamente del payload |
| Error interno recuperable | `None` (capturado internamente) | Se omite y se registra en log local |
| Excepción no capturada | `None` (capturado por el loader) | Se omite, se registra el traceback en log local |

### 1.4 Tipos permitidos en el dict de retorno

Los valores del diccionario deben ser serializables a JSON. Tipos permitidos:

| Tipo Python | Ejemplo |
|---|---|
| `int` | `42` |
| `float` | `73.4` |
| `str` | `"24.0.0"` |
| `bool` | `True` |
| `None` | `None` (campo sin dato, distinto de omitir la clave) |
| `str` ISO 8601 para fechas | `"2026-03-28T08:15:00"` |
| `list[dict]` | Lista homogénea de objetos planos. Los dicts de la lista solo contienen tipos primitivos ya permitidos. Permitido únicamente cuando el plugin monitoriza entidades múltiples. |

No se permiten: objetos Python, `datetime` sin serializar, dicts anidados.

### 1.5 Contratos por plugin

#### Plugin: `battery`

```
Nombre en config.json : "battery"
Fichero               : agent/plugins/battery.py
Privilegios mínimos   : Administrador local (requerido por powercfg /batteryreport)
Plataforma            : Solo Windows (equipos con batería)
```

**Fuente de datos y estrategia de fallback:**

```
1. powercfg /batteryreport  →  parseo del HTML generado
        ↓ si falla (no hay batería, sin permisos, error de ejecución)
2. WMI — clase Win32_Battery
        ↓ si falla
3. Devuelve None
```

El campo `battery_source` indica qué fuente proporcionó los datos. Los campos exclusivos de `powercfg` son `None` cuando la fuente es `"wmi"`.

| Clave | Tipo | Nullable | Fuente | Descripción |
|---|---|---|---|---|
| `battery_source` | `str` | No | — | Fuente usada: `"powercfg"` o `"wmi"` |
| `battery_name` | `str` | Sí | powercfg | Nombre/modelo de la batería (ej. `"DELL V494"`) |
| `battery_manufacturer` | `str` | Sí | powercfg | Fabricante (ej. `"Samsung SDI"`) |
| `battery_serial` | `str` | Sí | powercfg | Número de serie (ej. `"6322"`) |
| `battery_chemistry` | `str` | Sí | powercfg | Química: `"LION"`, `"NIMH"`, `"NICD"`, `"MOLI"`, `"PRIM"` u otro valor en bruto |
| `battery_design_capacity_wh` | `float` | No | ambas | Capacidad original en Wh con 3 decimales (ej. `60.002`) |
| `battery_full_charge_capacity_wh` | `float` | No | ambas | Capacidad actual máxima en Wh con 3 decimales (ej. `21.683`) |
| `battery_health_percent` | `float` | No | ambas | `(full / design) * 100`, redondeado a 1 decimal |
| `battery_status` | `int` | Sí | wmi | Código WMI de estado de batería. `None` si la fuente es `"powercfg"` |

Devuelve `None` si el equipo no tiene batería o si ambas fuentes fallan.

**Invariantes:**
- `battery_source` es siempre `"powercfg"` o `"wmi"`. Nunca `None`.
- `battery_design_capacity_wh > 0.0` siempre.
- `battery_full_charge_capacity_wh >= 0.0` siempre.
- `battery_health_percent` en rango `[0.0, 150.0]`. Valores fuera de rango se registran como anomalía y se devuelve `None`.
- `battery_status` en rango `[1, 11]` cuando presente. Valor fuera de rango se registra como anomalía pero se incluye igualmente.
- Cuando `battery_source` es `"wmi"`: los campos `battery_name`, `battery_manufacturer`, `battery_serial`, `battery_chemistry` son `None`.
- Los valores de capacidad de WMI (que vienen en mWh enteros) se convierten a Wh dividiendo por 1000 antes de incluirlos en el dict, para mantener unidad uniforme.

---

#### Plugin: `software_usage`

```
Nombre en config.json : "software_usage"
Fichero               : agent/plugins/software_usage.py
Privilegios mínimos   : Administrador local (Prefetch requiere permisos elevados)
Plataforma            : Solo Windows
```

Configuración de targets: `agent/config/software_targets.json`

El valor de retorno es `list[dict]`, con una entrada por target definido en `software_targets.json`:

| Clave | Tipo | Nullable | Descripción |
|---|---|---|---|
| `name` | `str` | No | Identificador del programa, tal como figura en `software_targets.json` |
| `installed` | `bool` | No | Si el programa está instalado |
| `version` | `str` | Sí | Versión instalada. `None` si no instalado |
| `last_execution` | `str` (ISO 8601) | Sí | Último uso detectado vía Prefetch. `None` si no hay datos |
| `executions_last_30d` | `int` | No | Ejecuciones en los últimos 30 días. `0` si no instalado o sin datos |
| `executions_last_60d` | `int` | No | Ejecuciones en los últimos 60 días. `0` si no instalado o sin datos |
| `executions_last_90d` | `int` | No | Ejecuciones en los últimos 90 días. `0` si no instalado o sin datos |

**Invariantes:**
- Si `installed` es `False`: `version` es `None` y todos los conteos son `0`.
- `executions_last_30d >= 0`, `executions_last_60d >= 0`, `executions_last_90d >= 0` siempre.
- `executions_last_30d <= executions_last_60d <= executions_last_90d` siempre.
- `last_execution`, si presente, es una cadena ISO 8601 válida en hora local sin zona horaria: `"YYYY-MM-DDTHH:MM:SS"`.
- La lista tiene exactamente un dict por cada target válido en `software_targets.json`.
- `[]` es un retorno válido (sin targets configurados o fichero ausente). `None` indica fallo interno del plugin.

---

#### Plugin: `boot_time`

```
Nombre en config.json : "boot_time"
Fichero               : agent/plugins/boot_time.py
Privilegios mínimos   : Administrador local
Plataforma            : Solo Windows
```

**Fuente de datos y estrategia de fallback:**
```
Fuente principal : Event Log — Event ID 100, canal Microsoft-Windows-Diagnostics-Performance/Operational (Get-WinEvent vía subprocess PowerShell)
Fallback         : WMI — Win32_OperatingSystem.LastBootUpTime (Get-WmiObject vía subprocess PowerShell)

1. Event Log (Event ID 100) → last_boot_time + boot_duration_seconds
        ↓ si el canal no está disponible, no tiene eventos ID 100, o falla
2. WMI (Win32_OperatingSystem) → last_boot_time solo, boot_duration_seconds=None
        ↓ si falla
3. Devuelve None
```

| Clave | Tipo | Nullable | Descripción |
|---|---|---|---|
| `boot_source` | `str` | No | Fuente usada: `"event_log"` o `"wmi"` |
| `last_boot_time` | `str` (ISO 8601) | No | Timestamp del último arranque en hora local |
| `boot_duration_seconds` | `int` | Sí | Duración del arranque en segundos. `None` si la fuente es `"wmi"` |

**Invariantes:**
- `boot_source` es siempre `"event_log"` o `"wmi"`. Nunca `None`.
- `last_boot_time` es siempre una cadena ISO 8601 válida: `"YYYY-MM-DDTHH:MM:SS"`.
- `boot_duration_seconds`, si presente, es `> 0`.
- `boot_duration_seconds` es `None` cuando `boot_source` es `"wmi"` (dato no disponible vía `Win32_OperatingSystem`).
- El plugin nunca devuelve `None` completo: si el Event Log o WMI están disponibles, devuelve el dict con al menos `boot_source` y `last_boot_time`.

---

#### Plugin: `disk_usage`

```
Nombre en config.json : "disk_usage"
Fichero               : agent/plugins/disk_usage.py
Privilegios mínimos   : Usuario estándar
Plataforma            : Solo Windows
```

**Fuente de datos:**
```
Fuente única : CIM — Win32_LogicalDisk (DriveType=3) vía subprocess PowerShell

1. Get-CimInstance → lista de unidades locales con sus métricas
        ↓ si falla
2. Devuelve None
```

El valor de retorno es `list[dict]`, con una entrada por unidad lógica local detectada:

| Clave | Tipo | Nullable | Descripción |
|---|---|---|---|
| `disk_source` | `str` | No | Fuente usada: siempre `"cim"` |
| `drive_letter` | `str` | No | Letra de la unidad (ej. `"C:"`, `"D:"`) |
| `volume_name` | `str` | Sí | Nombre del volumen. `None` si no tiene etiqueta |
| `filesystem` | `str` | Sí | Sistema de archivos (ej. `"NTFS"`, `"FAT32"`). `None` si no disponible |
| `total_capacity_gb` | `float` | No | Capacidad total en GB con 3 decimales (ej. `238.472`) |
| `free_capacity_gb` | `float` | No | Capacidad libre en GB con 3 decimales (ej. `45.123`) |
| `used_capacity_gb` | `float` | No | Capacidad usada en GB con 3 decimales (ej. `193.349`) |
| `used_percent` | `float` | No | Porcentaje de uso, 1 decimal. `(used / total) * 100` (ej. `81.1`) |

Devuelve `[]` si el equipo no tiene unidades locales detectables (DriveType=3).
Devuelve `None` si la consulta CIM falla.

**Invariantes:**
- `disk_source` es siempre `"cim"`. Nunca `None`.
- `drive_letter` nunca es `None` ni cadena vacía.
- `total_capacity_gb > 0.0` siempre.
- `free_capacity_gb >= 0.0` siempre.
- `used_capacity_gb >= 0.0` siempre.
- `free_capacity_gb <= total_capacity_gb` siempre.
- `used_percent` en rango `[0.0, 100.0]`.
- Los valores de capacidad se convierten de bytes a GB dividiendo por `1024^3` con 3 decimales de precisión.
- La lista está ordenada alfabéticamente por `drive_letter`.
- `[]` es un retorno válido (sin unidades locales). `None` indica fallo interno del plugin.

---

### 1.6 Lo que un plugin NO puede hacer

- Leer o escribir `config.json`.
- Comunicarse con el backend.
- Importar módulos de `core/` (sender, collector, config).
- Modificar el estado de otros plugins.
- Escribir en disco fuera del directorio de logs del agente.
- Lanzar subprocesos sin capturar su resultado y su excepción.

---

## 2. Payload del agente

### 2.1 Descripción

El `sender.py` construye el payload consolidando la salida de todos los plugins y lo envía al endpoint `POST /api/telemetry`. Este es el único formato aceptado por el backend.

### 2.2 Estructura

```json
{
  "device_id": "string",
  "timestamp": "string (ISO 8601 UTC)",
  "agent_version": "string (semver)",
  "username": "string",
  "metrics": {
    "<plugin_name>": { ... }
  }
}
```

### 2.3 Especificación de campos raíz

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `device_id` | `string` | Sí | Hostname del equipo. Máx. 255 caracteres. Solo ASCII. |
| `timestamp` | `string` | Sí | Momento del envío en UTC. Formato: `"YYYY-MM-DDTHH:MM:SSZ"` |
| `agent_version` | `string` | Sí | Versión del agente. Formato semver: `"MAJOR.MINOR.PATCH"` |
| `username` | `string` | Sí | Usuario de sesión activo. Formato: `"usuario@dominio"` o `"usuario"`. Máx. 255 caracteres. |
| `metrics` | `object` | Sí | Diccionario con una clave por plugin ejecutado con éxito. Nunca vacío: si todos los plugins fallan, el agente no envía. |

### 2.4 Estructura de `metrics`

Cada clave en `metrics` es el nombre del plugin (coincide con el nombre en `config.json`). Su valor es el `dict` devuelto por `collect()`. Los plugins que devuelven `None` **no aparecen** en `metrics`.

```json
{
  "metrics": {
    "battery": {
      "battery_source": "powercfg",
      "battery_name": "DELL V494",
      "battery_manufacturer": "Samsung SDI",
      "battery_serial": "6322",
      "battery_chemistry": "LION",
      "battery_design_capacity_wh": 60.002,
      "battery_full_charge_capacity_wh": 21.683,
      "battery_health_percent": 36.1,
      "battery_status": null
    },
    "software_usage": [
      {
        "name": "adobe_acrobat_pro",
        "installed": true,
        "version": "24.0.0",
        "last_execution": "2026-03-20T10:30:00",
        "executions_last_30d": 3,
        "executions_last_60d": 5,
        "executions_last_90d": 8
      }
    ],
    "boot_time": {
      "boot_source": "event_log",
      "last_boot_time": "2026-03-28T07:58:00",
      "boot_duration_seconds": 42
    },
    "disk_usage": [
      {
        "disk_source": "cim",
        "drive_letter": "C:",
        "volume_name": "Sistema",
        "filesystem": "NTFS",
        "total_capacity_gb": 238.472,
        "free_capacity_gb": 45.123,
        "used_capacity_gb": 193.349,
        "used_percent": 81.1
      },
      {
        "disk_source": "cim",
        "drive_letter": "D:",
        "volume_name": "Datos",
        "filesystem": "NTFS",
        "total_capacity_gb": 465.762,
        "free_capacity_gb": 120.458,
        "used_capacity_gb": 345.304,
        "used_percent": 74.1
      }
    ]
  }
}
``` de construcción del payload

- El `timestamp` se captura en el momento en que el `sender` inicia el envío, no en el momento de la recogida de métricas.
- Si `metrics` queda vacío tras ejecutar todos los plugins, el agente **no envía** y registra el evento en el log local.
- El payload se serializa en UTF-8. Caracteres no ASCII en `username` o `device_id` se normalizan a ASCII o se sustituyen por `_`.
- El tamaño máximo del payload es **1 MB**. Si se supera (improbable en la POC), el agente registra el error y no envía.

### 2.6 Payload de ejemplo completo

```json
{
  "device_id": "HOSTNAME-001",
  "timestamp": "2026-04-08T08:15:00Z",
  "agent_version": "1.1.0",
  "username": "usuario@dominio.local",
  "metrics": {
    "battery": {
      "battery_source": "powercfg",
      "battery_name": "DELL V494",
      "battery_manufacturer": "Samsung SDI",
      "battery_serial": "6322",
      "battery_chemistry": "LION",
      "battery_design_capacity_wh": 60.002,
      "battery_full_charge_capacity_wh": 21.683,
      "battery_health_percent": 36.1,
      "battery_status": null
    },
    "software_usage": [
      {
        "name": "adobe_acrobat_pro",
        "installed": true,
        "version": "24.0.0",
        "last_execution": "2026-03-20T10:30:00",
        "executions_last_30d": 3,
        "executions_last_60d": 5,
        "executions_last_90d": 8
      }
    ],
    "boot_time": {
      "boot_source": "event_log",
      "last_boot_time": "2026-04-08T07:58:00",
      "boot_duration_seconds": 42
    },
    "disk_usage": [
      {
        "disk_source": "cim",
        "drive_letter": "C:",
        "volume_name": "Sistema",
        "filesystem": "NTFS",
        "total_capacity_gb": 238.472,
        "free_capacity_gb": 45.123,
        "used_capacity_gb": 193.349,
        "used_percent": 81.1
      },
      {
        "disk_source": "cim",
        "drive_letter": "D:",
        "volume_name": "Datos",
        "filesystem": "NTFS",
        "total_capacity_gb": 465.762,
        "free_capacity_gb": 120.458,
        "used_capacity_gb": 345.304,
        "used_percent": 74.1
      }
    ]
  }
}
```

> **Ejemplo con fallback a WMI** (agente sin privilegios para powercfg):
> ```json
> "battery": {
>   "battery_source": "wmi",
>   "battery_name": null,
>   "battery_manufacturer": null,
>   "battery_serial": null,
>   "battery_chemistry": null,
>   "battery_design_capacity_wh": 45.0,
>   "battery_full_charge_capacity_wh": 32.85,
>   "battery_health_percent": 73.0,
>   "battery_status": 2
> }
> ```

---

## 3. Modelo de datos

### 3.1 Principios

- El esquema es **aditivo**: nunca se eliminan columnas, solo se añaden o deprecan.
- Toda métrica se guarda dos veces: en la tabla tipada correspondiente (para consultas) y en `telemetry_raw.payload` (como JSONB de auditoría y para métricas futuras sin esquema propio aún).
- Las claves primarias de métricas son `BIGSERIAL`. Las claves de dispositivos son `UUID`.
- Todos los `TIMESTAMP` se almacenan en **UTC**.
- No se usan claves foráneas con `ON DELETE CASCADE`. El borrado de datos es una operación de mantenimiento controlada, nunca automática.

### 3.2 Tabla: `devices`

Registro de cada dispositivo conocido por el sistema.

```sql
CREATE TABLE devices (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    hostname        VARCHAR(255)    NOT NULL,
    api_key_hash    VARCHAR(64)     NOT NULL,       -- SHA-256 hex de la API Key
    first_seen      TIMESTAMP       NOT NULL,
    last_seen       TIMESTAMP       NOT NULL,
    active          BOOLEAN         NOT NULL DEFAULT TRUE,
    agent_version   VARCHAR(20)     NULL            -- Última versión reportada
);

CREATE UNIQUE INDEX idx_devices_hostname ON devices (hostname);
CREATE INDEX idx_devices_active ON devices (active);
```

**Restricciones:**

| Campo | Restricción |
|---|---|
| `hostname` | Único. Máx. 255 caracteres. |
| `api_key_hash` | SHA-256 en hex (64 caracteres). No se almacena la key en claro. |
| `first_seen` | Nunca posterior a `last_seen`. |
| `agent_version` | Formato semver o `NULL` si no se ha reportado aún. |

---

### 3.3 Tabla: `telemetry_raw`

Almacén de auditoría. Guarda el payload completo de cada envío.

```sql
CREATE TABLE telemetry_raw (
    id          BIGSERIAL       PRIMARY KEY,
    device_id   UUID            NOT NULL REFERENCES devices(id),
    received_at TIMESTAMP       NOT NULL DEFAULT NOW(),
    payload     JSONB           NOT NULL
);

CREATE INDEX idx_telemetry_raw_device_time ON telemetry_raw (device_id, received_at DESC);
```

**Restricciones:**

| Campo | Restricción |
|---|---|
| `received_at` | Timestamp de recepción en el backend (no el del agente). |
| `payload` | Debe ser un objeto JSON válido con al menos las claves `device_id`, `timestamp`, `metrics`. Validación a nivel de aplicación, no de BD. |

**Retención:** 12 meses. Candidato a particionado por mes con `pg_partman` en Fase 3.

---

### 3.4 Tabla: `battery_metrics`

```sql
CREATE TABLE battery_metrics (
    id                          BIGSERIAL       PRIMARY KEY,
    device_id                   UUID            NOT NULL REFERENCES devices(id),
    recorded_at                 TIMESTAMP       NOT NULL,       -- timestamp del agente (UTC)
    received_at                 TIMESTAMP       NOT NULL DEFAULT NOW(),
    data_source                 VARCHAR(10)     NOT NULL,       -- 'powercfg' | 'wmi'
    battery_name                VARCHAR(100)    NULL,           -- solo powercfg
    battery_manufacturer        VARCHAR(100)    NULL,           -- solo powercfg
    battery_serial              VARCHAR(50)     NULL,           -- solo powercfg
    battery_chemistry           VARCHAR(10)     NULL,           -- solo powercfg
    design_capacity_wh          NUMERIC(10, 3)  NOT NULL CHECK (design_capacity_wh > 0),
    full_charge_capacity_wh     NUMERIC(10, 3)  NOT NULL CHECK (full_charge_capacity_wh >= 0),
    health_percent              NUMERIC(5, 2)   NOT NULL CHECK (health_percent BETWEEN 0 AND 150),
    battery_status              SMALLINT        NULL            -- null cuando fuente es powercfg
);

CREATE INDEX idx_battery_device_time ON battery_metrics (device_id, recorded_at DESC);
CREATE INDEX idx_battery_health ON battery_metrics (device_id, health_percent);
```

**Restricciones:**

| Campo | Restricción |
|---|---|
| `data_source` | Solo `'powercfg'` o `'wmi'`. Validado en aplicación antes de insertar. |
| `battery_name`, `battery_manufacturer`, `battery_serial`, `battery_chemistry` | `NULL` cuando `data_source = 'wmi'`. Presentes cuando `data_source = 'powercfg'` (pueden ser `NULL` si el campo venía vacío en el HTML). |
| `design_capacity_wh` | Estrictamente mayor que 0. Tres decimales. |
| `full_charge_capacity_wh` | Mayor o igual a 0. Puede ser 0 en baterías muy degradadas. Tres decimales. |
| `health_percent` | Entre 0.00 y 150.00. Dos decimales. |
| `battery_status` | `NULL` cuando `data_source = 'powercfg'`. Sin restricción de rango en BD cuando presente (se valida en aplicación). |

---

### 3.5 Tabla: `software_usage`

```sql
CREATE TABLE software_usage (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    software_name       VARCHAR(100)    NOT NULL,
    installed           BOOLEAN         NOT NULL,
    version             VARCHAR(50)     NULL,
    last_execution      TIMESTAMP       NULL,
    executions_30d      INTEGER         NOT NULL DEFAULT 0 CHECK (executions_30d >= 0),
    executions_60d      INTEGER         NOT NULL DEFAULT 0 CHECK (executions_60d >= 0),
    executions_90d      INTEGER         NOT NULL DEFAULT 0 CHECK (executions_90d >= 0)
);

CREATE INDEX idx_software_device_name_time ON software_usage (device_id, software_name, recorded_at DESC);
CREATE INDEX idx_software_name_installed   ON software_usage (software_name, installed);
```

**Restricciones:**

| Campo | Restricción |
|---|---|
| `software_name` | Valor controlado desde el agente. En la POC: `"adobe_acrobat_pro"`. Máx. 100 caracteres. |
| `version` | `NULL` si `installed` es `FALSE`. |
| `last_execution` | `NULL` si no hay datos. Almacenado en UTC (el agente envía hora local; el backend convierte). |
| `executions_30d` | `>= 0`. `0` si no instalado o sin datos. |
| `executions_60d` | `>= 0`. `0` si no instalado o sin datos. |
| `executions_90d` | `>= 0`. `0` si no instalado o sin datos. Invariante de orden validado en aplicación: `30d <= 60d <= 90d`.|

---

### 3.6 Tabla: `boot_metrics`

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

**Restricciones:**

| Campo | Restricción |
|---|---|
| `data_source` | Solo `'event_log'` o `'wmi'`. Validado en aplicación antes de insertar. Valor proviene directamente del campo `boot_source` del payload del agente. |
| `last_boot_time` | Almacenado en UTC. El backend convierte desde la hora local del agente. |
| `boot_duration_seconds` | `NULL` si `data_source = 'wmi'` o si el dato no estaba disponible. Si presente, estrictamente mayor que 0.|


---

### 3.7 Tabla: `disk_usage`

```sql
CREATE TABLE disk_usage (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    data_source         VARCHAR(10)     NOT NULL,   -- 'cim'
    drive_letter        VARCHAR(10)     NOT NULL,
    volume_name         VARCHAR(100)    NULL,
    filesystem          VARCHAR(20)     NULL,
    total_capacity_gb   NUMERIC(10, 3)  NOT NULL CHECK (total_capacity_gb > 0),
    free_capacity_gb    NUMERIC(10, 3)  NOT NULL CHECK (free_capacity_gb >= 0),
    used_capacity_gb    NUMERIC(10, 3)  NOT NULL CHECK (used_capacity_gb >= 0),
    used_percent        NUMERIC(5, 2)   NOT NULL CHECK (used_percent BETWEEN 0 AND 100)
);

CREATE INDEX idx_disk_device_time ON disk_usage (device_id, recorded_at DESC);
CREATE INDEX idx_disk_device_drive ON disk_usage (device_id, drive_letter, recorded_at DESC);
```

**Restricciones:**

| Campo | Restricción |
|---|---|
| `data_source` | Solo `'cim'`. Validado en aplicación antes de insertar. Valor proviene directamente del campo `disk_source` del payload del agente. |
| `drive_letter` | Nunca `NULL` ni cadena vacía. Máx. 10 caracteres para cubrir formatos futuros. |
| `volume_name` | `NULL` si el volumen no tiene etiqueta. Máx. 100 caracteres. |
| `filesystem` | `NULL` si no disponible. Típicamente `'NTFS'`, `'FAT32'`, `'exFAT'`. Máx. 20 caracteres. |
| `total_capacity_gb` | Estrictamente mayor que 0. Tres decimales. |
| `free_capacity_gb` | Mayor o igual a 0. Tres decimales. |
| `used_capacity_gb` | Mayor o igual a 0. Tres decimales. `used_capacity_gb = total_capacity_gb - free_capacity_gb` siempre. |
| `used_percent` | Entre 0.00 y 100.00. Dos decimales en BD aunque el plugin reporta 1 decimal. |

**Nota sobre múltiples registros por envío:** A diferencia de las otras tablas de métricas que insertan un registro por dispositivo y envío, `disk_usage` inserta **un registro por unidad detectada**. Un equipo con 3 discos locales generará 3 filas en cada envío. El índice `idx_disk_device_drive` optimiza las queries que filtran por dispositivo y letra de unidad específica.

---

### 3.8 Tabla: `agent_versions` *(Fase 2 — auto-update)*

Manifiesto de versiones servido por el endpoint `GET /api/agent/version`.

```sql
CREATE TABLE agent_versions (
    id              SERIAL          PRIMARY KEY,
    version         VARCHAR(20)     NOT NULL,
    artifact_type   VARCHAR(20)     NOT NULL,   -- 'core' | 'plugin'
    artifact_name   VARCHAR(100)    NOT NULL,   -- 'agent' | nombre del plugin
    download_url    VARCHAR(500)    NOT NULL,
    checksum_sha256 VARCHAR(64)     NOT NULL,
    published_at    TIMESTAMP       NOT NULL DEFAULT NOW(),
    active          BOOLEAN         NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX idx_agent_versions_active ON agent_versions (artifact_type, artifact_name, active)
    WHERE active = TRUE;
```

**Restricciones:**

| Campo | Restricción |
|---|---|
| `artifact_type` | Solo valores `'core'` o `'plugin'`. Validado en aplicación. |
| `checksum_sha256` | 64 caracteres hex (SHA-256). |
| Solo una versión activa por artefacto | Garantizado por el índice parcial único. |

---

## 4. API Backend

### 4.1 Convenciones globales

- **Base URL:** `https://ehukene.dominio.local/api`
- **Protocolo:** HTTPS obligatorio. HTTP rechazado con redirect 301.
- **Formato:** `Content-Type: application/json` en todas las peticiones y respuestas.
- **Autenticación:** Cabecera `X-API-Key: <key>` en todos los endpoints excepto `GET /api/agent/version`.
- **Encoding:** UTF-8.
- **Versión de API:** Sin versionado en la POC. Se introducirá prefijo `/v1/` en Fase 2 si hay cambios breaking.

### 4.2 Códigos de error estándar

Todos los errores siguen esta estructura:

```json
{
  "error": "string (código de error)",
  "detail": "string (descripción legible)"
}
```

| Código HTTP | `error` | Cuándo ocurre |
|---|---|---|
| `400` | `INVALID_PAYLOAD` | El JSON no puede parsearse o falta un campo requerido |
| `401` | `UNAUTHORIZED` | API Key ausente, inválida o revocada |
| `403` | `FORBIDDEN` | La API Key no corresponde al `device_id` del payload |
| `404` | `NOT_FOUND` | El recurso solicitado no existe |
| `409` | `DUPLICATE_SUBMISSION` | Ya existe un registro para este `device_id` en el día actual (solo `POST /api/telemetry`) |
| `413` | `PAYLOAD_TOO_LARGE` | El payload supera 1 MB |
| `422` | `VALIDATION_ERROR` | El payload es JSON válido pero no cumple el esquema |
| `429` | `RATE_LIMIT_EXCEEDED` | Se superó el límite de peticiones |
| `500` | `INTERNAL_ERROR` | Error interno del servidor (no exponer detalle al cliente) |

---

### 4.3 Endpoint: `POST /api/telemetry`

Recepción de métricas del agente.

**Autenticación:** Requerida (`X-API-Key`)

**Request body:** Ver sección 2 — Payload del agente.

**Validaciones (en orden de aplicación):**

1. La API Key existe y está activa → `401` si no.
2. El `device_id` del payload coincide con el dispositivo asociado a la API Key → `403` si no.
3. El payload es JSON válido y contiene todos los campos requeridos → `400` si no.
4. El payload cumple el esquema (tipos, rangos, formatos) → `422` si no.
5. El tamaño del payload es ≤ 1 MB → `413` si no.
6. No existe ya un registro para este `device_id` en el día de `timestamp` → `409` si existe (el agente debe respetar el control de duplicados, pero el backend es la fuente de verdad).

**Response 200 OK:**

```json
{
  "status": "accepted",
  "device_id": "HOSTNAME-001",
  "received_at": "2026-03-28T08:15:02Z"
}
```

**Efectos:**

- Se actualiza `devices.last_seen` y `devices.agent_version`.
- Se inserta en `telemetry_raw`.
- Se insertan registros en las tablas tipadas correspondientes a los plugins presentes en `metrics`.

---

### 4.4 Endpoint: `POST /api/devices/register`

Registro inicial de un dispositivo nuevo.

**Autenticación:** No requerida en POC (se revisará en Fase 2). En producción: proteger con IP whitelist o token de bootstrap.

**Request body:**

```json
{
  "hostname": "string",
  "requested_by": "string (opcional, usuario que registra)"
}
```

| Campo | Tipo | Requerido | Validación |
|---|---|---|---|
| `hostname` | `string` | Sí | Máx. 255 caracteres. Solo ASCII. |
| `requested_by` | `string` | No | Máx. 255 caracteres. Solo informativo. |

**Validaciones:**

1. `hostname` no vacío y cumple formato → `422` si no.
2. `hostname` no existe ya en `devices` → `409` si existe.

**Response 201 Created:**

```json
{
  "device_id": "uuid",
  "hostname": "HOSTNAME-001",
  "api_key": "string (solo se devuelve una vez, en claro)",
  "created_at": "2026-03-28T08:00:00Z"
}
```

> La `api_key` se devuelve únicamente en esta respuesta. El backend almacena solo su hash. Si se pierde, debe generarse una nueva.

---

### 4.5 Endpoint: `GET /api/devices`

Listado de dispositivos registrados.

**Autenticación:** Requerida (`X-API-Key`) — Solo keys de administración (distinto perfil de las keys de dispositivo, a definir en Fase 2). En POC: cualquier key válida.

**Query parameters:**

| Parámetro | Tipo | Descripción | Defecto |
|---|---|---|---|
| `active` | `bool` | Filtrar por estado activo | `true` |
| `limit` | `int` | Máximo de resultados | `100` |
| `offset` | `int` | Desplazamiento para paginación | `0` |

**Response 200 OK:**

```json
{
  "total": 7000,
  "limit": 100,
  "offset": 0,
  "devices": [
    {
      "device_id": "uuid",
      "hostname": "HOSTNAME-001",
      "first_seen": "2026-01-10T09:00:00Z",
      "last_seen": "2026-03-28T08:15:00Z",
      "active": true,
      "agent_version": "1.1.0"
    }
  ]
}
```

---

### 4.6 Endpoint: `GET /api/devices/{device_id}`

Detalle de un dispositivo.

**Autenticación:** Requerida.

**Path parameter:** `device_id` — UUID del dispositivo.

**Response 200 OK:**

```json
{
  "device_id": "uuid",
  "hostname": "HOSTNAME-001",
  "first_seen": "2026-01-10T09:00:00Z",
  "last_seen": "2026-03-28T08:15:00Z",
  "active": true,
  "agent_version": "1.1.0",
  "last_metrics": {
    "battery": {
      "health_percent": 73.0,
      "battery_status": 2,
      "recorded_at": "2026-03-28T08:15:00Z"
    },
    "software_usage": {
      "acrobat_installed": true,
      "acrobat_version": "24.0.0",
      "acrobat_last_execution": "2026-03-20T10:30:00Z",
      "acrobat_executions_last_30d": 3,
      "recorded_at": "2026-03-28T08:15:00Z"
    },
    "boot_time": {
      "last_boot_time": "2026-03-28T07:58:00Z",
      "boot_duration_seconds": 42,
      "recorded_at": "2026-03-28T08:15:00Z"
    }
  }
}
```

**Response 404:** Si el `device_id` no existe.

---

### 4.7 Endpoint: `GET /api/devices/{device_id}/history`

Histórico de métricas de un dispositivo.

**Autenticación:** Requerida.

**Query parameters:**

| Parámetro | Tipo | Descripción | Defecto |
|---|---|---|---|
| `metric` | `string` | Filtrar por tipo: `battery`, `software_usage`, `boot_time`, `disk_usage` | Todos |
| `from` | `string` (ISO 8601) | Fecha inicio | Hace 30 días |
| `to` | `string` (ISO 8601) | Fecha fin | Ahora |
| `limit` | `int` | Máximo de resultados por métrica | `90` |

**Response 200 OK:**

```json
{
  "device_id": "uuid",
  "from": "2026-02-26T00:00:00Z",
  "to": "2026-04-08T23:59:59Z",
  "history": {
    "battery": [
      {
        "recorded_at": "2026-04-08T08:15:00Z",
        "health_percent": 73.0,
        "battery_status": 2
      }
    ],
    "boot_time": [
      {
        "recorded_at": "2026-04-08T08:15:00Z",
        "last_boot_time": "2026-04-08T07:58:00Z",
        "boot_duration_seconds": 42
      }
    ],
    "disk_usage": [
      {
        "recorded_at": "2026-04-08T08:15:00Z",
        "drive_letter": "C:",
        "total_capacity_gb": 238.472,
        "free_capacity_gb": 45.123,
        "used_percent": 81.1
      },
      {
        "recorded_at": "2026-04-08T08:15:00Z",
        "drive_letter": "D:",
        "total_capacity_gb": 465.762,
        "free_capacity_gb": 120.458,
        "used_percent": 74.1
      }
    ]
  }
}
```

---

### 4.8 Endpoint: `GET /api/agent/version` *(Fase 2)*

Manifiesto de versiones para auto-actualización.

**Autenticación:** No requerida. Accesible vía HTTPS público.

**Response 200 OK:**

```json
{
  "core_version": "1.2.0",
  "core_download_url": "https://ehukene.dominio.local/dist/agent-1.2.0.exe",
  "core_checksum_sha256": "a3f1...",
  "plugins": {
    "battery": {
      "version": "1.1.0",
      "url": "https://ehukene.dominio.local/dist/plugins/battery-1.1.0.py",
      "checksum_sha256": "c8d2..."
    },
    "software_usage": {
      "version": "1.0.3",
      "url": "https://ehukene.dominio.local/dist/plugins/software_usage-1.0.3.py",
      "checksum_sha256": "e91a..."
    },
    "boot_time": {
      "version": "1.0.0",
      "url": "https://ehukene.dominio.local/dist/plugins/boot_time-1.0.0.py",
      "checksum_sha256": "b47f..."
    }
  }
}
```

**Restricciones:**

- Las URLs de descarga deben ser HTTPS.
- Los checksums son SHA-256 en hex (64 caracteres).
- Solo se incluyen plugins con `active = TRUE` en `agent_versions`.

---

### 4.9 Lo que la API NO hace

- No devuelve la API Key en claro después del registro inicial.
- No permite que un dispositivo consulte métricas de otro dispositivo con su propia API Key.
- No expone detalles internos de errores en respuestas `500`.
- No acepta payloads con `timestamp` futuro (más de 5 minutos sobre el tiempo del servidor → `422`).
- No acepta payloads con `timestamp` anterior a 24 horas → `422` (el agente no debe enviar datos de días anteriores).

---

## Apéndice A — Glosario

| Término | Definición |
|---|---|
| `device_id` | En el agente: hostname del equipo. En la BD: UUID de la tabla `devices`. El backend resuelve el hostname al UUID en cada petición. |
| `recorded_at` | Timestamp del momento de recogida de la métrica (lado agente), almacenado en UTC. |
| `received_at` | Timestamp de recepción en el backend. Siempre posterior a `recorded_at`. |
| Plugin | Módulo Python en `agent/plugins/` que implementa `collect() -> dict | None`. |
| Manifiesto | Respuesta de `GET /api/agent/version` con las versiones actuales del core y los plugins. |

---

## Apéndice B — Campos añadidos respecto al documento técnico v1.0

Los siguientes campos son nuevos respecto al documento técnico original y han sido incorporados en este contrato por necesidad de diseño:

| Campo | Tabla / Payload | Motivo |
|---|---|---|
| `agent_version` | Payload raíz | Necesario para detectar versiones desactualizadas en el backend |
| `received_at` | Todas las tablas de métricas | Distinguir momento de recogida vs. recepción |
| `agent_version` | Tabla `devices` | Seguimiento de versiones desplegadas en el parque |
| `installed` | Tabla `software_usage` | Permite filtrar equipos con software instalado vs. usándolo |
| `software_name` | Tabla `software_usage` | Prepara la tabla para más de un software sin cambio de esquema |

## Apéndice C — Cambios respecto a v1.0 de este documento (v1.1)

| Cambio | Sección | Motivo |
|---|---|---|
| Fuente de datos del plugin `battery` cambiada a `powercfg /batteryreport` con fallback a WMI | 1.5 | Mayor fiabilidad; WMI no soportado por todos los fabricantes |
| Privilegios del plugin `battery` elevados a administrador local | 1.5 | `powercfg /batteryreport` requiere permisos elevados |
| Campos nuevos: `battery_source`, `battery_name`, `battery_manufacturer`, `battery_serial`, `battery_chemistry` | 1.5, 2.4, 2.6 | Datos de identificación de batería solo disponibles vía powercfg |
| Unidad de capacidades cambiada de `mWh (int)` a `Wh (float, 3 decimales)` | 1.5, 2.4, 2.6 | powercfg reporta en Wh con decimales; se unifica la unidad para ambas fuentes |
| Renombrado `battery_design_capacity` → `battery_design_capacity_wh` | 1.5, 2.x | Unidad explícita en el nombre de campo |
| Renombrado `battery_full_charge_capacity` → `battery_full_charge_capacity_wh` | 1.5, 2.x | Unidad explícita en el nombre de campo |
| Tabla `battery_metrics` rediseñada: columnas nuevas, tipos actualizados | 3.4 | Refleja los nuevos campos y la unidad Wh |
| `battery_status` pasa a `NULLABLE` en BD | 3.4 | Es `null` cuando la fuente es powercfg |
| `CYCLE COUNT` descartado del contrato | — | Dato no fiable: la mayoría de fabricantes no lo exponen (`-`) |
| `list[dict]` añadido como tipo permitido| 1.4 | `software_usage` monitoriza entidades múltiples; estructura plana no es viable |
| Contrato de `software_usage` reescrito: retorno cambia de dict a `list[dict]` con una entrada por target | 1.5 | Plugin configurable para múltiples programas |
|Campos `acrobat_*` eliminados; sustituidos por campos genéricos `name`, `installed`, `version`, `last_execution`, `executions_last_*` | 1.5 | Generalización del contrato |
| Privilegios de `software_usage` elevados a administrador local | 1.5 | Prefetch requiere permisos elevados|
| `executions_last_30d` → tres campos: `executions_last_30d`, `executions_last_60d`, `executions_last_90d` | 1.5, 2, 3.5 | Mayor granularidad temporal para análisis de uso|
|Tabla `software_usage`: añadidas columnas `executions_60d` y `executions_90d` | 3.5 | Refleja los tres periodos del contrato|
| Fichero de configuración `agent/config/software_targets.json` introducido | 1.5 | Lista de programas a monitorizar configurable sin redespliegue del ejecutable|
| Privilegios de `boot_time` elevados a administrador local | 1.5 | `Get-WinEvent` sobre el canal Diagnostics-Performance requiere permisos elevados |
| Fuente primaria de `boot_time` definida: Event ID 100 con fallback WMI | 1.5 |El contrato v1.2 no especificaba las fuentes; la implementación las hace explícitas |
| Invariantes de `boot_time` ampliados: mención del Event Log y `boot_duration_seconds`=`None` en fallback WMI | 1.5 | Refleja el comportamiento real de las dos fuentes |
| Columna `data_source` añadida a `boot_metrics` | 3.6 | Trazabilidad de la fuente de cada registro, en línea con `battery_metrics`|
## Apéndice D — Cambios respecto a v1.3 (v1.4)

| Cambio | Sección | Motivo |
|---|---|---|
| Campo `boot_source` añadido al contrato del plugin `boot_time` | 1.5 | Elimina la inferencia implícita `boot_duration_seconds=None → fuente=wmi` en el backend; simetría con `battery_source` |
| Invariante `boot_duration_seconds=None cuando boot_source='wmi'` reformulado como dependencia explícita de `boot_source` | 1.5 | El campo que manda es `boot_source`; la duración es consecuencia, no el indicador |
| Restricción `data_source` en tabla `boot_metrics` actualizada: el valor proviene de `boot_source` del payload, no se infiere | 3.6 | Refleja el flujo de datos real tras el cambio en el plugin y el schema Pydantic |

## Apéndice E — Cambios respecto a v1.4 (v1.5)

| Cambio | Sección | Motivo |
|---|---|---|
| Plugin `disk_usage` añadido al contrato del sistema | 1.5 | Nuevo plugin para monitorizar ocupación de disco en equipos Windows |
| Tabla `disk_usage` añadida al modelo de datos | 3.7 | Almacenamiento de histórico de ocupación de disco por unidad |
| Endpoint `/api/devices/{device_id}/history` actualizado para incluir `disk_usage` | 4.7 | Soporte para consulta de histórico de disco |
| Ejemplos de payload actualizados con `disk_usage` | 2.4, 2.6 | Reflejar el nuevo plugin en la documentación |
| Numeración de tablas ajustada: `agent_versions` pasa de §3.7 a §3.8 | 3 | Inserción de `disk_usage` desplaza el resto |
