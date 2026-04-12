"""
Plugin: boot_time
Fuente principal : Event Log — Event ID 100, canal Diagnostics-Performance/Operational
                   (Get-WinEvent vía subprocess PowerShell)
Fallback         : WMI — Win32_OperatingSystem.LastBootUpTime
                   (Get-WmiObject vía subprocess PowerShell)
Privilegios      : Administrador local
Plataforma       : Solo Windows

Contrato de retorno (ehukene_contratos.md §1.5 — boot_time, v1.2):

    {
        "last_boot_time":        str,        # ISO 8601 hora local, nunca None
        "boot_duration_seconds": int | None, # None si el Event Log no está disponible
    }

    Devuelve None solo si WMI también falla (situación excepcional).

Invariantes:
    - last_boot_time es siempre una cadena ISO 8601 válida: "YYYY-MM-DDTHH:MM:SS".
    - boot_duration_seconds, si presente, es > 0.
    - El plugin nunca devuelve None completo: si WMI está disponible, devuelve
      el dict con al menos last_boot_time.

Estrategia de fuentes:
    _run_event_log() es la fuente primaria. Devuelve ambos campos extrayendo
    BootStartTime y BootTime del Event ID 100. Si falla o el canal no está
    disponible, _run_wmi() proporciona last_boot_time desde
    Win32_OperatingSystem.LastBootUpTime, con boot_duration_seconds=None.

    La correlación entre fuentes no es necesaria: cuando _run_event_log()
    tiene éxito, ambos campos proceden del mismo evento y están
    garantizadamente alineados.
"""

import logging
import subprocess
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_EVENT_LOG_TIMEOUT_S   = 15    # timeout para Get-WinEvent
_WMI_TIMEOUT_S         = 15    # timeout para Get-WmiObject
_BOOT_START_CORR_MAX_S = 300   # ventana de correlación: 5 minutos


# ===========================================================================
# Fuente 1: Event Log — Event ID 100 Diagnostics-Performance
# ===========================================================================

def _run_event_log() -> dict | None:
    """
    Consulta el Event ID 100 del canal
    Microsoft-Windows-Diagnostics-Performance/Operational vía PowerShell.

    Extrae BootStartTime (timestamp UTC del inicio del arranque) y BootTime
    (duración total en ms). Convierte BootStartTime a hora local para cumplir
    el contrato y BootTime a segundos enteros.

    Devuelve el dict completo o None si el canal no existe, no tiene eventos
    ID 100, o el script PowerShell falla.
    """
    ps_script = r"""
$ErrorActionPreference = 'SilentlyContinue'

try {
    $event = Get-WinEvent -LogName 'Microsoft-Windows-Diagnostics-Performance/Operational' `
                          -MaxEvents 50 -ErrorAction Stop |
             Where-Object { $_.Id -eq 100 } |
             Select-Object -First 1

    if (-not $event) {
        Write-Output 'NO_EVENT'
        exit 0
    }

    $xml  = [xml]$event.ToXml()
    $data = @{}
    foreach ($node in $xml.Event.EventData.Data) {
        $data[$node.Name] = $node.'#text'
    }

    $bootStartTime = $data['BootStartTime']
    $bootTime      = $data['BootTime']

    if (-not $bootStartTime -or -not $bootTime) {
        Write-Output 'PARSE_FAILED'
        exit 0
    }

    Write-Output "BOOT_START=$bootStartTime"
    Write-Output "BOOT_TIME_MS=$bootTime"
} catch {
    Write-Output "EVENT_LOG_ERROR=$($_.Exception.Message)"
    exit 0
}
"""

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            timeout=_EVENT_LOG_TIMEOUT_S,
        )
    except FileNotFoundError:
        log.debug("event_log: PowerShell no encontrado en PATH")
        return None
    except subprocess.TimeoutExpired:
        log.warning("event_log: Get-WinEvent excedió el timeout de %ds", _EVENT_LOG_TIMEOUT_S)
        return None
    except Exception as exc:
        log.warning("event_log: error inesperado ejecutando PowerShell: %s", exc)
        return None

    output = result.stdout.decode("utf-8", errors="replace")
    log.debug("event_log: PowerShell output: %s", output.strip())

    if "NO_EVENT" in output:
        log.debug("event_log: canal disponible pero sin eventos ID 100")
        return None

    if "PARSE_FAILED" in output:
        log.warning("event_log: BootStartTime o BootTime ausentes en el XML del evento")
        return None

    if "EVENT_LOG_ERROR=" in output:
        for line in output.splitlines():
            if line.startswith("EVENT_LOG_ERROR="):
                log.warning("event_log: error al consultar el Event Log: %s", line.split("=", 1)[1])
        return None

    # ── Parsear valores ───────────────────────────────────────────────────────
    values = {}
    for line in output.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip()

    boot_start_raw = values.get("BOOT_START", "")
    boot_time_ms_raw = values.get("BOOT_TIME_MS", "")

    if not boot_start_raw or not boot_time_ms_raw:
        log.warning("event_log: no se pudieron extraer BOOT_START o BOOT_TIME_MS del output")
        return None

    # ── Convertir BootStartTime UTC → hora local ──────────────────────────────
    # El campo viene en formato ISO 8601 UTC con nanosegundos:
    # "2026-03-28T07:11:38.588792900Z"
    # datetime.fromisoformat() en Python 3.11+ acepta el sufijo Z; en versiones
    # anteriores hay que normalizarlo a +00:00.
    try:
        boot_start_normalized = boot_start_raw.rstrip("Z").split(".")[0]  # "2026-03-28T07:11:38"
        boot_dt_utc = datetime.strptime(boot_start_normalized, "%Y-%m-%dT%H:%M:%S")
        boot_dt_utc = boot_dt_utc.replace(tzinfo=timezone.utc)
        boot_dt_local = boot_dt_utc.astimezone(tz=None).replace(tzinfo=None)
        last_boot_time = boot_dt_local.isoformat(timespec="seconds")
    except (ValueError, OverflowError) as exc:
        log.warning("event_log: no se pudo parsear BootStartTime '%s': %s", boot_start_raw, exc)
        return None

    # ── Convertir BootTime ms → segundos enteros ──────────────────────────────
    try:
        boot_time_ms = int(boot_time_ms_raw)
    except ValueError as exc:
        log.warning("event_log: BootTime no es un entero válido ('%s'): %s", boot_time_ms_raw, exc)
        return None

    if boot_time_ms <= 0:
        log.warning("event_log: BootTime = %d ms, valor no válido", boot_time_ms)
        return None

    # Invariante: boot_duration_seconds > 0. Si ms < 1000, max garantiza >= 1.
    boot_duration_seconds = max(1, int(boot_time_ms / 1000))

    return {
        "last_boot_time":        last_boot_time,
        "boot_duration_seconds": boot_duration_seconds,
    }


# ===========================================================================
# Fuente 2: WMI — Win32_OperatingSystem (fallback)
# ===========================================================================

def _run_wmi() -> dict | None:
    """
    Consulta Win32_OperatingSystem.LastBootUpTime vía PowerShell.

    Proporciona únicamente last_boot_time; boot_duration_seconds queda a None
    porque WMI no expone la duración del arranque.

    El timestamp WMI tiene formato "20260328071138.000000+060" (hora local con
    offset en minutos). Se extrae la parte datetime y se descarta el offset:
    el resultado ya es hora local, que es lo que requiere el contrato.

    Devuelve el dict completo (con boot_duration_seconds=None) o None si WMI
    falla.
    """
    ps_script = r"""
$ErrorActionPreference = 'SilentlyContinue'

try {
    $os = Get-WmiObject -Class Win32_OperatingSystem -Namespace root\cimv2 -ErrorAction Stop |
          Select-Object -First 1

    if (-not $os) {
        Write-Output 'WMI_FAILED'
        exit 0
    }

    Write-Output "LAST_BOOT=$($os.LastBootUpTime)"
} catch {
    Write-Output "WMI_ERROR=$($_.Exception.Message)"
    exit 0
}
"""

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            timeout=_WMI_TIMEOUT_S,
        )
    except FileNotFoundError:
        log.debug("wmi: PowerShell no encontrado en PATH")
        return None
    except subprocess.TimeoutExpired:
        log.warning("wmi: Get-WmiObject excedió el timeout de %ds", _WMI_TIMEOUT_S)
        return None
    except Exception as exc:
        log.warning("wmi: error inesperado ejecutando PowerShell: %s", exc)
        return None

    output = result.stdout.decode("utf-8", errors="replace")
    log.debug("wmi: PowerShell output: %s", output.strip())

    if "WMI_FAILED" in output:
        log.warning("wmi: Win32_OperatingSystem no devolvió instancias")
        return None

    if "WMI_ERROR=" in output:
        for line in output.splitlines():
            if line.startswith("WMI_ERROR="):
                log.warning("wmi: error al consultar WMI: %s", line.split("=", 1)[1])
        return None

    # ── Parsear LAST_BOOT ─────────────────────────────────────────────────────
    values = {}
    for line in output.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip()

    last_boot_raw = values.get("LAST_BOOT", "")
    if not last_boot_raw:
        log.warning("wmi: LAST_BOOT ausente en el output de PowerShell")
        return None

    # Formato WMI: "20260328071138.000000+060"
    # Los primeros 14 caracteres son la parte datetime: "YYYYMMDDHHMMSS"
    try:
        boot_dt = datetime.strptime(last_boot_raw[:14], "%Y%m%d%H%M%S")
        last_boot_time = boot_dt.isoformat(timespec="seconds")
    except (ValueError, IndexError) as exc:
        log.warning("wmi: no se pudo parsear LastBootUpTime '%s': %s", last_boot_raw, exc)
        return None

    return {
        "last_boot_time":        last_boot_time,
        "boot_duration_seconds": None,   # no disponible vía WMI
    }


# ===========================================================================
# Punto de entrada del plugin
# ===========================================================================

def collect() -> dict | None:
    """
    Interfaz pública del plugin. El collector llama únicamente a esta función.

    Estrategia de fuente con fallback (contrato §1.5):
        1. Event Log (Event ID 100) → last_boot_time + boot_duration_seconds
        2. WMI (Win32_OperatingSystem) → last_boot_time solo, si Event Log falla
        3. Devuelve None → solo si WMI también falla (situación excepcional)

    Nunca lanza excepciones al caller.
    """
    try:
        log.debug("boot_time: intentando fuente event_log")
        result = _run_event_log()
        if result is not None:
            log.debug(
                "boot_time: event_log OK — last_boot=%s duration=%ss",
                result["last_boot_time"],
                result["boot_duration_seconds"],
            )
            return result

        log.debug("boot_time: event_log sin resultado, intentando WMI")
        result = _run_wmi()
        if result is not None:
            log.debug(
                "boot_time: WMI OK — last_boot=%s (duration no disponible)",
                result["last_boot_time"],
            )
            return result

        log.warning("boot_time: ambas fuentes fallaron")
        return None

    except Exception as exc:  # noqa: BLE001
        log.exception("boot_time: excepción no esperada en collect(): %s", exc)
        return None
