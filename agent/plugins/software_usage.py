"""
Plugin: software_usage
Fuente instalación (primaria) : Get-Package vía PowerShell — busca por nombre lógico
Fuente instalación (fallback)  : Registro de Windows (HKLM) — rutas configuradas en targets
Fuente uso                     : Prefetch de Windows (C:\\Windows\\Prefetch\\)
Privilegios                    : Administrador local (Prefetch y Get-Package requieren permisos elevados)
Plataforma                     : Solo Windows

Contrato de retorno (ehukene_contratos.md §1.5 — software_usage, v1.2):

    list[dict]  — una entrada por target definido en software_targets.json

    Cada dict:
    {
        "name":                  str,
        "installed":             bool,
        "version":               str | None,
        "last_execution":        str | None,   # ISO 8601 hora local
        "executions_last_30d":   int,
        "executions_last_60d":   int,
        "executions_last_90d":   int,
    }

    Devuelve [] si software_targets.json no existe, está vacío o está malformado.
    Devuelve None solo ante un fallo interno inesperado del propio plugin.

Invariantes:
    - Si installed es False: version es None y todos los conteos son 0.
    - executions_last_30d >= 0, executions_last_60d >= 0, executions_last_90d >= 0 siempre.
    - executions_last_30d <= executions_last_60d <= executions_last_90d siempre.
    - last_execution, si presente, es ISO 8601 hora local sin zona: "YYYY-MM-DDTHH:MM:SS".
    - La lista tiene exactamente un dict por cada target válido en software_targets.json.
    - [] es retorno válido (sin targets configurados). None indica fallo interno del plugin.
"""

import glob
import json
import logging
import os
import re
import subprocess
import winreg
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_PREFETCH_DIR          = r"C:\Windows\Prefetch"
_CONFIG_PATH           = Path(__file__).parent.parent / "config" / "software_targets.json"
_WINDOW_30_DAYS        = 30
_WINDOW_60_DAYS        = 60
_WINDOW_90_DAYS        = 90
_GET_PACKAGE_TIMEOUT_S = 15
_REGISTRY_HIVES        = [winreg.HKEY_LOCAL_MACHINE]
_SEMVER_RE             = re.compile(r"^\d+\.\d+\.\d+$")


# ===========================================================================
# Bloque config: carga y validación de software_targets.json
# ===========================================================================

def _parse_version_tuple(version_str: str) -> tuple:
    """
    Convierte una cadena de versión en una tupla de enteros para comparación.

    Acepta formatos con cualquier número de componentes numéricos separados
    por puntos (ej. "24.0.0", "26.1.21367"). Los componentes no numéricos
    se tratan como 0.

    Ejemplos:
        "24.0.0"     → (24, 0, 0)
        "26.1.21367" → (26, 1, 21367)
        ""           → (0,)
    """
    if not version_str:
        return (0,)
    parts = []
    for part in version_str.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _load_targets() -> list[dict]:
    """
    Carga y valida software_targets.json.

    Campos obligatorios del fichero: 'version' (semver) y 'targets' (lista).
    Campos opcionales: 'last_updated', 'description', 'maintainer'.

    Campos obligatorios por target: 'name', 'registry_keys', 'prefetch_pattern'.
    Campo opcional por target: 'package_name' (activa Get-Package como fuente primaria).

    Devuelve [] en los siguientes casos:
        - El fichero no existe.
        - El JSON está malformado.
        - Falta 'version' o 'targets'.
        - 'version' no tiene formato semver (MAJOR.MINOR.PATCH).
    Los targets individuales inválidos se ignoran sin invalidar el resto.
    Nunca lanza excepciones al caller.
    """
    try:
        if not _CONFIG_PATH.exists():
            log.debug(
                "software_usage: software_targets.json no encontrado en %s",
                _CONFIG_PATH,
            )
            return []

        with _CONFIG_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)

        # ── Validación de campos obligatorios del fichero ─────────────────────
        version = data.get("version")
        if not version:
            log.warning(
                "software_usage: software_targets.json — falta el campo obligatorio 'version'"
            )
            return []

        if not _SEMVER_RE.match(str(version)):
            log.warning(
                "software_usage: software_targets.json — 'version' no tiene formato semver "
                "(esperado MAJOR.MINOR.PATCH, recibido: %r)",
                version,
            )
            return []

        targets_raw = data.get("targets")
        if targets_raw is None:
            log.warning(
                "software_usage: software_targets.json — falta el campo obligatorio 'targets'"
            )
            return []

        if not isinstance(targets_raw, list):
            log.warning(
                "software_usage: software_targets.json — 'targets' no es una lista"
            )
            return []

        # ── Log de metadatos opcionales ───────────────────────────────────────
        log.debug(
            "software_usage: targets v%s cargados (last_updated=%s, maintainer=%s)",
            version,
            data.get("last_updated", "—"),
            data.get("maintainer", "—"),
        )

        # ── Validación de targets individuales ────────────────────────────────
        valid = []
        for t in targets_raw:
            if not isinstance(t, dict):
                log.warning("software_usage: target ignorado (no es un objeto): %r", t)
                continue
            missing = [
                f for f in ("name", "registry_keys", "prefetch_pattern")
                if not t.get(f)
            ]
            if missing:
                log.warning(
                    "software_usage: target '%s' ignorado — faltan campos obligatorios: %s",
                    t.get("name", "<sin nombre>"),
                    ", ".join(missing),
                )
                continue
            valid.append(t)

        log.debug(
            "software_usage: %d de %d target(s) válidos",
            len(valid),
            len(targets_raw),
        )
        return valid

    except json.JSONDecodeError as exc:
        log.warning("software_usage: software_targets.json malformado: %s", exc)
        return []
    except Exception as exc:
        log.warning(
            "software_usage: error inesperado al leer software_targets.json: %s", exc
        )
        return []


# ===========================================================================
# Fuente 1: Get-Package vía PowerShell (fuente primaria de instalación)
# ===========================================================================

# ── Script PowerShell embebido ────────────────────────────────────────────────
#
# Salidas posibles:
#   JSON con uno o varios objetos {Name, Version}  → software encontrado
#   NOT_FOUND                                       → Get-Package sin resultados
#   GET_PACKAGE_ERROR=<mensaje>                     → error en el cmdlet
#
_PS_GET_PACKAGE = """\
$pattern = '{pattern}'
try {{
    $pkgs = @(Get-Package -Name $pattern -ErrorAction Stop |
              Select-Object Name, Version)
    if ($pkgs.Count -eq 0) {{
        Write-Output 'NOT_FOUND'
    }} else {{
        $pkgs | ConvertTo-Json -Compress
    }}
}} catch {{
    Write-Output "GET_PACKAGE_ERROR=$($_.Exception.Message)"
}}
"""


def _check_get_package(target: dict) -> tuple[bool, str | None]:
    """
    Consulta Get-Package para determinar si el software está instalado.

    Si hay múltiples coincidencias selecciona la de versión más alta.
    Devuelve (True, version) si está instalado, (False, None) en cualquier
    otro caso (no encontrado, error, timeout).
    Nunca lanza excepciones al caller.
    """
    pattern = target["package_name"]
    script  = _PS_GET_PACKAGE.format(pattern=pattern)

    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=_GET_PACKAGE_TIMEOUT_S,
        )
        output = result.stdout.strip()

        if not output:
            log.warning(
                "get_package: salida vacía para '%s' (stderr: %s)",
                target["name"],
                result.stderr.strip(),
            )
            return False, None

        if output == "NOT_FOUND":
            log.debug("get_package: '%s' no encontrado", target["name"])
            return False, None

        if output.startswith("GET_PACKAGE_ERROR="):
            log.warning(
                "get_package: error al consultar '%s': %s",
                target["name"],
                output[len("GET_PACKAGE_ERROR="):],
            )
            return False, None

        # ── Parseo del JSON devuelto por ConvertTo-Json ───────────────────────
        # PowerShell devuelve un objeto {} si hay un resultado y una lista []
        # si hay varios. Se normaliza siempre a lista.
        raw = json.loads(output)
        packages = raw if isinstance(raw, list) else [raw]

        if not packages:
            log.debug("get_package: '%s' no encontrado", target["name"])
            return False, None

        # ── Selección de la versión más alta ante múltiples resultados ─────────
        best = max(packages, key=lambda p: _parse_version_tuple(p.get("Version", "")))
        version = str(best.get("Version", "") or "").strip() or None

        log.debug(
            "get_package: '%s' encontrado — versión: %s (%d resultado(s))",
            target["name"],
            version,
            len(packages),
        )
        return True, version

    except FileNotFoundError:
        log.debug("get_package: PowerShell no encontrado en PATH")
        return False, None
    except subprocess.TimeoutExpired:
        log.warning(
            "get_package: Get-Package excedió el timeout de %ds para '%s'",
            _GET_PACKAGE_TIMEOUT_S,
            target["name"],
        )
        return False, None
    except json.JSONDecodeError as exc:
        log.warning(
            "get_package: no se pudo parsear la salida de Get-Package para '%s': %s",
            target["name"],
            exc,
        )
        return False, None
    except Exception as exc:
        log.warning(
            "get_package: error inesperado para '%s': %s",
            target["name"],
            exc,
        )
        return False, None


# ===========================================================================
# Fuente 2: Registro de Windows (fallback de instalación)
# ===========================================================================

def _check_registry(target: dict) -> tuple[bool, str | None]:
    """
    Consulta el registro de Windows para determinar si el software está instalado
    y qué versión tiene.

    Prueba cada ruta en target['registry_keys'] en orden y devuelve al primer éxito.
    Devuelve (True, version) si está instalado, (False, None) si no.
    Nunca lanza excepciones al caller.
    """
    version_value = target.get("registry_version_value", "DisplayVersion")

    for hive in _REGISTRY_HIVES:
        for key_path in target["registry_keys"]:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    version = winreg.QueryValueEx(key, version_value)[0]
                    version = str(version).strip() or None
                    log.debug(
                        "registro: '%s' encontrado en %s — versión: %s",
                        target["name"],
                        key_path,
                        version,
                    )
                    return True, version
            except FileNotFoundError:
                continue
            except OSError as exc:
                log.warning(
                    "registro: error al leer '%s' en %s: %s",
                    target["name"],
                    key_path,
                    exc,
                )
                continue

    log.debug(
        "registro: '%s' no encontrado en ninguna ruta configurada",
        target["name"],
    )
    return False, None


# ===========================================================================
# Fuente 3: Prefetch — last_execution y conteos de ejecuciones
# ===========================================================================

def _check_prefetch(target: dict) -> tuple[str | None, int, int, int]:
    """
    Busca ficheros .pf en C:\\Windows\\Prefetch que coincidan con el patrón
    del target y calcula last_execution y los conteos a 30, 60 y 90 días.

    Windows puede generar hasta 8 ficheros .pf por ejecutable. Se usan todos.
    La fecha de modificación (mtime) de cada .pf corresponde a la última
    ejecución registrada en ese fichero.

    Devuelve (last_execution_iso, count_30d, count_60d, count_90d).
    Devuelve (None, 0, 0, 0) si no hay ficheros o si Prefetch no está disponible.
    Nunca lanza excepciones al caller.
    """
    try:
        pattern  = os.path.join(_PREFETCH_DIR, target["prefetch_pattern"])
        pf_files = glob.glob(pattern)

        if not pf_files:
            log.debug("prefetch: sin ficheros .pf para '%s'", target["name"])
            return None, 0, 0, 0

        now       = datetime.now()
        cutoff_30 = now - timedelta(days=_WINDOW_30_DAYS)
        cutoff_60 = now - timedelta(days=_WINDOW_60_DAYS)
        cutoff_90 = now - timedelta(days=_WINDOW_90_DAYS)

        mtimes: list[datetime] = []
        for pf in pf_files:
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(pf))
                mtimes.append(mtime)
            except OSError as exc:
                log.warning("prefetch: no se pudo leer mtime de %s: %s", pf, exc)
                continue

        if not mtimes:
            return None, 0, 0, 0

        # last_execution = mtime más reciente de todos los .pf del target
        last_dt  = max(mtimes)
        last_iso = last_dt.isoformat(timespec="seconds")

        # Conteos: cuántos .pf tienen mtime dentro de cada ventana temporal.
        # Cada fichero .pf representa una sesión de ejecución distinta del
        # ejecutable, por lo que contar ficheros dentro de la ventana es una
        # aproximación razonable del número de ejecuciones en ese periodo.
        count_30 = sum(1 for t in mtimes if t >= cutoff_30)
        count_60 = sum(1 for t in mtimes if t >= cutoff_60)
        count_90 = sum(1 for t in mtimes if t >= cutoff_90)

        log.debug(
            "prefetch: '%s' — last=%s  30d=%d  60d=%d  90d=%d",
            target["name"],
            last_iso,
            count_30,
            count_60,
            count_90,
        )
        return last_iso, count_30, count_60, count_90

    except PermissionError as exc:
        log.warning("prefetch: sin permisos para leer %s: %s", _PREFETCH_DIR, exc)
        return None, 0, 0, 0
    except Exception as exc:
        log.warning(
            "prefetch: error inesperado para '%s': %s", target["name"], exc
        )
        return None, 0, 0, 0


# ===========================================================================
# Bloque auxiliar: recopilación por target
# ===========================================================================

def _collect_one(target: dict) -> dict:
    """
    Orquesta las tres fuentes para un único target y construye su dict de retorno.

    Estrategia de instalación:
        1. Get-Package (si 'package_name' está definido en el target)
        2. winreg     (siempre como fallback, o como fuente única si no hay package_name)

    Si el software no está instalado según ambas fuentes, los campos de uso
    se fijan a sus valores nulos sin consultar Prefetch. Si está instalado
    pero Prefetch falla, se devuelven los conteos a 0 y last_execution a None.

    Nunca lanza excepciones al caller. Siempre devuelve un dict completo.
    """
    try:
        installed, version = False, None

        # ── Fuente 1: Get-Package (fuente primaria, si está configurada) ───────
        if target.get("package_name"):
            log.debug(
                "software_usage: '%s' — intentando Get-Package",
                target["name"],
            )
            installed, version = _check_get_package(target)

            if not installed:
                log.debug(
                    "software_usage: '%s' — Get-Package sin resultado, intentando registro",
                    target["name"],
                )

        # ── Fuente 2: winreg (fallback o fuente única sin package_name) ────────
        if not installed:
            installed, version = _check_registry(target)

        # ── Software no instalado: devolver dict nulo sin consultar Prefetch ───
        if not installed:
            log.debug("software_usage: '%s' no instalado", target["name"])
            return {
                "name":                target["name"],
                "installed":           False,
                "version":             None,
                "last_execution":      None,
                "executions_last_30d": 0,
                "executions_last_60d": 0,
                "executions_last_90d": 0,
            }

        # ── Fuente 3: Prefetch (uso) ───────────────────────────────────────────
        last_exec, cnt_30, cnt_60, cnt_90 = _check_prefetch(target)

        return {
            "name":                target["name"],
            "installed":           True,
            "version":             version,
            "last_execution":      last_exec,
            "executions_last_30d": cnt_30,
            "executions_last_60d": cnt_60,
            "executions_last_90d": cnt_90,
        }

    except Exception as exc:
        # Degradación controlada: el target falla pero no aborta el resto.
        log.warning(
            "software_usage: error inesperado procesando '%s': %s",
            target.get("name"),
            exc,
        )
        return {
            "name":                target.get("name", "unknown"),
            "installed":           False,
            "version":             None,
            "last_execution":      None,
            "executions_last_30d": 0,
            "executions_last_60d": 0,
            "executions_last_90d": 0,
        }


# ===========================================================================
# Punto de entrada del plugin
# ===========================================================================

def collect() -> list | None:
    """
    Interfaz pública del plugin. El collector llama únicamente a esta función.

    Carga los targets desde agent/config/software_targets.json y recopila
    métricas de instalación y uso para cada uno de forma independiente.

    Devuelve [] si no hay targets configurados o el fichero no existe/es inválido.
    Devuelve None solo ante un fallo interno inesperado del propio plugin.

    Nunca lanza excepciones al caller.
    """
    try:
        targets = _load_targets()

        if not targets:
            log.debug(
                "software_usage: sin targets configurados, devolviendo lista vacía"
            )
            return []

        results = [_collect_one(t) for t in targets]

        log.debug(
            "software_usage: %d target(s) procesados — %d instalados",
            len(results),
            sum(1 for r in results if r["installed"]),
        )
        return results

    except Exception as exc:  # noqa: BLE001
        log.exception(
            "software_usage: excepción no esperada en collect(): %s", exc
        )
        return None