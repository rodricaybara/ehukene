# EHUkene — Plugin `boot_time`
## Documentación técnica

**Versión:** 1.1
**Estado:** Implementado
**Fecha:** 2026-03-31
**Fichero:** `agent/plugins/boot_time.py`
**Relacionado con:** Contratos v1.4 · Estándar de plugins v1.0

---

## Índice

1. [Propósito](#1-propósito)
2. [Requisitos](#2-requisitos)
3. [Fuentes de datos](#3-fuentes-de-datos)
4. [Contrato de retorno](#4-contrato-de-retorno)
5. [Flujo de ejecución](#5-flujo-de-ejecución)
6. [Comportamiento ante fallos](#6-comportamiento-ante-fallos)
7. [Limitaciones conocidas](#7-limitaciones-conocidas)
8. [Estructura interna del módulo](#8-estructura-interna-del-módulo)
9. [Logging](#9-logging)

---

## 1. Propósito

El plugin `boot_time` recopila métricas del proceso de arranque del sistema operativo: el momento del último inicio y la duración total del arranque. Estas métricas son un indicador de salud del equipo — tiempos de arranque elevados o en tendencia creciente señalan equipos con problemas de rendimiento que pueden requerir intervención.

El caso de uso principal en la POC es la identificación de equipos lentos: ranking de los equipos con mayor tiempo de arranque y seguimiento de su evolución temporal para detectar degradación progresiva.

---

## 2. Requisitos

| Requisito | Valor |
|---|---|
| Plataforma | Solo Windows |
| Privilegios | Administrador local |
| Dependencias externas | Ninguna (solo biblioteca estándar de Python) |
| Módulos Python | `logging`, `subprocess`, `datetime` |

> Los privilegios de administrador son necesarios para leer el canal
> `Microsoft-Windows-Diagnostics-Performance/Operational` mediante `Get-WinEvent`.
> Sin ellos, el plugin cae al fallback WMI, que proporciona `last_boot_time` pero
> no `boot_duration_seconds`.

---

## 3. Fuentes de datos

El plugin usa dos fuentes con responsabilidades distintas, no intercambiables. La fuente primaria aporta ambos campos del contrato desde un único evento. La secundaria solo puede aportar `last_boot_time`.

### Fuente 1 — Event Log (Event ID 100)

**Qué aporta:** `last_boot_time` y `boot_duration_seconds`.

Windows registra el Event ID 100 en el canal `Microsoft-Windows-Diagnostics-Performance/Operational` al finalizar cada arranque. El evento contiene todos los tiempos de fase del proceso de inicio. El plugin extrae dos campos del XML del evento:

| Campo XML | Valor en ejemplo real | Uso |
|---|---|---|
| `BootStartTime` | `"2026-03-28T07:11:38.588792900Z"` | Timestamp UTC del inicio del arranque |
| `BootTime` | `166219` | Duración total del arranque en milisegundos |

`BootStartTime` viene en UTC con nanosegundos. El plugin lo convierte a hora local sin zona horaria para cumplir el contrato, usando el offset del sistema en el momento de la ejecución.

`BootTime` se convierte a segundos enteros (`int(ms / 1000)`), con `max(1, ...)` para garantizar el invariante `boot_duration_seconds > 0` ante valores anómalos inferiores a 1000 ms.

La consulta se realiza vía `Get-WinEvent` en PowerShell (subproceso), mismo patrón que los demás plugins del agente. El script recupera los 50 eventos más recientes del canal y filtra por `Id -eq 100`, tomando el primero.

**Privilegios necesarios:** administrador local.

### Fuente 2 — WMI `Win32_OperatingSystem` (fallback)

**Qué aporta:** `last_boot_time` únicamente. `boot_duration_seconds` queda a `None`.

Consulta `Win32_OperatingSystem.LastBootUpTime` vía `Get-WmiObject` en PowerShell. WMI no expone la duración del arranque, solo el momento en que se inició el sistema.

El campo `LastBootUpTime` viene en formato WMI: `"20260328071138.000000+060"`. Los primeros 14 caracteres (`YYYYMMDDHHMMSS`) son la parte datetime en hora local; el sufijo es el offset en minutos y se descarta — el resultado ya es hora local, que es lo que requiere el contrato.

**Cuándo se activa:** cuando el canal Diagnostics-Performance no está disponible, no contiene eventos ID 100, o `Get-WinEvent` falla por cualquier motivo.

**Privilegios necesarios:** administrador local (recomendado); en la mayoría de equipos funciona con usuario estándar.

---

## 4. Contrato de retorno

`collect()` devuelve `dict | None`.

| Campo | Tipo | Nullable | Fuente | Descripción |
|---|---|---|---|---|
| `boot_source` | `str` | No | ambas | Fuente usada: `"event_log"` o `"wmi"` |
| `last_boot_time` | `str` (ISO 8601) | No | ambas | Timestamp del último arranque en hora local |
| `boot_duration_seconds` | `int` | Sí | event_log | Duración total del arranque en segundos. `None` si `boot_source` es `"wmi"` |

### Invariantes

- `boot_source` es siempre `"event_log"` o `"wmi"`. Nunca `None`.
- `last_boot_time` es siempre una cadena ISO 8601 válida: `"YYYY-MM-DDTHH:MM:SS"`.
- `boot_duration_seconds`, si presente, es `> 0`.
- `boot_duration_seconds` es `None` cuando `boot_source` es `"wmi"` (dato no disponible vía `Win32_OperatingSystem`).
- El plugin nunca devuelve `None` completo: si el Event Log o WMI están disponibles, devuelve el dict con al menos `boot_source` y `last_boot_time`.

### Valores de retorno especiales

| Valor | Significado |
|---|---|
| `dict` con los tres campos | Ejecución normal. `boot_source="event_log"`. |
| `dict` con `boot_duration_seconds=None` | Event Log no disponible. `boot_source="wmi"`. |
| `None` | Ambas fuentes fallaron. Situación excepcional. |

### Ejemplo de retorno — fuente `event_log`

```json
{
  "boot_source": "event_log",
  "last_boot_time": "2026-03-28T08:11:38",
  "boot_duration_seconds": 166
}
```

> El ejemplo corresponde al evento real capturado durante el desarrollo:
> `BootStartTime=2026-03-28T07:11:38Z` (UTC+1 → hora local `08:11:38`),
> `BootTime=166219 ms` → `166 s`.

### Ejemplo de retorno — fuente `wmi` (fallback)

```json
{
  "boot_source": "wmi",
  "last_boot_time": "2026-03-28T08:11:38",
  "boot_duration_seconds": null
}
```

---

## 5. Flujo de ejecución

```
collect()
    │
    ├── _run_event_log()
    │       Script PowerShell: Get-WinEvent, canal Diagnostics-Performance
    │       Filtra Id -eq 100, toma el primero de los 50 más recientes
    │       ¿PowerShell no encontrado?    → None  (log.debug)
    │       ¿Timeout (15s)?              → None  (log.warning)
    │       ¿"NO_EVENT" en output?       → None  (log.debug — canal sin eventos ID 100)
    │       ¿"PARSE_FAILED" en output?   → None  (log.warning — campos ausentes en XML)
    │       ¿"EVENT_LOG_ERROR=" en output? → None  (log.warning — error en Get-WinEvent)
    │       Parsea BOOT_START= y BOOT_TIME_MS= del output
    │       Convierte BootStartTime UTC → hora local → ISO 8601 sin zona
    │       Convierte BootTime ms → int segundos con max(1, ...)
    │       ¿BootTime <= 0?             → None  (log.warning)
    │       Retorna dict con boot_source="event_log" y los tres campos
    │
    ├── Si _run_event_log() devuelve None → _run_wmi()
    │       Script PowerShell: Get-WmiObject Win32_OperatingSystem
    │       ¿PowerShell no encontrado?   → None  (log.debug)
    │       ¿Timeout (15s)?             → None  (log.warning)
    │       ¿"WMI_FAILED" en output?    → None  (log.warning)
    │       ¿"WMI_ERROR=" en output?    → None  (log.warning)
    │       Parsea LAST_BOOT= del output
    │       Extrae primeros 14 chars del formato WMI → datetime hora local → ISO 8601
    │       Retorna dict con boot_source="wmi", last_boot_time y boot_duration_seconds=None
    │
    └── Si ambas devuelven None → collect() devuelve None  (log.warning)
```

---

## 6. Comportamiento ante fallos

| Situación | Comportamiento |
|---|---|
| PowerShell no encontrado en PATH (event_log) | Cae a WMI. `DEBUG` en log. |
| `Get-WinEvent` excede timeout (15s) | Cae a WMI. `WARNING` en log. |
| Canal Diagnostics-Performance desactivado o sin eventos ID 100 | Cae a WMI. `DEBUG` en log. |
| Campos `BootStartTime` o `BootTime` ausentes en el XML del evento | Cae a WMI. `WARNING` en log. |
| `BootStartTime` no parseable como ISO 8601 | Cae a WMI. `WARNING` en log. |
| `BootTime` no es entero válido | Cae a WMI. `WARNING` en log. |
| `BootTime` <= 0 | Cae a WMI. `WARNING` en log. |
| Error en `Get-WinEvent` (permisos, canal corrupto) | Cae a WMI. `WARNING` en log. |
| PowerShell no encontrado en PATH (WMI) | `collect()` devuelve `None`. `DEBUG` en log. |
| `Get-WmiObject` excede timeout (15s) | `collect()` devuelve `None`. `WARNING` en log. |
| `Win32_OperatingSystem` no devuelve instancias | `collect()` devuelve `None`. `WARNING` en log. |
| `LastBootUpTime` no parseable (formato WMI inesperado) | `collect()` devuelve `None`. `WARNING` en log. |
| Error en `Get-WmiObject` (WMI corrupto) | `collect()` devuelve `None`. `WARNING` en log. |
| Excepción inesperada en `collect()` | `None` + `EXCEPTION` en log (con traceback). |

---

## 7. Limitaciones conocidas

### `boot_duration_seconds` no disponible cuando el Event Log cae al fallback

Si el canal `Diagnostics-Performance` no está activo o no tiene eventos ID 100, el plugin reporta `boot_duration_seconds=null`. Esto puede ocurrir en equipos con el servicio de Prefetch desactivado, en algunas configuraciones de servidor, o en equipos con Secure Boot en configuraciones específicas. El campo `data_source` en `boot_metrics` permite identificar qué proporción del parque está en esta situación.

### El Event ID 100 puede no reflejar el arranque actual tras tiempo prolongado

El Visor de Eventos tiene capacidad limitada. En equipos que llevan semanas encendidos sin reiniciarse, el Event ID 100 del arranque actual puede haber sido desplazado por eventos más recientes (rearranques parciales, actualizaciones). En ese caso, `_run_event_log()` devuelve `None` y el plugin cae a WMI. Esta situación es infrecuente dado que el agente solo se ejecuta una vez al día en el inicio de sesión.

### `BootTime` incluye toda la fase de arranque hasta escritorio funcional

El campo `BootTime` mide desde que el kernel toma el control hasta que el escritorio está operativo para el usuario. No incluye el tiempo de POST/BIOS ni el tiempo del cargador de arranque (`OSLoaderDuration` es un campo separado del mismo evento). El dato es consistente entre equipos y suficiente para el caso de uso de comparación relativa.

### Conversión UTC → hora local depende del offset del sistema en el momento de ejecución

`BootStartTime` viene en UTC. La conversión a hora local se realiza con el offset activo en el momento en que el agente ejecuta el plugin, no en el momento del arranque. En equipos que atraviesan un cambio de horario entre el arranque y la ejecución del agente, el timestamp reportado puede diferir en una hora respecto a la hora local real del arranque. El backend almacena en UTC, por lo que el impacto se limita a la visualización en hora local.

---

## 8. Estructura interna del módulo

```
boot_time.py
│
├── Imports
├── log = logging.getLogger(__name__)
├── Constantes
│     _EVENT_LOG_TIMEOUT_S    timeout para Get-WinEvent (15s)
│     _WMI_TIMEOUT_S          timeout para Get-WmiObject (15s)
│     _BOOT_START_CORR_MAX_S  reservado para correlación futura (300s)
│
├── Fuente 1: Event Log — Event ID 100
│     _run_event_log()        script PowerShell embebido + parseo de output
│                             convierte BootStartTime UTC → hora local ISO 8601
│                             convierte BootTime ms → int segundos
│
├── Fuente 2: WMI Win32_OperatingSystem (fallback)
│     _run_wmi()              script PowerShell embebido + parseo de output
│                             extrae LastBootUpTime del formato WMI
│                             boot_duration_seconds fijo a None
│
└── Punto de entrada
      collect()               interfaz pública, estrategia event_log → WMI → None
```

---

## 9. Logging

Todos los mensajes usan el logger del módulo (`logging.getLogger(__name__)`). El plugin no configura handlers ni formatters.

| Situación | Nivel | Ejemplo de mensaje |
|---|---|---|
| Inicio de intento de fuente | `DEBUG` | `boot_time: intentando fuente event_log` |
| Canal sin eventos ID 100 | `DEBUG` | `event_log: canal disponible pero sin eventos ID 100` |
| PowerShell no encontrado (event_log) | `DEBUG` | `event_log: PowerShell no encontrado en PATH` |
| PowerShell no encontrado (WMI) | `DEBUG` | `wmi: PowerShell no encontrado en PATH` |
| Campos XML ausentes en el evento | `WARNING` | `event_log: BootStartTime o BootTime ausentes en el XML del evento` |
| Error en `Get-WinEvent` | `WARNING` | `event_log: error al consultar el Event Log: <mensaje>` |
| `Get-WinEvent` excede timeout | `WARNING` | `event_log: Get-WinEvent excedió el timeout de 15s` |
| Error de parseo de `BootStartTime` | `WARNING` | `event_log: no se pudo parsear BootStartTime '...': <exc>` |
| `BootTime` no válido | `WARNING` | `event_log: BootTime = 0 ms, valor no válido` |
| `Win32_OperatingSystem` sin instancias | `WARNING` | `wmi: Win32_OperatingSystem no devolvió instancias` |
| Error en `Get-WmiObject` | `WARNING` | `wmi: error al consultar WMI: <mensaje>` |
| `Get-WmiObject` excede timeout | `WARNING` | `wmi: Get-WmiObject excedió el timeout de 15s` |
| Error de parseo de `LastBootUpTime` | `WARNING` | `wmi: no se pudo parsear LastBootUpTime '...': <exc>` |
| Ambas fuentes fallaron | `WARNING` | `boot_time: ambas fuentes fallaron` |
| Éxito con Event Log | `DEBUG` | `boot_time: event_log OK — last_boot=2026-03-28T08:11:38 duration=166s` |
| Éxito con WMI | `DEBUG` | `boot_time: WMI OK — last_boot=2026-03-28T08:11:38 (duration no disponible)` |
| Excepción inesperada en `collect()` | `EXCEPTION` | Incluye traceback completo |
