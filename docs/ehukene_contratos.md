# EHUkene — Contratos del Sistema
## Documento de referencia de diseño

**Versión:** 1.6  
**Estado:** Diseño  
**Fecha:** 2026-04-16  
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

No se permiten: objetos Python, `datetime` sin serializar, dicts anidados (excepto en `health_monitor` que tiene estructura compleja).

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

#### Plugin: `health_monitor`

```
Nombre en config.json : "health_monitor"
Fichero               : agent/plugins/health_monitor.py
Privilegios mínimos   : Usuario estándar (algunas métricas requieren admin local)
Plataforma            : Solo Windows
Configuración         : agent/config/health_monitor_config.json
```

**Descripción:** Plugin de monitorización integral que recopila 8 métricas de salud del sistema. Diseñado para funcionar en entornos corporativos restrictivos con principio de "fiabilidad sobre precisión".

**Estructura de retorno:**

El plugin devuelve un `dict` con la siguiente estructura (nunca `None` - si hay error, las métricas individuales reportan `status: "error"`):

```python
{
    "plugin_version": str,              # Versión del plugin (semver)
    "host": str,                        # Hostname del equipo
    "domain": str,                      # Dominio (o "WORKGROUP")
    "timestamp": str,                   # ISO 8601 UTC del momento de ejecución
    "execution": {
        "duration_ms": int,             # Duración total de ejecución
        "metrics_attempted": int,       # Siempre 8
        "metrics_successful": int       # Cuántas completaron sin error
    },
    "metrics": {
        "cpu": {...},                   # Ver detalle abajo
        "memory": {...},
        "disk": {...},
        "events": {...},
        "domain": {...},
        "uptime": {...},
        "boot_time": {...},
        "services": [...]               # Lista de servicios
    }
}
```

### Métrica: `cpu`

**Fuente:** `Get-CimInstance Win32_Processor | Select-Object LoadPercentage`

| Clave | Tipo | Nullable | Descripción |
|---|---|---|---|
| `load_percentage` | `int` | Sí | Porcentaje de carga CPU (0-100). `None` si hay error |
| `status` | `str` | No | `"ok"`, `"warning"`, `"critical"`, `"error"` |
| `error_msg` | `str` | Sí | Mensaje de error si `status == "error"` |

**Invariantes:**
- `load_percentage` en rango `[0, 100]` cuando presente.
- `status` es uno de: `"ok"`, `"warning"`, `"critical"`, `"error"`.
- Si `status == "error"`: `load_percentage` es `None` y `error_msg` contiene el detalle.
- Si `status != "error"`: `load_percentage` no es `None` y `error_msg` es `None`.

### Métrica: `memory`

**Fuente:** `Get-CimInstance Win32_OperatingSystem`

| Clave | Tipo | Nullable | Descripción |
|---|---|---|---|
| `total_kb` | `int` | Sí | Memoria total en KB. `None` si hay error |
| `free_kb` | `int` | Sí | Memoria libre en KB. `None` si hay error |
| `usage_pct` | `float` | Sí | Porcentaje de uso con 2 decimales. `None` si hay error |
| `status` | `str` | No | `"ok"`, `"warning"`, `"critical"`, `"error"` |
| `error_msg` | `str` | Sí | Mensaje de error si `status == "error"` |

**Invariantes:**
- `total_kb > 0` cuando presente.
- `free_kb >= 0` cuando presente.
- `free_kb <= total_kb` cuando ambos presentes.
- `usage_pct` en rango `[0.0, 100.0]` cuando presente, con 2 decimales.
- Cálculo: `usage_pct = ((total_kb - free_kb) / total_kb) * 100`.

### Métrica: `disk`

**Fuente:** `Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$env:SystemDrive'"`

**Nota:** Solo monitoriza el disco del sistema (típicamente C:).

| Clave | Tipo | Nullable | Descripción |
|---|---|---|---|
| `drive` | `str` | Sí | Letra de unidad (ej. `"C:"`). `None` si hay error |
| `total_gb` | `float` | Sí | Capacidad total en GB con 2 decimales. `None` si hay error |
| `free_gb` | `float` | Sí | Espacio libre en GB con 2 decimales. `None` si hay error |
| `free_pct` | `float` | Sí | Porcentaje libre con 2 decimales. `None` si hay error |
| `status` | `str` | No | `"ok"`, `"warning"`, `"critical"`, `"error"` |
| `error_msg` | `str` | Sí | Mensaje de error si `status == "error"` |

**Invariantes:**
- `total_gb > 0.0` cuando presente.
- `free_gb >= 0.0` cuando presente.
- `free_gb <= total_gb` cuando ambos presentes.
- `free_pct` en rango `[0.0, 100.0]` cuando presente.
- Cálculo: `free_pct = (free_gb / total_gb) * 100`.

### Métrica: `events`

**Fuente:** `Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2}`

**Descripción:** Eventos críticos y de error del Event Log del sistema (últimas 24h). Triple filtrado: por provider+eventID, por combinaciones específicas, y eventos sin mensaje.

| Clave | Tipo | Nullable | Descripción |
|---|---|---|---|
| `critical_count` | `int` | No | Número de eventos de nivel Critical |
| `error_count` | `int` | No | Número de eventos de nivel Error |
| `filtered_count` | `int` | No | Número de eventos descartados (ruido) |
| `top_sources` | `list[dict]` | No | Top 5 providers por frecuencia (puede estar vacío) |
| `sample_events` | `list[dict]` | No | Hasta 5 eventos de muestra (puede estar vacío) |
| `status` | `str` | No | `"ok"`, `"warning"`, `"critical"`, `"error"` |
| `error_msg` | `str` | Sí | Mensaje de error si `status == "error"` |

**Estructura de `top_sources` (cada item):**
- `provider` (str): Nombre del provider
- `count` (int): Número de eventos

**Estructura de `sample_events` (cada item):**
- `event_id` (int): ID del evento
- `provider` (str): Provider/Source
- `level` (str): `"Critical"` o `"Error"`
- `time_created` (str, ISO 8601 UTC): Timestamp del evento

**Invariantes:**
- `critical_count >= 0`, `error_count >= 0`, `filtered_count >= 0`.
- `top_sources` es una lista (puede estar vacía si no hay eventos).
- `sample_events` es una lista (puede estar vacía si no hay eventos).
- Máximo 5 items en `top_sources`.
- Máximo 5 items en `sample_events`.

### Métrica: `domain`

**Fuente:** `Test-ComputerSecureChannel`

| Clave | Tipo | Nullable | Descripción |
|---|---|---|---|
| `secure_channel` | `bool` | No | `true` si el canal seguro está activo |
| `status` | `str` | No | `"ok"`, `"error"`, `"not_in_domain"` |
| `error_msg` | `str` | Sí | Mensaje de error si `status == "error"` |

**Invariantes:**
- `status` es uno de: `"ok"`, `"error"`, `"not_in_domain"`.
- Si `status == "ok"`: `secure_channel` es `true`.
- Si `status == "not_in_domain"`: `secure_channel` es `false`.

### Métrica: `uptime`

**Fuente:** `Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime`

| Clave | Tipo | Nullable | Descripción |
|---|---|---|---|
| `last_boot` | `str` (ISO 8601 UTC) | Sí | Timestamp del último arranque. `None` si hay error |
| `days` | `float` | Sí | Días desde el arranque con 1 decimal. `None` si hay error |
| `status` | `str` | No | `"ok"`, `"warning"`, `"critical"`, `"error"` |
| `error_msg` | `str` | Sí | Mensaje de error si `status == "error"` |

**Invariantes:**
- `last_boot` es ISO 8601 UTC válido cuando presente: `"YYYY-MM-DDTHH:MM:SSZ"`.
- `days >= 0.0` cuando presente, con 1 decimal.
- Cálculo: `days = (datetime.utcnow() - last_boot).total_seconds() / 86400`.

### Métrica: `boot_time`

**Fuente:** Estrategia dual con fallback
1. Event Log — Event ID 100 (Microsoft-Windows-Diagnostics-Performance/Operational)
2. WMI — Win32_OperatingSystem.LastBootUpTime

| Clave | Tipo | Nullable | Descripción |
|---|---|---|---|
| `last_boot_time` | `str` (ISO 8601 local) | Sí | Timestamp del arranque. `None` si hay error |
| `boot_duration_seconds` | `int` | Sí | Duración del boot. `None` si WMI o error |
| `source` | `str` | Sí | `"event_log"` o `"wmi"`. `None` si hay error |
| `status` | `str` | No | `"optimal"`, `"ok"`, `"degraded"`, `"critical"`, `"unknown"`, `"error"` |
| `error_msg` | `str` | Sí | Mensaje de error si `status == "error"` |

**Invariantes:**
- `last_boot_time` es ISO 8601 local válido cuando presente: `"YYYY-MM-DDTHH:MM:SS"` (sin Z).
- `boot_duration_seconds > 0` cuando presente.
- `source` es `"event_log"` o `"wmi"` cuando presente.
- Si `source == "wmi"`: `boot_duration_seconds` es `None` y `status` es `"unknown"`.
- Si `source == "event_log"`: `boot_duration_seconds` no es `None`.
- `status` es uno de: `"optimal"`, `"ok"`, `"degraded"`, `"critical"`, `"unknown"`, `"error"`.

### Métrica: `services`

**Fuente:** `Get-Service` con filtrado por tiers configurables

**Descripción:** Lista de servicios críticos organizados en 3 niveles (tiers). El valor de retorno es `list[dict]`.

**Estructura de cada servicio:**

| Clave | Tipo | Nullable | Descripción |
|---|---|---|---|
| `name` | `str` | No | Nombre interno del servicio |
| `display_name` | `str` | Sí | Nombre visible. `None` si no disponible |
| `state` | `str` | No | `"Running"`, `"Stopped"`, `"Paused"`, etc. |
| `startup_type` | `str` | Sí | `"Automatic"`, `"Manual"`, `"Disabled"`. `None` si no disponible |
| `tier` | `int` | No | Nivel de criticidad (1-3) |
| `status` | `str` | No | `"ok"`, `"warning"`, `"critical"`, `"not_available"`, `"error"` |

**Invariantes:**
- `tier` en rango `[1, 3]`.
- `status` es uno de: `"ok"`, `"warning"`, `"critical"`, `"not_available"`, `"error"`.
- `state` no es `None` (valor mínimo: `"Unknown"`).
- Regla especial: Si `state == "Stopped"` y `startup_type == "Disabled"`: `status = "ok"`.
- La lista contiene todos los servicios configurados en los 3 tiers.

**Configuración de tiers (por defecto):**
- **Tier 1 (Crítico):** SepMasterService, EventLog, RpcSs, LanmanWorkstation
- **Tier 2 (Importante):** WinDefend, wuauserv, Spooler, Dhcp
- **Tier 3 (Monitoreo):** LanmanServer, W32Time, Dnscache, Netlogon

### Invariantes Globales del Plugin

- El plugin siempre devuelve un `dict` (nunca `None`).
- El bloque `metrics` contiene exactamente 8 claves: `cpu`, `memory`, `disk`, `events`, `domain`, `uptime`, `boot_time`, `services`.
- `execution.metrics_attempted` es siempre `8`.
- `execution.metrics_successful` en rango `[0, 8]`.
- `execution.duration_ms > 0`.
- `plugin_version` sigue formato semver: `"MAJOR.MINOR.PATCH"`.
- `timestamp` es ISO 8601 UTC válido: `"YYYY-MM-DDTHH:MM:SSZ"`.

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
    ],
    "health_monitor": {
      "plugin_version": "1.1.0",
      "host": "HOSTNAME-001",
      "domain": "CORPNET",
      "timestamp": "2026-04-16T14:30:15Z",
      "execution": {
        "duration_ms": 2847,
        "metrics_attempted": 8,
        "metrics_successful": 8
      },
      "metrics": {
        "cpu": {
          "load_percentage": 45,
          "status": "ok",
          "error_msg": null
        },
        "memory": {
          "total_kb": 8388608,
          "free_kb": 2097152,
          "usage_pct": 75.00,
          "status": "ok",
          "error_msg": null
        },
        "disk": {
          "drive": "C:",
          "total_gb": 238.47,
          "free_gb": 15.62,
          "free_pct": 6.55,
          "status": "critical",
          "error_msg": null
        },
        "events": {
          "critical_count": 0,
          "error_count": 4,
          "filtered_count": 25,
          "top_sources": [
            {"provider": "Microsoft-Windows-WindowsUpdateClient", "count": 2}
          ],
          "sample_events": [
            {
              "event_id": 20,
              "provider": "Microsoft-Windows-WindowsUpdateClient",
              "level": "Error",
              "time_created": "2026-04-16T10:23:45Z"
            }
          ],
          "status": "ok",
          "error_msg": null
        },
        "domain": {
          "secure_channel": true,
          "status": "ok",
          "error_msg": null
        },
        "uptime": {
          "last_boot": "2026-04-02T08:15:30Z",
          "days": 14.3,
          "status": "ok",
          "error_msg": null
        },
        "boot_time": {
          "last_boot_time": "2026-04-02T09:15:30",
          "boot_duration_seconds": 115,
          "source": "event_log",
          "status": "ok",
          "error_msg": null
        },
        "services": [
          {
            "name": "EventLog",
            "display_name": "Windows Event Log",
            "state": "Running",
            "startup_type": "Automatic",
            "tier": 1,
            "status": "ok"
          },
          {
            "name": "WinDefend",
            "display_name": "Windows Defender Antivirus Service",
            "state": "Stopped",
            "startup_type": "Manual",
            "tier": 2,
            "status": "ok"
          }
        ]
      }
    }
  }
}
```

### 2.5 Reglas de construcción del payload

- El `timestamp` se captura en el momento en que el `sender` inicia el envío, no en el momento de la recogida de métricas.
- Si `metrics` queda vacío tras ejecutar todos los plugins, el agente **no envía** y registra el evento en el log local.
- El payload se serializa en UTF-8. Caracteres no ASCII en `username` o `device_id` se normalizan a ASCII o se sustituyen por `_`.
- El tamaño máximo del payload es **1 MB**. Si se supera (improbable en la POC), el agente registra el error y no envía.

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
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    agent_timestamp     TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    payload             JSONB           NOT NULL
);

CREATE INDEX idx_telemetry_raw_device_time ON telemetry_raw (device_id, received_at DESC);
CREATE INDEX idx_telemetry_raw_device_agent_ts ON telemetry_raw (device_id, agent_timestamp DESC);
```

**Restricciones:**

| Campo | Restricción |
|---|---|
| `agent_timestamp` | Timestamp del agente (extraído del campo `timestamp` del payload). Usado para deduplicación diaria. |
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

---

### 3.7 Tabla: `disk_metrics`

```sql
CREATE TABLE disk_metrics (
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

CREATE INDEX idx_disk_device_time ON disk_metrics (device_id, recorded_at DESC);
CREATE INDEX idx_disk_device_drive ON disk_metrics (device_id, drive_letter, recorded_at DESC);
```

---

### 3.8 Tablas: Health Monitor (8 tablas)

#### `health_cpu_metrics`

```sql
CREATE TABLE health_cpu_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    load_percentage     SMALLINT        NULL CHECK (load_percentage BETWEEN 0 AND 100),
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX idx_health_cpu_device_time ON health_cpu_metrics (device_id, recorded_at DESC);
```

#### `health_memory_metrics`

```sql
CREATE TABLE health_memory_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    total_kb            BIGINT          NULL CHECK (total_kb > 0),
    free_kb             BIGINT          NULL CHECK (free_kb >= 0),
    usage_pct           NUMERIC(5, 2)   NULL CHECK (usage_pct BETWEEN 0 AND 100),
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX idx_health_memory_device_time ON health_memory_metrics (device_id, recorded_at DESC);
```

#### `health_disk_metrics`

```sql
CREATE TABLE health_disk_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    drive               VARCHAR(10)     NULL,
    total_gb            NUMERIC(10, 2)  NULL CHECK (total_gb > 0),
    free_gb             NUMERIC(10, 2)  NULL CHECK (free_gb >= 0),
    free_pct            NUMERIC(5, 2)   NULL CHECK (free_pct BETWEEN 0 AND 100),
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX idx_health_disk_device_time ON health_disk_metrics (device_id, recorded_at DESC);
```

#### `health_event_metrics`

```sql
CREATE TABLE health_event_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    critical_count      INTEGER         NOT NULL DEFAULT 0 CHECK (critical_count >= 0),
    error_count         INTEGER         NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    filtered_count      INTEGER         NOT NULL DEFAULT 0 CHECK (filtered_count >= 0),
    top_sources         JSONB           NOT NULL DEFAULT '[]'::jsonb,
    sample_events       JSONB           NOT NULL DEFAULT '[]'::jsonb,
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX idx_health_event_device_time ON health_event_metrics (device_id, recorded_at DESC);
```

#### `health_domain_metrics`

```sql
CREATE TABLE health_domain_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    secure_channel      BOOLEAN         NOT NULL DEFAULT FALSE,
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX idx_health_domain_device_time ON health_domain_metrics (device_id, recorded_at DESC);
```

#### `health_uptime_metrics`

```sql
CREATE TABLE health_uptime_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_boot           TIMESTAMP       NULL,
    days                NUMERIC(5, 1)   NULL CHECK (days >= 0),
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX idx_health_uptime_device_time ON health_uptime_metrics (device_id, recorded_at DESC);
```

#### `health_boot_time_metrics`

```sql
CREATE TABLE health_boot_time_metrics (
    id                      BIGSERIAL       PRIMARY KEY,
    device_id               UUID            NOT NULL REFERENCES devices(id),
    recorded_at             TIMESTAMP       NOT NULL,
    received_at             TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_boot_time          TIMESTAMP       NULL,
    boot_duration_seconds   INTEGER         NULL CHECK (boot_duration_seconds > 0),
    source                  VARCHAR(20)     NULL,
    status                  VARCHAR(20)     NOT NULL,
    error_msg               TEXT            NULL
);

CREATE INDEX idx_health_boot_time_device_time ON health_boot_time_metrics (device_id, recorded_at DESC);
```

#### `health_service_metrics`

```sql
CREATE TABLE health_service_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    service_name        VARCHAR(100)    NOT NULL,
    display_name        VARCHAR(255)    NULL,
    state               VARCHAR(50)     NOT NULL,
    startup_type        VARCHAR(50)     NULL,
    tier                SMALLINT        NOT NULL CHECK (tier BETWEEN 0 AND 3),
    status              VARCHAR(20)     NOT NULL
);

CREATE INDEX idx_health_service_device_time ON health_service_metrics (device_id, recorded_at DESC);
CREATE INDEX idx_health_service_device_name ON health_service_metrics (device_id, service_name, recorded_at DESC);
```

---

### 3.9 Tabla: `agent_versions` *(Fase 2 — auto-update)*

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
| `409` | `DUPLICATE_SUBMISSION` | Ya existe un registro para este `device_id` en la ventana de deduplicación |
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
6. No existe ya un registro para este `device_id` en la ventana de deduplicación (±12.5h centrada en `agent_timestamp`) → `409` si existe.

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
- Se inserta en `telemetry_raw` con `agent_timestamp` del payload.
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

**Response 201 Created:**

```json
{
  "device_id": "uuid",
  "hostname": "HOSTNAME-001",
  "api_key": "string (solo se devuelve una vez, en claro)",
  "created_at": "2026-03-28T08:00:00Z"
}
```

---

### 4.5 Endpoint: `GET /api/devices`

Listado de dispositivos registrados.

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

**Response 200 OK:** Incluye `last_metrics` con las métricas más recientes de todos los plugins, incluyendo `health_monitor`.

---

### 4.7 Endpoint: `GET /api/devices/{device_id}/history`

Histórico de métricas de un dispositivo.

**Query parameters:**

| Parámetro | Tipo | Descripción | Defecto |
|---|---|---|---|
| `metric` | `string` | Filtrar por tipo | Todos |
| `from` | `string` (ISO 8601) | Fecha inicio | Hace 30 días |
| `to` | `string` (ISO 8601) | Fecha fin | Ahora |
| `limit` | `int` | Máximo de resultados por métrica | `90` |

**Valores válidos para `metric`:**
- `battery`
- `software_usage`
- `boot_time`
- `disk_usage`
- `health_cpu`
- `health_memory`
- `health_disk`
- `health_events`
- `health_domain`
- `health_uptime`
- `health_boot_time`
- `health_services`

---

### 4.8 Endpoint: `GET /api/agent/version` *(Fase 2)*

Manifiesto de versiones para auto-actualización.

**Autenticación:** No requerida.

---

## Apéndice A — Glosario

| Término | Definición |
|---|---|
| `device_id` | En el agente: hostname del equipo. En la BD: UUID de la tabla `devices`. El backend resuelve el hostname al UUID en cada petición. |
| `recorded_at` | Timestamp del momento de recogida de la métrica (lado agente), almacenado en UTC. |
| `received_at` | Timestamp de recepción en el backend. Siempre posterior a `recorded_at`. |
| `agent_timestamp` | Timestamp del agente (del campo `timestamp` del payload). Usado para deduplicación en lugar de `received_at`. |
| Plugin | Módulo Python en `agent/plugins/` que implementa `collect() -> dict | None`. |

---

## Apéndice B — Changelog

### v1.6 (2026-04-16)

**Añadido:**
- Plugin `health_monitor` con 8 métricas integradas de salud del sistema
- 8 tablas nuevas en base de datos: `health_cpu_metrics`, `health_memory_metrics`, `health_disk_metrics`, `health_event_metrics`, `health_domain_metrics`, `health_uptime_metrics`, `health_boot_time_metrics`, `health_service_metrics`
- Campo `agent_timestamp` en tabla `telemetry_raw` para deduplicación correcta
- Estados adicionales: `optimal`, `degraded`, `unknown` (boot_time), `not_in_domain` (domain), `not_available` (services)
- Estructura compleja permitida en health_monitor (dict anidado con execution metadata)
- Documentación extensa de health_monitor en sección 1.5

**Cambiado:**
- Deduplicación usa `agent_timestamp` en lugar de `received_at` (corrige bug de latencia de red)
- Índice adicional en `telemetry_raw`: `idx_telemetry_raw_device_agent_ts`

---

### v1.5 (2026-04-08)

**Añadido:**
- Plugin `disk_usage` para monitorización de múltiples unidades
- Tabla `disk_metrics` en base de datos

---

### v1.4 (2026-04-08)

**Añadido:**
- Campo `boot_source` explícito en plugin `boot_time`
- Columna `data_source` en tabla `boot_metrics`

**Cambiado:**
- Inferencia de fuente eliminada (antes se infería de `boot_duration_seconds=None`)

---

### v1.3 (2026-03-29)

**Añadido:**
- Plugin `software_usage` con soporte para múltiples targets
- Plugin `boot_time` con estrategia de fallback Event Log → WMI
- Fichero de configuración `software_targets.json`

**Cambiado:**
- `software_usage` cambia de dict a `list[dict]`
- Campos de ejecución extendidos: `executions_last_30d`, `executions_last_60d`, `executions_last_90d`

---

### Versiones anteriores

Ver documento de contratos v1.0-v1.2 para changelog completo.

---

**Fin del documento de contratos v1.6**