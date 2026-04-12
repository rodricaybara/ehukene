# EHUkene — Estándar de diseño de plugins
## Documento de referencia

**Versión:** 1.0
**Estado:** Diseño
**Fecha:** 2026-03-29
**Relacionado con:** Documento técnico v1.0 · Contratos v1.1

> Este documento define el estándar que debe seguir todo plugin del agente EHUkene. El plugin `battery` es la implementación de referencia. Cualquier desviación respecto a este estándar es un bug de diseño, no de código.

---

## Índice

1. [Qué es un plugin](#1-qué-es-un-plugin)
2. [Cabecera de módulo](#2-cabecera-de-módulo)
3. [Estructura interna del fichero](#3-estructura-interna-del-fichero)
4. [Funciones de fuente `_run_*()`](#4-funciones-de-fuente-_run_)
5. [Función `collect()`](#5-función-collect)
6. [Tipos y serialización](#6-tipos-y-serialización)
7. [Logging](#7-logging)
8. [Lo que un plugin NO puede hacer](#8-lo-que-un-plugin-no-puede-hacer)
9. [Checklist de validación](#9-checklist-de-validación)
10. [Plantilla base](#10-plantilla-base)

---

## 1. Qué es un plugin

Un plugin es un módulo Python ubicado en `agent/plugins/`. Su única responsabilidad es recoger un conjunto de métricas del equipo y devolverlas en un dict serializable.

El sistema de plugins se rige por tres principios:

- **Aislamiento.** Un plugin no conoce la existencia de otros plugins, ni del collector, ni del sender.
- **Contrato estricto.** Cada plugin publica exactamente las claves definidas en `ehukene_contratos.md §1.5`. Ni más, ni menos.
- **Resiliencia.** Un plugin nunca propaga excepciones. Si falla, devuelve `None` y el sistema continúa.

---

## 2. Cabecera de módulo

Todo plugin comienza con un docstring de módulo que documenta su contrato completo. Es la primera cosa que lee un desarrollador y debe ser autosuficiente.

```python
"""
Plugin: <nombre>
Fuente principal : <descripción de la fuente primaria>
Fallback         : <descripción del fallback, si existe; omitir la línea si no>
Privilegios      : <Usuario estándar | Administrador local>
Plataforma       : <Solo Windows | Solo Windows, equipos con batería>

Contrato de retorno (ehukene_contratos.md §1.5 — <nombre>, vX.Y):

    {
        "campo_1": tipo,
        "campo_2": tipo | None,
        ...
    }

    Devuelve None si <condición de equipo no aplicable o ambas fuentes fallan>.

Invariantes:
    - <invariante 1>
    - <invariante 2>
    ...
"""
```

**Reglas:**

- El contrato documentado en la cabecera debe ser copia exacta de `ehukene_contratos.md`. Si difieren, el documento de contratos es la fuente de verdad y la cabecera está desactualizada.
- La sección `Fallback` se omite si el plugin solo tiene una fuente de datos.
- Los invariantes se copian literalmente del documento de contratos.

---

## 3. Estructura interna del fichero

El fichero se organiza siempre en este orden, separado por bloques comentados:

```
1.  Imports
2.  logger
3.  Constantes
4.  Bloque fuente 1   (_run_<fuente1>() + clases auxiliares si las hay)
5.  Bloque fuente 2   (_run_<fuente2>())   ← omitir si no hay fallback
6.  Punto de entrada  (collect())
```

### Separadores de bloque

Los bloques principales se separan con una línea de `=`:

```python
# ===========================================================================
# Fuente 1: <nombre de fuente>
# ===========================================================================
```

Las subsecciones internas de un bloque usan una línea de `─`:

```python
# ── <descripción> ────────────────────────────────────────────────────────────
```

### Imports

Se ordenan en tres grupos separados por línea en blanco, en este orden:

1. Módulos de la biblioteca estándar
2. Paquetes de terceros (si los hay)
3. Módulos propios del agente (prohibido — ver sección 8)

### Logger

La segunda línea tras los imports, siempre:

```python
log = logging.getLogger(__name__)
```

### Constantes

Las constantes del plugin usan prefijo `_` y nombres en `MAYÚSCULAS_CON_GUIONES`. Se agrupan tras el logger con un comentario de sección:

```python
# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_POWERCFG_TIMEOUT_S = 20
_PLUGIN_MAX_HEALTH  = 150.0
```

---

## 4. Funciones de fuente `_run_*()`

Cada fuente de datos se implementa como una función privada independiente.

### Firma

```python
def _run_<fuente>() -> dict | None:
    """Descripción de qué consulta y qué devuelve."""
```

### Contrato de retorno

- Devuelve el dict **completo** con todas las claves del contrato del plugin, o `None`.
- Nunca devuelve un dict parcial. Si la fuente no puede construir todas las claves requeridas, devuelve `None`.
- Los campos no disponibles para esta fuente se incluyen con valor `None` explícito.

```python
# Correcto: todas las claves presentes, las no disponibles como None
return {
    "battery_source":                  "wmi",
    "battery_name":                    None,   # no disponible vía WMI
    "battery_manufacturer":            None,
    "battery_design_capacity_wh":      design_wh,
    "battery_health_percent":          health,
    "battery_status":                  status,
}

# Incorrecto: dict parcial
return {
    "battery_design_capacity_wh": design_wh,
    "battery_health_percent":     health,
}
```

### Gestión de errores

Cada función captura sus propias excepciones internamente. Nada se propaga hacia `collect()`. El patrón general es:

```python
try:
    # operación que puede fallar
except TipoEspecífico as exc:
    log.warning("Descripción del fallo: %s", exc)
    return None
except Exception as exc:
    log.warning("Error inesperado en <fuente>: %s", exc)
    return None
```

### Señales de "equipo no aplicable"

Cuando la fuente determina que el equipo no tiene el hardware o software que el plugin mide (sin batería, software no instalado), el retorno es `None` limpio — no es un error. Se loguea con `log.debug`, no con `log.warning`:

```python
if "no battery is installed" in html_content.lower():
    log.debug("powercfg: equipo sin batería")
    return None  # No es un error, el equipo simplemente no aplica
```

### Conversión de unidades

Las conversiones de unidades se realizan dentro de `_run_*()`, antes de construir el dict de retorno. El dict que devuelve `_run_*()` ya sale en las unidades definidas en el contrato.

```python
# Conversión mWh → Wh dentro de _run_wmi(), antes del return
design_wh = round(design_mwh / 1000, 3)
full_wh   = round(full_mwh   / 1000, 3)
```

### Validación de invariantes

Cada `_run_*()` valida los invariantes del contrato antes de devolver el dict. Si un invariante se viola, el comportamiento depende del contrato:

- **Dato inválido que invalida el resultado** (p.ej. `design_capacity <= 0`, `health_percent` fuera de `[0, 150]`): loguear con `log.warning` y devolver `None`.
- **Dato anómalo pero incluible** (p.ej. `battery_status` fuera de `[1, 11]`): loguear con `log.warning` e incluir el valor igualmente.

El documento de contratos especifica para cada campo cuál de los dos casos aplica.

---

## 5. Función `collect()`

Es la única función pública del módulo. Su forma es siempre la misma.

### Firma

```python
def collect() -> dict | None:
```

### Estructura para plugins con fallback

```python
def collect() -> dict | None:
    """
    Interfaz pública del plugin.  El collector llama únicamente a esta función.

    Estrategia de fuente con fallback (contrato §1.5):
        1. <fuente 1>  → <descripción>
        2. <fuente 2>  → si <condición de fallback>
        3. Devuelve None → si ambas fuentes fallan

    Nunca lanza excepciones al caller.
    """
    try:
        log.debug("<nombre>: intentando fuente <fuente1>")
        result = _run_<fuente1>()
        if result is not None:
            log.debug(
                "<nombre>: <fuente1> OK — <campo>=<formato>",
                result["<campo>"],
            )
            return result

        log.debug("<nombre>: <fuente1> sin resultado, intentando <fuente2>")
        result = _run_<fuente2>()
        if result is not None:
            log.debug(
                "<nombre>: <fuente2> OK — <campo>=<formato>",
                result["<campo>"],
            )
            return result

        log.debug("<nombre>: ambas fuentes sin resultado (<motivo probable>)")
        return None

    except Exception as exc:  # noqa: BLE001
        log.exception("<nombre>: excepción no esperada en collect(): %s", exc)
        return None
```

### Estructura para plugins con una sola fuente

```python
def collect() -> dict | None:
    """
    Interfaz pública del plugin.  El collector llama únicamente a esta función.

    Fuente: <descripción>
    Devuelve None si <condición de no aplicabilidad o fallo>.

    Nunca lanza excepciones al caller.
    """
    try:
        log.debug("<nombre>: recogiendo métricas")
        result = _run_<fuente>()
        if result is not None:
            log.debug("<nombre>: OK — <campo>=<formato>", result["<campo>"])
            return result

        log.debug("<nombre>: sin resultado (<motivo probable>)")
        return None

    except Exception as exc:  # noqa: BLE001
        log.exception("<nombre>: excepción no esperada en collect(): %s", exc)
        return None
```

### Reglas de `collect()`

- El bloque `try/except Exception` que envuelve todo el cuerpo es **obligatorio**. Es la garantía del contrato "nunca lanza excepciones al caller".
- `collect()` no contiene lógica de negocio. Solo orquesta las llamadas a `_run_*()` y loguea el resultado.
- Los mensajes de log tienen siempre el prefijo `"<nombre_plugin>: "`.
- El `log.debug` de éxito incluye el campo más representativo del resultado (p.ej. `health_percent`, `boot_duration_seconds`) para que el diagnóstico sea útil sin ejecutar el CLI.

---

## 6. Tipos y serialización

Toda la disciplina de tipos recae en el dict de retorno. El collector y el sender no transforman los valores.

### Tabla de tipos

| Tipo en el contrato | Tipo Python | Aplicación |
|---|---|---|
| `float (N decimales)` | `round(valor, N)` | Siempre redondear explícitamente al construir el dict |
| `str \| None` | `str` o `None` | Nunca devolver cadena vacía `""` donde el contrato admite `None` |
| `int \| None` | `int` o `None` | Convertir explícitamente con `int()` si el origen es otro tipo |
| `bool` | `bool` nativo | Usar `True`/`False`, no `1`/`0` |
| Timestamp ISO 8601 | `str` `"YYYY-MM-DDTHH:MM:SS"` | Usar `datetime.isoformat()` sobre un objeto `datetime` sin zona |

### Cadenas vacías

Si una fuente devuelve una cadena vacía para un campo que el contrato define como `str | None`, se normaliza a `None`:

```python
# Correcto
"battery_name": parser.battery_name or None

# Incorrecto
"battery_name": parser.battery_name   # puede ser ""
```

### Timestamps

Los timestamps se generan siempre en hora local sin zona horaria, en formato `"YYYY-MM-DDTHH:MM:SS"`. La conversión a UTC es responsabilidad del backend, no del plugin.

```python
from datetime import datetime

boot_dt = datetime.strptime(last_boot_raw[:14], "%Y%m%d%H%M%S")
"last_boot_time": boot_dt.isoformat()   # "2026-03-28T07:58:00"
```

---

## 7. Logging

El agente usa el módulo `logging` estándar. Los plugins no configuran handlers ni formatters — solo usan el logger del módulo.

### Niveles

| Situación | Nivel |
|---|---|
| Fuente no disponible en este equipo (sin batería, sin software instalado) | `DEBUG` |
| Fuente disponible pero falla (permisos, timeout, parse error) | `WARNING` |
| Dato obtenido pero fuera de rango / anomalía | `WARNING` |
| Éxito de recogida (en `collect()`) | `DEBUG` |
| Excepción inesperada capturada en `collect()` | `EXCEPTION` (incluye traceback) |

### Formato de mensajes

Los mensajes dentro de `_run_*()` son descriptivos del contexto de la fuente:

```python
log.debug("powercfg: equipo sin batería")
log.warning("powercfg: excedió el timeout de %ds", _POWERCFG_TIMEOUT_S)
log.warning("WMI: battery_health_percent fuera de rango: %.1f", health)
```

Los mensajes dentro de `collect()` llevan el prefijo con el nombre del plugin:

```python
log.debug("battery: intentando fuente powercfg")
log.debug("battery: powercfg OK — health=%.1f%%", result["battery_health_percent"])
log.exception("battery: excepción no esperada en collect(): %s", exc)
```

---

## 8. Lo que un plugin NO puede hacer

Estas restricciones son absolutas. Un plugin que viola cualquiera de ellas incumple el contrato del sistema.

- **No importar módulos de `core/`** (`sender`, `collector`, `config`, `plugin_loader`).
- **No comunicarse con el backend** ni con ningún servicio de red externo.
- **No leer ni escribir `config.json`**.
- **No escribir en disco** fuera de lo estrictamente necesario para su operación (p.ej. ficheros temporales que el propio plugin limpia).
- **No modificar el estado de otros plugins** ni del entorno de ejecución de forma observable.
- **No lanzar subprocesos sin capturar su resultado y su excepción**.
- **No devolver un dict parcial**. El dict de retorno contiene siempre todas las claves del contrato.
- **No propagar excepciones al caller**.

---

## 9. Checklist de validación

Antes de considerar un plugin completo, debe superar todos estos puntos:

**Estructura y documentación**
- [ ] Cabecera de módulo con Plugin, Fuente, Privilegios, Plataforma, Contrato e Invariantes
- [ ] El contrato de la cabecera coincide con `ehukene_contratos.md §1.5`
- [ ] `log = logging.getLogger(__name__)` presente tras los imports
- [ ] Constantes con prefijo `_` en `MAYÚSCULAS`
- [ ] Bloques separados con los comentarios de sección correctos

**Funciones de fuente**
- [ ] Una función `_run_*()` por fuente de datos
- [ ] Cada `_run_*()` devuelve el dict completo o `None`, nunca parcial
- [ ] Los campos no disponibles para una fuente se incluyen como `None` explícito
- [ ] Las conversiones de unidades ocurren dentro de `_run_*()`, antes del `return`
- [ ] Los invariantes del contrato se validan antes de construir el dict
- [ ] Las señales de "equipo no aplicable" se loguean como `DEBUG`, no como `WARNING`

**`collect()`**
- [ ] `try/except Exception` envuelve todo el cuerpo
- [ ] `collect()` no contiene lógica de negocio
- [ ] Log de éxito incluye el campo más representativo del resultado
- [ ] Mensajes de log con prefijo `"<nombre_plugin>: "`

**Tipos**
- [ ] Los `float` se construyen con `round(valor, N)` con el número de decimales del contrato
- [ ] Las cadenas vacías se normalizan a `None` donde el contrato admite `None`
- [ ] Los timestamps son `str` en formato ISO 8601 sin zona horaria

**Restricciones**
- [ ] Sin imports de `core/`
- [ ] Sin comunicación con el backend
- [ ] Sin acceso a `config.json`
- [ ] Sin efectos secundarios observables fuera de la lectura de métricas

---

## 10. Plantilla base

Esqueleto mínimo para un plugin nuevo. Sustituir todos los `<marcadores>` antes de implementar la lógica.

```python
"""
Plugin: <nombre>
Fuente principal : <descripción>
Fallback         : <descripción>  ← eliminar si no hay fallback
Privilegios      : <Usuario estándar | Administrador local>
Plataforma       : Solo Windows

Contrato de retorno (ehukene_contratos.md §1.5 — <nombre>, vX.Y):

    {
        "<campo_1>": <tipo>,
        "<campo_2>": <tipo> | None,
    }

    Devuelve None si <condición>.

Invariantes:
    - <invariante 1>
"""

import logging
# import <stdlib_modules>

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_<NOMBRE>_TIMEOUT_S = 15


# ===========================================================================
# Fuente 1: <nombre de fuente>
# ===========================================================================

def _run_<fuente1>() -> dict | None:
    """<Descripción de qué consulta y qué devuelve.>"""
    try:
        # TODO: implementar recogida de métricas

        return {
            "<campo_1>": <valor>,
            "<campo_2>": None,  # no disponible vía <fuente1>
        }
    except <ExcepcionEspecifica> as exc:
        log.warning("<fuente1>: <descripción del fallo>: %s", exc)
        return None
    except Exception as exc:
        log.warning("<fuente1>: error inesperado: %s", exc)
        return None


# ===========================================================================
# Fuente 2: <nombre de fuente>  ← eliminar bloque si no hay fallback
# ===========================================================================

def _run_<fuente2>() -> dict | None:
    """<Descripción de qué consulta y qué devuelve.>"""
    try:
        # TODO: implementar recogida de métricas

        return {
            "<campo_1>": <valor>,
            "<campo_2>": <valor>,
        }
    except Exception as exc:
        log.warning("<fuente2>: error inesperado: %s", exc)
        return None


# ===========================================================================
# Punto de entrada del plugin
# ===========================================================================

def collect() -> dict | None:
    """
    Interfaz pública del plugin.  El collector llama únicamente a esta función.

    Estrategia de fuente con fallback (contrato §1.5):
        1. <fuente1>  → <descripción>
        2. <fuente2>  → si <fuente1> falla
        3. Devuelve None → si ambas fuentes fallan

    Nunca lanza excepciones al caller.
    """
    try:
        log.debug("<nombre>: intentando fuente <fuente1>")
        result = _run_<fuente1>()
        if result is not None:
            log.debug("<nombre>: <fuente1> OK — <campo>=<fmt>", result["<campo>"])
            return result

        log.debug("<nombre>: <fuente1> sin resultado, intentando <fuente2>")
        result = _run_<fuente2>()
        if result is not None:
            log.debug("<nombre>: <fuente2> OK — <campo>=<fmt>", result["<campo>"])
            return result

        log.debug("<nombre>: ambas fuentes sin resultado (<motivo probable>)")
        return None

    except Exception as exc:  # noqa: BLE001
        log.exception("<nombre>: excepción no esperada en collect(): %s", exc)
        return None
```
