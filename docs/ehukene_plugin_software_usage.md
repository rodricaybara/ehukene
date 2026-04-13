# EHUkene — Plugin `software_usage`
## Documentación técnica

**Versión:** 1.3.1
**Estado:** Implementado
**Fecha:** 2026-04-13
**Fichero:** `agent/plugins/software_usage.py`
**Relacionado con:** Contratos v1.2 · Estándar de plugins v1.0

---

## Índice

1. [Propósito](#1-propósito)
2. [Requisitos](#2-requisitos)
3. [Fuentes de datos](#3-fuentes-de-datos)
4. [Configuración de targets](#4-configuración-de-targets)
5. [Contrato de retorno](#5-contrato-de-retorno)
6. [Flujo de ejecución](#6-flujo-de-ejecución)
7. [Comportamiento ante fallos](#7-comportamiento-ante-fallos)
8. [Limitaciones conocidas](#8-limitaciones-conocidas)
9. [Estructura interna del módulo](#9-estructura-interna-del-módulo)
10. [Logging](#10-logging)

---

## 1. Propósito

El plugin `software_usage` recopila métricas de instalación y uso real de uno o varios programas configurados. Para cada programa informa de si está instalado, su versión y la frecuencia de uso en ventanas de 30, 60 y 90 días.

El caso de uso principal en la POC es la optimización de licencias de Adobe Acrobat Pro: detectar equipos con la aplicación instalada pero sin uso real para liberar licencias innecesarias.

---

## 2. Requisitos

| Requisito | Valor |
|---|---|
| Plataforma | Solo Windows |
| Privilegios | Administrador local |
| Dependencias externas | Ninguna (solo biblioteca estándar de Python) |
| Módulos Python | `glob`, `json`, `logging`, `os`, `re`, `subprocess`, `sys`, `winreg`, `datetime`, `pathlib` |

> Los privilegios de administrador son necesarios para `Get-Package` y para acceder a `C:\Windows\Prefetch\`. Sin ellos, el plugin cae al fallback de registro para la instalación y devuelve conteos de uso a `0`.

---

## 3. Fuentes de datos

El plugin usa tres fuentes con responsabilidades distintas.

### Fuente 1 — `Get-Package` vía PowerShell (fuente primaria de instalación)

**Qué aporta:** `installed` y `version`.

**Cuándo se activa:** cuando el target declara el campo `package_name` en `software_targets.json`. Si el campo no está presente, el plugin pasa directamente al registro.

Windows expone los paquetes instalados a través de la API de PackageManagement (`Get-Package`). La búsqueda se realiza por nombre lógico mediante un patrón glob, lo que la hace resistente a cambios de GUID o de ruta de instalación.

El script PowerShell embebido ejecuta:

```powershell
Get-Package -Name "<pattern>" | Select-Object Name, Version | ConvertTo-Json
```

Si hay múltiples coincidencias, el plugin selecciona la de **versión más alta**. La comparación de versiones se realiza componente a componente sobre los segmentos numéricos de la cadena, sin dependencias externas.

**Privilegios necesarios:** administrador local en la mayoría de configuraciones.

**Señales de salida del script:**

| Salida | Significado |
|---|---|
| JSON `{Name, Version}` o `[{…}]` | Software encontrado |
| `NOT_FOUND` | `Get-Package` no devolvió resultados |
| `GET_PACKAGE_ERROR=<msg>` | Error en la ejecución del cmdlet |

### Fuente 2 — Registro de Windows (fallback de instalación)

**Qué aporta:** `installed` y `version`.

**Cuándo se activa:** cuando `Get-Package` no está configurado para el target, o cuando `Get-Package` falla o no encuentra el software.

El plugin prueba cada ruta de `registry_keys` en orden bajo `HKEY_LOCAL_MACHINE` y devuelve al primer éxito. Esto permite cubrir instalaciones en distintas ubicaciones del registro (por ejemplo, aplicaciones 32-bit en sistemas 64-bit mediante la ruta `WOW6432Node`).

**Privilegios necesarios:** usuario estándar.

### Fuente 3 — Prefetch de Windows

**Qué aporta:** `last_execution`, `executions_last_30d`, `executions_last_60d`, `executions_last_90d`.

**Cuándo se activa:** siempre que el software haya sido detectado como instalado por alguna de las fuentes anteriores.

Windows genera ficheros `.pf` al ejecutar una aplicación. Cada fichero recibe en su nombre un hash derivado de la ruta del ejecutable. El sistema puede mantener hasta 8 ficheros `.pf` por ejecutable, rotándolos cuando se supera ese límite.

La fecha de modificación (`mtime`) de cada fichero `.pf` corresponde al momento de la última ejecución registrada en él. El plugin recoge los `mtime` de todos los ficheros `.pf` del target y calcula:

- `last_execution` — el `mtime` más reciente entre todos los ficheros encontrados.
- `executions_last_Nd` — número de ficheros `.pf` cuyo `mtime` cae dentro de la ventana de N días.

**Privilegios necesarios:** administrador local.

---

## 4. Configuración de targets

La lista de programas a monitorizar se define en `agent/config/software_targets.json`. El plugin lee este fichero en cada ejecución. Añadir o quitar un programa solo requiere editar el JSON y actualizar el fichero en los endpoints vía Ivanti, sin redesplegar el ejecutable.

### Ubicación

```
agent/
└── config/
    └── software_targets.json
```

### Estructura del fichero

```json
{
  "version": "1.1.0",
  "last_updated": "2026-04-09",
  "description": "Lista de software a monitorizar - UPV/EHU",
  "maintainer": "Servicio de Informática",
  "targets": [
    {
      "name": "adobe_acrobat_pro",
      "display_name": "Adobe Acrobat Pro",
      "package_name": "*Adobe Acrobat*",
      "registry_keys": [
        "SOFTWARE\\Adobe\\Adobe Acrobat\\DC\\Installer",
        "SOFTWARE\\WOW6432Node\\Adobe\\Adobe Acrobat\\DC\\Installer"
      ],
      "registry_version_value": "ProductVersion",
      "prefetch_pattern": "ACROBAT.EXE-*.pf"
    }
  ]
}
```

### Campos de cabecera del fichero

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `version` | `string` | **Sí** | Versión semántica del fichero. Formato obligatorio: `MAJOR.MINOR.PATCH`. |
| `targets` | `array` | **Sí** | Lista de programas a monitorizar. |
| `last_updated` | `string` | No | Fecha de la última actualización. Formato recomendado: `YYYY-MM-DD`. |
| `description` | `string` | No | Descripción del fichero. Solo informativo. |
| `maintainer` | `string` | No | Responsable del mantenimiento. Solo informativo. |

### Campos por target

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `name` | `string` | **Sí** | Identificador estable del programa. Se usa como clave en el payload. Sin espacios. |
| `registry_keys` | `string[]` | **Sí** | Rutas del registro a probar en orden como fallback. Se usa la primera que exista. |
| `prefetch_pattern` | `string` | **Sí** | Patrón glob para localizar los ficheros `.pf` en `C:\Windows\Prefetch\`. |
| `package_name` | `string` | No | Patrón glob para `Get-Package`. Si está presente, activa la fuente primaria de instalación. |
| `registry_version_value` | `string` | No | Nombre del valor del registro que contiene la versión. Por defecto: `"DisplayVersion"`. |
| `display_name` | `string` | No | Nombre legible. Solo informativo, no sale en el payload. |

> Si `package_name` no está definido en un target, el plugin usa el registro directamente como única fuente de instalación. Esto permite convivir en el mismo JSON targets con distintas estrategias de detección.

### Comportamiento ante fichero inválido

| Situación | Resultado |
|---|---|
| Fichero no existe | `collect()` devuelve `[]` |
| JSON malformado | `collect()` devuelve `[]` |
| Falta campo `version` | `collect()` devuelve `[]` + `WARNING` en log |
| `version` fuera de formato semver | `collect()` devuelve `[]` + `WARNING` en log |
| Falta campo `targets` | `collect()` devuelve `[]` + `WARNING` en log |
| Target sin campos obligatorios | El target se ignora; el resto continúan |

---

## 5. Contrato de retorno

`collect()` devuelve `list[dict] | None`.

Cada elemento de la lista corresponde a un target de `software_targets.json`:

| Campo | Tipo | Nullable | Descripción |
|---|---|---|---|
| `name` | `str` | No | Identificador del programa, tal como figura en `software_targets.json` |
| `installed` | `bool` | No | Si el programa está instalado en el equipo |
| `version` | `str` | Sí | Versión instalada. `None` si no instalado |
| `last_execution` | `str` ISO 8601 | Sí | Último uso detectado vía Prefetch. `None` si no hay datos |
| `executions_last_30d` | `int` | No | Ejecuciones en los últimos 30 días. `0` si no instalado o sin datos |
| `executions_last_60d` | `int` | No | Ejecuciones en los últimos 60 días. `0` si no instalado o sin datos |
| `executions_last_90d` | `int` | No | Ejecuciones en los últimos 90 días. `0` si no instalado o sin datos |

### Invariantes

- Si `installed` es `False`: `version` es `None` y todos los conteos son `0`.
- `executions_last_30d >= 0`, `executions_last_60d >= 0`, `executions_last_90d >= 0` siempre.
- `executions_last_30d <= executions_last_60d <= executions_last_90d` siempre.
- `last_execution`, si presente, es ISO 8601 en hora local sin zona horaria: `"YYYY-MM-DDTHH:MM:SS"`.
- La lista tiene exactamente un dict por cada target válido en `software_targets.json`.

### Valores de retorno especiales

| Valor | Significado |
|---|---|
| `list[dict]` | Ejecución normal. Un dict por target. |
| `[]` | Sin targets configurados, fichero ausente o inválido. No es un error. |
| `None` | Fallo interno inesperado en el propio plugin. |

### Ejemplo de retorno

```json
[
  {
    "name": "adobe_acrobat_pro",
    "installed": true,
    "version": "24.0.0",
    "last_execution": "2026-03-20T10:30:00",
    "executions_last_30d": 3,
    "executions_last_60d": 7,
    "executions_last_90d": 11
  },
  {
    "name": "7zip",
    "installed": false,
    "version": null,
    "last_execution": null,
    "executions_last_30d": 0,
    "executions_last_60d": 0,
    "executions_last_90d": 0
  }
]
```

---

## 6. Flujo de ejecución

```
collect()
    │
    ├── _load_targets()
    │       Verifica existencia del fichero
    │       Valida campos obligatorios: 'version' (semver) y 'targets'
    │       Loguea metadatos opcionales: version, last_updated, maintainer
    │       Filtra targets inválidos (sin campos obligatorios)
    │       Devuelve [] si el fichero falta, es inválido o no hay targets válidos
    │
    └── Para cada target → _collect_one(target)
            │
            ├── ¿Tiene 'package_name'?
            │     Sí → _check_get_package(target)
            │               Ejecuta Get-Package vía PowerShell (timeout 15s)
            │               Parsea JSON de salida
            │               ¿Múltiples resultados? → selecciona versión más alta
            │               Devuelve (True, version) o (False, None)
            │
            ├── ¿installed == False? (Get-Package sin resultado o no configurado)
            │     → _check_registry(target)
            │               Prueba cada registry_key en orden bajo HKLM
            │               Devuelve (True, version) o (False, None)
            │
            ├── ¿installed == False tras ambas fuentes?
            │     → Retorna dict con installed=False, version=None, conteos=0
            │        (sin consultar Prefetch)
            │
            └── installed == True
                    → _check_prefetch(target)
                              Localiza ficheros .pf por patrón glob
                              Lee mtime de cada fichero
                              last_execution = mtime más reciente
                              Calcula conteos 30/60/90d en una sola pasada
                              Devuelve (last_iso, cnt_30, cnt_60, cnt_90)
                    → Retorna dict completo con todos los campos
```

Un fallo en cualquier punto de `_collect_one()` produce un dict degradado con `installed=False` y conteos a `0` para ese target, sin interrumpir el procesamiento del resto.

---

## 7. Comportamiento ante fallos

| Situación | Comportamiento |
|---|---|
| `software_targets.json` no existe | `collect()` devuelve `[]` |
| `software_targets.json` malformado | `collect()` devuelve `[]` |
| Falta `version` o formato semver incorrecto | `collect()` devuelve `[]` + `WARNING` |
| Falta campo `targets` | `collect()` devuelve `[]` + `WARNING` |
| Target sin campos obligatorios | El target se ignora + `WARNING`; el resto continúan |
| PowerShell no encontrado en PATH | Cae a winreg. `DEBUG` en log. |
| `Get-Package` excede timeout (15s) | Cae a winreg. `WARNING` en log. |
| `Get-Package` devuelve error del cmdlet | Cae a winreg. `WARNING` en log. |
| `Get-Package` sin resultados (`NOT_FOUND`) | Cae a winreg. `DEBUG` en log. |
| JSON de `Get-Package` no parseable | Cae a winreg. `WARNING` en log. |
| Clave de registro no encontrada | `installed=False` para ese target. `DEBUG` en log. |
| Error de lectura del registro (permisos, I/O) | `installed=False` + `WARNING` en log. |
| Sin permisos para leer `C:\Windows\Prefetch\` | `last_execution=None`, conteos=`0` + `WARNING` en log. |
| Sin ficheros `.pf` para el patrón del target | `last_execution=None`, conteos=`0`. `DEBUG` en log. |
| Error de lectura de un fichero `.pf` individual | El fichero se omite; el resto se procesan. |
| Excepción inesperada en `_collect_one()` | Dict degradado para ese target + `WARNING` en log. |
| Excepción inesperada en `collect()` | `None` + `EXCEPTION` en log (con traceback). |

---

## 8. Limitaciones conocidas

### Conteo de ejecuciones es una aproximación

Prefetch mantiene como máximo 8 ficheros `.pf` por ejecutable. Si el programa se ha ejecutado más de 8 veces, los ficheros más antiguos son sobreescritos y el conteo real puede ser mayor que el reportado. El dato es útil como indicador de actividad, no como registro exhaustivo.

### Prefetch puede estar desactivado

En algunos entornos Windows (servidores, SSDs con ciertas configuraciones) el servicio de Prefetch está desactivado. En ese caso el directorio `C:\Windows\Prefetch\` existe pero no contiene ficheros `.pf`. El plugin detecta esta situación como "sin datos de uso" y devuelve `last_execution=None` y conteos a `0` sin emitir un error.

### `Get-Package` puede ser lento en el primer arranque

En equipos con muchos paquetes instalados, el primer `Get-Package` de la sesión puede tardar varios segundos mientras Windows inicializa el proveedor de PackageManagement. El timeout de 15 segundos cubre este escenario, pero si un equipo es consistentemente lento en este punto el plugin caerá al fallback de registro.

### Solo se consulta `HKEY_LOCAL_MACHINE` en el fallback de registro

Las instalaciones por usuario (`HKEY_CURRENT_USER`) no se detectan vía winreg. `Get-Package` sí las detecta al consultar el repositorio del sistema. Si un software se instala exclusivamente por usuario y no tiene `package_name` configurado, el plugin lo reportará como no instalado.

### `last_execution` en hora local sin zona horaria

El plugin devuelve el timestamp en hora local del equipo, sin información de zona horaria. La conversión a UTC es responsabilidad del backend al persistir en base de datos.

---

## 9. Estructura interna del módulo

```
software_usage.py
│
├── Imports
├── log = logging.getLogger(__name__)
├── Constantes
│     _PREFETCH_DIR            ruta al directorio de Prefetch
│     _BASE_DIR                ruta base del agente (compatible con PyInstaller)
│     _CONFIG_PATH             ruta a software_targets.json, derivada de _BASE_DIR
│     _WINDOW_30/60/90_DAYS   ventanas temporales de conteo
│     _GET_PACKAGE_TIMEOUT_S  timeout para el subproceso PowerShell
│     _REGISTRY_HIVES         hives del registro a consultar
│     _SEMVER_RE               expresión regular de validación semver
│
├── Bloque config
│     _parse_version_tuple()  convierte cadena de versión a tupla comparable
│     _load_targets()         carga, valida y filtra software_targets.json
│
├── Fuente 1: Get-Package vía PowerShell
│     _PS_GET_PACKAGE         script PowerShell embebido
│     _check_get_package()    instalación y versión por nombre lógico
│
├── Fuente 2: Registro de Windows (fallback)
│     _check_registry()       instalación y versión por ruta de registro
│
├── Fuente 3: Prefetch
│     _check_prefetch()       last_execution y conteos 30/60/90d
│
├── Bloque auxiliar
│     _collect_one()          orquesta las tres fuentes para un target
│
└── Punto de entrada
      collect()               interfaz pública, itera sobre todos los targets
```

---

## 10. Logging

Todos los mensajes usan el logger del módulo (`logging.getLogger(__name__)`). El plugin no configura handlers ni formatters.

| Situación | Nivel | Ejemplo |
|---|---|---|
| `software_targets.json` no encontrado | `DEBUG` | `software_usage: software_targets.json no encontrado en ...` |
| Falta campo obligatorio en el fichero | `WARNING` | `software_usage: software_targets.json — falta el campo obligatorio 'version'` |
| `version` fuera de formato semver | `WARNING` | `software_usage: software_targets.json — 'version' no tiene formato semver ...` |
| Metadatos del fichero cargados | `DEBUG` | `software_usage: targets v1.1.0 cargados (last_updated=2026-04-09, maintainer=Servicio de Informática)` |
| Target ignorado por campos faltantes | `WARNING` | `software_usage: target 'adobe_acrobat_pro' ignorado — faltan campos obligatorios: prefetch_pattern` |
| N targets válidos cargados | `DEBUG` | `software_usage: 2 de 2 target(s) válidos` |
| Intentando Get-Package para un target | `DEBUG` | `software_usage: 'adobe_acrobat_pro' — intentando Get-Package` |
| Get-Package sin resultado, cae a registro | `DEBUG` | `software_usage: 'adobe_acrobat_pro' — Get-Package sin resultado, intentando registro` |
| Get-Package encontró el software | `DEBUG` | `get_package: 'adobe_acrobat_pro' encontrado — versión: 24.0.0 (1 resultado(s))` |
| Get-Package excede timeout | `WARNING` | `get_package: Get-Package excedió el timeout de 15s para 'adobe_acrobat_pro'` |
| Get-Package devuelve error del cmdlet | `WARNING` | `get_package: error al consultar 'adobe_acrobat_pro': ...` |
| Software encontrado vía registro | `DEBUG` | `registro: 'adobe_acrobat_pro' encontrado en SOFTWARE\... — versión: 24.0.0` |
| Software no instalado | `DEBUG` | `software_usage: 'adobe_acrobat_pro' no instalado` |
| Error de lectura del registro | `WARNING` | `registro: error al leer 'adobe_acrobat_pro' en SOFTWARE\...: ...` |
| Sin permisos para leer Prefetch | `WARNING` | `prefetch: sin permisos para leer C:\Windows\Prefetch\: ...` |
| Sin ficheros `.pf` para un target | `DEBUG` | `prefetch: sin ficheros .pf para 'adobe_acrobat_pro'` |
| Éxito de recogida | `DEBUG` | `software_usage: 2 target(s) procesados — 1 instalados` |
| Excepción inesperada en `collect()` | `EXCEPTION` | Incluye traceback completo |