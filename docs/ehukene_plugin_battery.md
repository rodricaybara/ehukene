# EHUkene — Plugin `battery`
## Documentación técnica

**Versión:** 1.1
**Estado:** Implementado
**Fecha:** 2026-03-30
**Fichero:** `agent/plugins/battery.py`
**Relacionado con:** Contratos v1.1 · Estándar de plugins v1.0

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

El plugin `battery` recopila métricas de salud y estado de la batería del equipo. Calcula el porcentaje de degradación comparando la capacidad de diseño original con la capacidad máxima actual, e incluye metadatos de identificación del pack de batería cuando la fuente primaria los expone.

El caso de uso principal en la POC es la planificación de reposición de hardware: detectar equipos con baterías degradadas por debajo de umbrales operativos para programar su sustitución de forma anticipada.

---

## 2. Requisitos

| Requisito | Valor |
|---|---|
| Plataforma | Solo Windows, equipos con batería |
| Privilegios | Administrador local |
| Dependencias externas | Ninguna (solo biblioteca estándar de Python) |
| Módulos Python | `logging`, `os`, `re`, `subprocess`, `tempfile`, `html.parser` |

> Los privilegios de administrador son necesarios para ejecutar `powercfg /batteryreport`. Sin ellos, el plugin cae al fallback WMI, que sí funciona con usuario estándar en la mayoría de equipos.

---

## 3. Fuentes de datos

El plugin usa dos fuentes con estrategia de fallback ordenado. Si la fuente primaria falla o no está disponible, se intenta la secundaria antes de devolver `None`.

### Fuente 1 — `powercfg /batteryreport`

**Qué aporta:** todos los campos del contrato excepto `battery_status`.

Windows genera un informe HTML en una ruta temporal configurable vía `/output`. El plugin ejecuta el comando con `/duration 1` (ventana de 1 día, suficiente para los datos estáticos de instalación) y parsea el HTML resultante mediante `_BatteryReportParser`.

El parser implementa un autómata de estados que localiza la sección `Installed batteries` del informe y extrae los valores de sus celdas de tabla. El formato HTML es producido por Windows y estructuralmente estable entre versiones de sistema operativo.

**Campos obtenidos:** `battery_name`, `battery_manufacturer`, `battery_serial`, `battery_chemistry`, `battery_design_capacity_wh`, `battery_full_charge_capacity_wh`.

**Capacidades:** reportadas en formato `"60.002 mWh"` o `"21,683 mWh"` según el locale del sistema. El parser normaliza ambos formatos (punto y coma como separador decimal) antes de convertir a `float`.

**Señal de equipo sin batería:** el informe incluye la cadena `"No battery is installed"` cuando el equipo no dispone de batería. El plugin detecta esta condición y devuelve `None` limpio, sin considerarlo un error.

**Privilegios necesarios:** administrador local.

### Fuente 2 — WMI via PowerShell (fallback)

**Qué aporta:** `battery_design_capacity_wh`, `battery_full_charge_capacity_wh`, `battery_status`. Los campos de identificación (`name`, `manufacturer`, `serial`, `chemistry`) quedan a `None`.

Se evita la dependencia del paquete `wmi` (que requiere `pywin32`) y los problemas de WMI en modo WOW64 —documentados en el script Ivanti preexistente— delegando la consulta a un subproceso PowerShell que usa `Get-WmiObject` (stack DCOM/RPC).

Las clases consultadas son:

| Clase WMI | Namespace | Campo extraído |
|---|---|---|
| `Win32_Battery` | `root\cimv2` | `BatteryStatus` — detección y estado actual |
| `BatteryStaticData` | `root\WMI` | `DesignedCapacity` en mWh |
| `BatteryFullChargedCapacity` | `root\WMI` | `FullChargedCapacity` en mWh |

Los valores de capacidad llegan en mWh enteros y se convierten a Wh (`/ 1000`) antes de incluirlos en el dict de retorno, manteniendo la unidad uniforme definida en el contrato.

**Señal de equipo sin batería:** el script PowerShell emite la cadena `NO_BATTERY` cuando `Win32_Battery` no devuelve instancias. El plugin la detecta y devuelve `None` limpio.

**Señal de fallo WMI:** el script emite `WMI_FAILED` si `BatteryStaticData` o `BatteryFullChargedCapacity` no están disponibles.

**Privilegios necesarios:** administrador local (recomendado); en muchos equipos funciona con usuario estándar.

---

## 4. Contrato de retorno

`collect()` devuelve `dict | None`.

| Campo | Tipo | Nullable | Fuente | Descripción |
|---|---|---|---|---|
| `battery_source` | `str` | No | — | Fuente usada: `"powercfg"` o `"wmi"` |
| `battery_name` | `str` | Sí | powercfg | Nombre/modelo del pack (ej. `"DELL V49408B"`) |
| `battery_manufacturer` | `str` | Sí | powercfg | Fabricante (ej. `"Samsung SDI"`) |
| `battery_serial` | `str` | Sí | powercfg | Número de serie (ej. `"6322"`) |
| `battery_chemistry` | `str` | Sí | powercfg | Química: `"LION"`, `"NIMH"`, `"NICD"`, etc. |
| `battery_design_capacity_wh` | `float` | No | ambas | Capacidad original en Wh, 3 decimales (ej. `60.002`) |
| `battery_full_charge_capacity_wh` | `float` | No | ambas | Capacidad máxima actual en Wh, 3 decimales (ej. `21.683`) |
| `battery_health_percent` | `float` | No | ambas | `(full / design) × 100`, 1 decimal (ej. `36.1`) |
| `battery_status` | `int` | Sí | wmi | Código WMI de estado. `None` si la fuente es `"powercfg"` |

### Invariantes

- `battery_source` es siempre `"powercfg"` o `"wmi"`. Nunca `None`.
- `battery_design_capacity_wh > 0.0` siempre.
- `battery_full_charge_capacity_wh >= 0.0` siempre.
- `battery_health_percent` en rango `[0.0, 150.0]`. Fuera de rango → `None`.
- `battery_status` en rango `[1, 11]` cuando presente. Valor fuera de rango se incluye igualmente pero se registra como anomalía en el log.
- Cuando `battery_source` es `"wmi"`: `battery_name`, `battery_manufacturer`, `battery_serial` y `battery_chemistry` son `None`.

### Valores de retorno especiales

| Valor | Significado |
|---|---|
| `dict` | Ejecución normal. |
| `None` | Equipo sin batería, o ambas fuentes fallaron. |

### Ejemplo de retorno — fuente `powercfg`

```json
{
  "battery_source": "powercfg",
  "battery_name": "DELL V49408B",
  "battery_manufacturer": "Samsung SDI",
  "battery_serial": "6322",
  "battery_chemistry": "LION",
  "battery_design_capacity_wh": 60.002,
  "battery_full_charge_capacity_wh": 21.683,
  "battery_health_percent": 36.1,
  "battery_status": null
}
```

### Ejemplo de retorno — fuente `wmi` (fallback)

```json
{
  "battery_source": "wmi",
  "battery_name": null,
  "battery_manufacturer": null,
  "battery_serial": null,
  "battery_chemistry": null,
  "battery_design_capacity_wh": 60.002,
  "battery_full_charge_capacity_wh": 21.683,
  "battery_health_percent": 36.1,
  "battery_status": 2
}
```

---

## 5. Flujo de ejecución

```
collect()
    │
    ├── _run_powercfg()
    │       Ejecuta: powercfg /batteryreport /output <tmp> /duration 1
    │       ¿returncode != 0?  → None  (log.debug)
    │       ¿Timeout?          → None  (log.warning)
    │       Lee HTML del fichero temporal → lo elimina en finally
    │       ¿"no battery is installed"?  → None  (log.debug, equipo sin batería)
    │       _BatteryReportParser.feed(html)
    │           Localiza sección "Installed batteries"
    │           Extrae celdas: NAME, MANUFACTURER, SERIAL NUMBER,
    │                          CHEMISTRY, DESIGN CAPACITY, FULL CHARGE CAPACITY
    │           Normaliza formato de capacidad (coma/punto decimal)
    │           Convierte a float en Wh con 3 decimales
    │       ¿design <= 0?    → None  (log.debug)
    │       ¿full < 0?       → None  (log.debug)
    │       Calcula health = round(full / design * 100, 1)
    │       ¿health fuera de [0, 150]? → None  (log.warning)
    │       Retorna dict completo con battery_status=None
    │
    ├── Si _run_powercfg() devuelve None → _run_wmi()
    │       Script PowerShell con Get-WmiObject:
    │           Win32_Battery          → detección + BatteryStatus
    │           BatteryStaticData      → DesignedCapacity (mWh)
    │           BatteryFullChargedCapacity → FullChargedCapacity (mWh)
    │       ¿"NO_BATTERY" en output?  → None  (sin batería)
    │       ¿"WMI_FAILED" en output?  → None  (log.warning)
    │       Parsea DESIGN=, FULL=, STATUS= del output
    │       ¿design <= 0?    → None  (log.warning)
    │       Convierte mWh → Wh (/ 1000, 3 decimales)
    │       Calcula health = round(full / design * 100, 1)
    │       ¿health fuera de [0, 150]? → None  (log.warning)
    │       ¿status fuera de [1, 11]?  → incluye igualmente (log.warning)
    │       Retorna dict completo con name/manufacturer/serial/chemistry=None
    │
    └── Si ambas devuelven None → collect() devuelve None
```

---

## 6. Comportamiento ante fallos

| Situación | Comportamiento |
|---|---|
| `powercfg` no encontrado en PATH | Cae a WMI. `DEBUG` en log. |
| `powercfg` excede timeout (20s) | Cae a WMI. `WARNING` en log. |
| `powercfg` retorna código de error | Cae a WMI. `DEBUG` en log. |
| Error al leer el HTML temporal | Cae a WMI. `WARNING` en log. |
| Error al parsear el HTML | Cae a WMI. `WARNING` en log. |
| `design_capacity` no válida (powercfg) | Cae a WMI. `DEBUG` en log. |
| Equipo sin batería (detectado por powercfg) | Cae a WMI para confirmar. Si WMI también confirma `NO_BATTERY` → `None`. `DEBUG` en log. |
| PowerShell no encontrado | `collect()` devuelve `None`. `DEBUG` en log. |
| WMI timeout (15s) | `collect()` devuelve `None`. `DEBUG` en log. |
| `WMI_FAILED` (clases no disponibles) | `collect()` devuelve `None`. `WARNING` en log. |
| `design_capacity` no válida (WMI) | `collect()` devuelve `None`. `WARNING` en log. |
| `health_percent` fuera de `[0, 150]` | `collect()` devuelve `None`. `WARNING` en log. |
| `battery_status` fuera de `[1, 11]` | Se incluye en el dict. `WARNING` en log. |
| Excepción inesperada en `collect()` | `None` + `EXCEPTION` en log (con traceback). |

---

## 7. Limitaciones conocidas

### `battery_status` no disponible vía `powercfg`

El informe HTML de `powercfg` no expone el estado actual de la batería (cargando, descargando, etc.). Cuando la fuente es `"powercfg"`, el campo `battery_status` es siempre `None`. Si el estado es necesario, el sistema puede combinar este campo con el valor devuelto por una ejecución posterior del fallback WMI, aunque esto no está contemplado en el flujo actual.

### Campos de identificación no disponibles vía WMI

`BatteryStaticData` en `root\WMI` expone `ManufactureName` y `DeviceName`, pero estos valores son inconsistentes o están vacíos en una proporción significativa de equipos según fabricante y versión de driver. Por esta razón, el contrato v1.1 establece explícitamente que `battery_name`, `battery_manufacturer`, `battery_serial` y `battery_chemistry` son `None` cuando la fuente es `"wmi"`.

### `CYCLE COUNT` no recogido

El campo `Cycle Count` aparece en el informe `powercfg` pero la mayoría de fabricantes no lo exponen (`-`). El contrato v1.1 descartó este campo por no ser fiable. No se recoge.

### Fichero temporal de `powercfg`

El plugin escribe el informe HTML en el directorio temporal del sistema (`%TEMP%`) con nombre fijo `ehukene_batteryreport.html`. El fichero se elimina en el bloque `finally` inmediatamente después de la lectura. En caso de fallo de eliminación, el fichero queda en disco hasta la siguiente ejecución del agente, que lo sobreescribirá.

### Equipos con múltiples baterías

El parser extrae únicamente los datos del primer pack de batería encontrado en la sección `Installed batteries`. Los equipos con dos baterías (algunos modelos de workstation móvil) reportarán solo la primera.

---

## 8. Estructura interna del módulo

```
battery.py
│
├── Imports
├── log = logging.getLogger(__name__)
├── Constantes
│     _POWERCFG_TIMEOUT_S   timeout en segundos para powercfg (20)
│     _PLUGIN_MAX_HEALTH    límite superior del rango de salud (150.0)
│
├── Fuente 1: powercfg /batteryreport
│     _BatteryReportParser  parser HTML basado en HTMLParser
│         _FIELD_MAP        mapeo de etiquetas HTML → atributos del parser
│         handle_starttag() gestión de apertura de etiquetas td/h2
│         handle_endtag()   cierre de td: despacha _process_td_text()
│         handle_data()     detección de sección y captura de texto de celda
│         _process_td_text() autómata etiqueta/valor
│         _parse_capacity_wh() conversión de cadena mWh a float Wh
│         design_capacity_wh()      accessor
│         full_charge_capacity_wh() accessor
│     _run_powercfg()       orquesta ejecución, lectura y parseo del informe
│
├── Fuente 2: WMI via PowerShell (fallback)
│     _run_wmi()            script PowerShell embebido + parseo de output
│
└── Punto de entrada
      collect()             interfaz pública, estrategia powercfg → WMI → None
```

---

## 9. Logging

Todos los mensajes usan el logger del módulo (`logging.getLogger(__name__)`). El plugin no configura handlers ni formatters.

| Situación | Nivel | Ejemplo |
|---|---|---|
| Inicio de intento de fuente | `DEBUG` | `battery: intentando fuente powercfg` |
| Equipo sin batería (cualquier fuente) | `DEBUG` | `powercfg: equipo sin batería` |
| `powercfg` no encontrado en PATH | `DEBUG` | `powercfg no encontrado en PATH` |
| `powercfg` retorna código de error | `DEBUG` | `powercfg retornó 1: ...` |
| Dato de capacidad no válido (design/full) | `DEBUG` | `powercfg: design_capacity_wh no válida (None)` |
| `powercfg` excede timeout | `WARNING` | `powercfg excedió el timeout de 20s` |
| Error al leer o parsear el HTML | `WARNING` | `No se pudo leer el informe de powercfg: ...` |
| WMI fallback via PowerShell falló | `DEBUG` | `WMI fallback via PowerShell falló: ...` |
| Clases WMI no disponibles | `WARNING` | `WMI: BatteryStaticData o BatteryFullChargedCapacity no disponibles` |
| `design_capacity` inválida (WMI) | `WARNING` | `WMI: DesignedCapacity = 0 mWh, no válido` |
| `health_percent` fuera de rango | `WARNING` | `WMI: battery_health_percent fuera de rango: 160.0 (...)` |
| `battery_status` fuera de `[1, 11]` | `WARNING` | `WMI: battery_status=0 fuera del rango esperado [1,11]` |
| Éxito de recogida | `DEBUG` | `battery: powercfg OK — health=36.1% design=60.002 Wh full=21.683 Wh` |
| Excepción inesperada en `collect()` | `EXCEPTION` | Incluye traceback completo |
