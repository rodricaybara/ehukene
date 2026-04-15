"""
Plugin: health_monitor
Fuente principal : PowerShell nativo de Windows (CIM, WMI, Event Log, Services)
Privilegios      : Administrador local
Plataforma       : Solo Windows

Contrato de retorno (health_monitor_spec_v1.1.md §6, v1.1.0):

    {
        "plugin_version": str,
        "host": str,
        "domain": str,
        "timestamp": str,
        "execution": {
            "duration_ms": int,
            "metrics_attempted": int,
            "metrics_successful": int,
        },
        "metrics": {
            "cpu": dict,
            "memory": dict,
            "disk": dict,
            "events": dict,
            "domain": dict,
            "uptime": dict,
            "boot_time": dict,
            "services": list[dict],
        },
    }

    Devuelve siempre un dict serializable salvo error catastrófico inesperado.

Invariantes:
    - El dict final contiene siempre las 8 métricas esperadas.
    - Si una métrica falla, su bloque incluye status="error" y el resto continúa.
    - boot_time usa hora local sin zona; timestamp global usa UTC con sufijo Z.
"""

import json
import logging
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_PLUGIN_VERSION = "1.1.0"
_METRICS_ATTEMPTED = 8
_METRIC_TIMEOUT_S = 10

if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).parent
else:
    _BASE_DIR = Path(__file__).resolve().parent.parent

_CONFIG_PATH = _BASE_DIR / "config" / "health_monitor_config.json"


# ===========================================================================
# Configuración
# ===========================================================================

def _default_config() -> dict:
    """Devuelve la configuración por defecto definida en la spec v1.1."""
    return {
        "version": "1.1",
        "thresholds": {
            "disk": {"critical": 10, "warning": 20},
            "memory": {"critical": 90, "warning": 80},
            "cpu": {"critical": 90, "warning": 75},
            "events": {
                "critical_count_threshold": 10,
                "error_count_threshold": 50,
            },
            "uptime": {"max_days_without_reboot": 90},
            "boot_time": {"optimal": 60, "normal": 120, "degraded": 180},
        },
        "services": {
            "tier1": [
                "SepMasterService",
                "EventLog",
                "RpcSs",
                "LanmanWorkstation",
            ],
            "tier2": [
                "WinDefend",
                "wuauserv",
                "BITS",
                "Dnscache",
                "W32Time",
                "WinRM",
            ],
            "tier3": ["Spooler"],
        },
        "event_filters": {
            "ignored_providers": [
                "Microsoft-Windows-GroupPolicy",
                "NETLOGON",
                "Microsoft-Windows-Time-Service",
                "Microsoft-Windows-DistributedCOM",
                "Microsoft-Windows-Kernel-General",
                "USER32",
            ],
            "ignored_event_ids": [1014, 10016, 10010, 1001, 10154, 15, 1, 37],
            "ignored_combinations": [
                {"provider": "Microsoft-Windows-DNS-Client", "event_id": 1014},
                {"provider": "Microsoft-Windows-DistributedCOM", "event_id": 10016},
                {"provider": "Microsoft-Windows-DistributedCOM", "event_id": 10010},
            ],
        },
    }


def _merge_defaults(base: dict, override: dict) -> dict:
    """Fusiona un dict de usuario sobre el default sin validación exhaustiva."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_config() -> dict:
    """Carga la configuración o crea el fichero con defaults si no existe."""
    defaults = _default_config()

    if not _CONFIG_PATH.exists():
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CONFIG_PATH.write_text(
                json.dumps(defaults, indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
            log.debug("health_monitor: config creada en %s", _CONFIG_PATH)
        except OSError as exc:
            log.warning("health_monitor: no se pudo crear config por defecto: %s", exc)
        return defaults

    try:
        loaded = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            log.warning("health_monitor: config inválida, usando defaults")
            return defaults
        return _merge_defaults(defaults, loaded)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("health_monitor: no se pudo leer config, usando defaults: %s", exc)
        return defaults


# ===========================================================================
# Utilidades PowerShell
# ===========================================================================

def _run_powershell(script: str, timeout: int = _METRIC_TIMEOUT_S) -> subprocess.CompletedProcess:
    """Ejecuta un script PowerShell y devuelve el CompletedProcess."""
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _load_json_from_ps(script: str, source: str, timeout: int = _METRIC_TIMEOUT_S):
    """Ejecuta PowerShell y parsea una respuesta JSON o un marcador de error."""
    try:
        result = _run_powershell(script, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(f"{source}: PowerShell no encontrado") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{source}: timeout after {timeout} seconds") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"{source}: error ejecutando PowerShell: {exc}") from exc

    output = (result.stdout or "").strip()
    if not output:
        raise RuntimeError(f"{source}: salida vacia")
    if output.startswith("ERROR="):
        raise RuntimeError(output[len("ERROR="):])

    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{source}: salida JSON invalida") from exc


def _error_metric(status: str = "error", **fields) -> dict:
    """Construye un bloque de error serializable."""
    data = dict(fields)
    data["status"] = status
    return data


def _success_metric(value) -> bool:
    """Determina si una métrica cuenta como exitosa para execution metadata."""
    if isinstance(value, list):
        return True
    if isinstance(value, dict):
        return value.get("status") not in {"error"}
    return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_host() -> str:
    return os.environ.get("COMPUTERNAME") or platform.node() or "UNKNOWN"


def _get_domain_name() -> str:
    return os.environ.get("USERDOMAIN") or "WORKGROUP"


# ===========================================================================
# Métrica: CPU
# ===========================================================================

def _get_cpu_metric(config: dict) -> dict:
    try:
        script = r"""
$ErrorActionPreference = 'Stop'
try {
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty LoadPercentage
    @{ load_percentage = [int]$cpu } | ConvertTo-Json -Compress
} catch {
    Write-Output "ERROR=$($_.Exception.Message)"
}
"""
        data = _load_json_from_ps(script, "cpu")
        load_pct = int(data["load_percentage"])
        thresholds = config["thresholds"]["cpu"]
        if load_pct >= thresholds["critical"]:
            status = "critical"
        elif load_pct >= thresholds["warning"]:
            status = "warning"
        else:
            status = "ok"
        return {"load_percentage": load_pct, "status": status}
    except Exception as exc:  # noqa: BLE001
        log.warning("health_monitor: cpu fallo: %s", exc)
        return _error_metric(load_percentage=None, error_msg=str(exc))


# ===========================================================================
# Métrica: Memoria
# ===========================================================================

def _get_memory_metric(config: dict) -> dict:
    try:
        script = r"""
$ErrorActionPreference = 'Stop'
try {
    $os = Get-CimInstance Win32_OperatingSystem
    @{
        total_kb = [int64]$os.TotalVisibleMemorySize
        free_kb = [int64]$os.FreePhysicalMemory
    } | ConvertTo-Json -Compress
} catch {
    Write-Output "ERROR=$($_.Exception.Message)"
}
"""
        data = _load_json_from_ps(script, "memory")
        total_kb = int(data["total_kb"])
        free_kb = int(data["free_kb"])
        used_kb = total_kb - free_kb
        usage_pct = round((used_kb / total_kb) * 100, 2)
        thresholds = config["thresholds"]["memory"]
        if usage_pct >= thresholds["critical"]:
            status = "critical"
        elif usage_pct >= thresholds["warning"]:
            status = "warning"
        else:
            status = "ok"
        return {
            "total_kb": total_kb,
            "free_kb": free_kb,
            "usage_pct": usage_pct,
            "status": status,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("health_monitor: memory fallo: %s", exc)
        return _error_metric(total_kb=None, free_kb=None, usage_pct=None, error_msg=str(exc))


# ===========================================================================
# Métrica: Disco
# ===========================================================================

def _get_disk_metric(config: dict) -> dict:
    try:
        script = r"""
$ErrorActionPreference = 'Stop'
try {
    $systemDrive = 'C:'
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$systemDrive' AND DriveType=3"
    if (-not $disk -and $env:SystemDrive) {
        $systemDrive = $env:SystemDrive
        $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$systemDrive' AND DriveType=3"
    }
    if (-not $disk) {
        Write-Output 'ERROR=System drive not found or not accessible'
        exit 0
    }
    @{
        drive = [string]$disk.DeviceID
        total_gb = [math]::Round([double]$disk.Size / 1GB, 2)
        free_gb = [math]::Round([double]$disk.FreeSpace / 1GB, 2)
        free_pct = [math]::Round(([double]$disk.FreeSpace / [double]$disk.Size) * 100, 2)
    } | ConvertTo-Json -Compress
} catch {
    Write-Output "ERROR=$($_.Exception.Message)"
}
"""
        data = _load_json_from_ps(script, "disk")
        free_pct = float(data["free_pct"])
        thresholds = config["thresholds"]["disk"]
        if free_pct <= thresholds["critical"]:
            status = "critical"
        elif free_pct <= thresholds["warning"]:
            status = "warning"
        else:
            status = "ok"
        return {
            "drive": data["drive"],
            "total_gb": round(float(data["total_gb"]), 2),
            "free_gb": round(float(data["free_gb"]), 2),
            "free_pct": round(free_pct, 2),
            "status": status,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("health_monitor: disk fallo: %s", exc)
        return _error_metric(drive=None, total_gb=None, free_gb=None, free_pct=None, error_msg=str(exc))


# ===========================================================================
# Métrica: Eventos
# ===========================================================================

def _get_events_metric(config: dict) -> dict:
    try:
        filters = json.dumps(config["event_filters"], ensure_ascii=True)
        script = f"""
$ErrorActionPreference = 'Stop'
try {{
    $config = ConvertFrom-Json @'
{filters}
'@

    $events = @(Get-WinEvent -FilterHashtable @{{
        LogName = 'System'
        Level = 1,2
        StartTime = (Get-Date).AddDays(-1)
    }} -ErrorAction Stop)

    $filtered = @()
    $filteredOut = 0

    foreach ($event in $events) {{
        $ignored = $false
        if ($event.ProviderName -in $config.ignored_providers) {{ $ignored = $true }}
        if (-not $ignored -and $event.Id -in $config.ignored_event_ids) {{ $ignored = $true }}
        if (-not $ignored) {{
            foreach ($combo in $config.ignored_combinations) {{
                if ($event.ProviderName -eq $combo.provider -and [int]$event.Id -eq [int]$combo.event_id) {{
                    $ignored = $true
                    break
                }}
            }}
        }}
        if ($ignored) {{
            $filteredOut += 1
        }} else {{
            $filtered += $event
        }}
    }}

    $topSources = @($filtered | Group-Object ProviderName | Sort-Object Count -Descending | Select-Object -First 5 | ForEach-Object {{
        @{{
            provider = [string]$_.Name
            count = [int]$_.Count
        }}
    }})

    $sampleEvents = @($filtered | Sort-Object Level, TimeCreated -Descending | Select-Object -First 5 | ForEach-Object {{
        @{{
            event_id = [int]$_.Id
            provider = [string]$_.ProviderName
            level = switch([int]$_.Level) {{
                1 {{ 'Critical' }}
                2 {{ 'Error' }}
                default {{ 'Unknown' }}
            }}
            time_created = $_.TimeCreated.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        }}
    }})

    @{{
        critical_count = [int]@($filtered | Where-Object {{ $_.Level -eq 1 }}).Count
        error_count = [int]@($filtered | Where-Object {{ $_.Level -eq 2 }}).Count
        filtered_count = [int]$filteredOut
        top_sources = $topSources
        sample_events = $sampleEvents
    }} | ConvertTo-Json -Depth 5 -Compress
}} catch {{
    Write-Output "ERROR=Event log not accessible"
}}
"""
        data = _load_json_from_ps(script, "events")
        critical_count = int(data["critical_count"])
        error_count = int(data["error_count"])
        thresholds = config["thresholds"]["events"]
        if critical_count >= thresholds["critical_count_threshold"]:
            status = "critical"
        elif error_count >= thresholds["error_count_threshold"]:
            status = "warning"
        else:
            status = "ok"
        return {
            "critical_count": critical_count,
            "error_count": error_count,
            "filtered_count": int(data["filtered_count"]),
            "top_sources": data.get("top_sources", []),
            "sample_events": data.get("sample_events", []),
            "status": status,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("health_monitor: events fallo: %s", exc)
        return {
            "critical_count": 0,
            "error_count": 0,
            "filtered_count": 0,
            "top_sources": [],
            "sample_events": [],
            "status": "error",
            "error_msg": str(exc),
        }


# ===========================================================================
# Métrica: Dominio
# ===========================================================================

def _get_domain_metric() -> dict:
    try:
        script = r"""
$ErrorActionPreference = 'Stop'
try {
    $secure = Test-ComputerSecureChannel -ErrorAction Stop
    @{
        secure_channel = [bool]$secure
        status = $(if ($secure) { 'ok' } else { 'error' })
    } | ConvertTo-Json -Compress
} catch {
    @{
        secure_channel = $false
        status = 'not_in_domain'
    } | ConvertTo-Json -Compress
}
"""
        data = _load_json_from_ps(script, "domain")
        return {
            "secure_channel": bool(data["secure_channel"]),
            "status": data["status"],
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("health_monitor: domain fallo: %s", exc)
        return _error_metric(secure_channel=False, error_msg=str(exc))


# ===========================================================================
# Métrica: Uptime
# ===========================================================================

def _get_uptime_metric(config: dict) -> dict:
    try:
        script = r"""
$ErrorActionPreference = 'Stop'
try {
    $os = Get-CimInstance Win32_OperatingSystem
    $lastBoot = $os.LastBootUpTime
    $days = [math]::Round(((Get-Date) - $lastBoot).TotalDays, 1)
    @{
        last_boot = $lastBoot.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        days = $days
    } | ConvertTo-Json -Compress
} catch {
    Write-Output "ERROR=$($_.Exception.Message)"
}
"""
        data = _load_json_from_ps(script, "uptime")
        days = round(float(data["days"]), 1)
        max_days = config["thresholds"]["uptime"]["max_days_without_reboot"]
        status = "warning" if days >= max_days else "ok"
        return {
            "last_boot": data["last_boot"],
            "days": days,
            "status": status,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("health_monitor: uptime fallo: %s", exc)
        return _error_metric(last_boot=None, days=None, error_msg=str(exc))


# ===========================================================================
# Métrica: Boot Time
# ===========================================================================

def _get_boot_time_status(boot_duration_seconds: int | None, thresholds: dict) -> str:
    if boot_duration_seconds is None:
        return "unknown"
    if boot_duration_seconds < thresholds["optimal"]:
        return "optimal"
    if boot_duration_seconds < thresholds["normal"]:
        return "ok"
    if boot_duration_seconds < thresholds["degraded"]:
        return "degraded"
    return "critical"


def _get_boot_time_from_event_log() -> dict | None:
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
try {
    $event = Get-WinEvent -LogName 'Microsoft-Windows-Diagnostics-Performance/Operational' -MaxEvents 50 -ErrorAction Stop |
             Where-Object { $_.Id -eq 100 } |
             Select-Object -First 1
    if (-not $event) {
        Write-Output 'ERROR=NO_EVENT'
        exit 0
    }
    $xml = [xml]$event.ToXml()
    $data = @{}
    foreach ($node in $xml.Event.EventData.Data) {
        $data[$node.Name] = $node.'#text'
    }
    $bootStartTime = $data['BootStartTime']
    $bootTime = $data['BootTime']
    if (-not $bootStartTime -or -not $bootTime) {
        Write-Output 'ERROR=PARSE_FAILED'
        exit 0
    }
    @{
        boot_start_time = [string]$bootStartTime
        boot_time_ms = [int]$bootTime
    } | ConvertTo-Json -Compress
} catch {
    Write-Output "ERROR=$($_.Exception.Message)"
}
"""
    try:
        data = _load_json_from_ps(script, "boot_time_event")
    except RuntimeError:
        return None

    try:
        boot_start_raw = str(data["boot_start_time"])
        boot_start_normalized = boot_start_raw.rstrip("Z").split(".")[0]
        boot_dt_utc = datetime.strptime(boot_start_normalized, "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        boot_dt_local = boot_dt_utc.astimezone().replace(tzinfo=None)
        boot_time_ms = int(data["boot_time_ms"])
        if boot_time_ms <= 0:
            return None
        return {
            "last_boot_time": boot_dt_local.isoformat(timespec="seconds"),
            "boot_duration_seconds": max(1, int(boot_time_ms / 1000)),
            "source": "event_log",
        }
    except (KeyError, TypeError, ValueError):
        return None


def _get_boot_time_from_wmi() -> dict | None:
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
try {
    $os = Get-WmiObject -Class Win32_OperatingSystem -Namespace root\cimv2 -ErrorAction Stop |
          Select-Object -First 1
    if (-not $os -or -not $os.LastBootUpTime) {
        Write-Output 'ERROR=WMI_FAILED'
        exit 0
    }
    @{ last_boot = [string]$os.LastBootUpTime } | ConvertTo-Json -Compress
} catch {
    Write-Output "ERROR=$($_.Exception.Message)"
}
"""
    try:
        data = _load_json_from_ps(script, "boot_time_wmi")
    except RuntimeError:
        return None

    try:
        raw_value = str(data["last_boot"])
        boot_dt = datetime.strptime(raw_value[:14], "%Y%m%d%H%M%S")
        return {
            "last_boot_time": boot_dt.isoformat(timespec="seconds"),
            "boot_duration_seconds": None,
            "source": "wmi",
        }
    except (KeyError, TypeError, ValueError):
        return None


def _get_boot_time_metric(config: dict) -> dict:
    try:
        result = _get_boot_time_from_event_log()
        if result is None:
            result = _get_boot_time_from_wmi()
        if result is None:
            return _error_metric(
                last_boot_time=None,
                boot_duration_seconds=None,
                source=None,
                error_msg="Could not retrieve boot time from Event Log or WMI",
            )

        result["status"] = _get_boot_time_status(
            result["boot_duration_seconds"],
            config["thresholds"]["boot_time"],
        )
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("health_monitor: boot_time fallo: %s", exc)
        return _error_metric(
            last_boot_time=None,
            boot_duration_seconds=None,
            source=None,
            error_msg=str(exc),
        )


# ===========================================================================
# Métrica: Servicios
# ===========================================================================

def _get_service_tier(service_name: str, config: dict) -> int:
    if service_name in config["services"]["tier1"]:
        return 1
    if service_name in config["services"]["tier2"]:
        return 2
    if service_name in config["services"]["tier3"]:
        return 3
    return 0


def _get_service_status(state: str, startup_type: str | None, tier: int) -> str:
    if state == "Running":
        return "ok"
    if state == "Stopped":
        if startup_type == "Disabled":
            return "ok"
        if startup_type == "Automatic":
            if tier == 1:
                return "critical"
            if tier in {2, 3}:
                return "warning"
        if startup_type == "Manual":
            return "warning" if tier == 1 else "ok"
    return "ok"


def _get_services_metric(config: dict) -> list[dict]:
    try:
        all_services = (
            config["services"]["tier1"]
            + config["services"]["tier2"]
            + config["services"]["tier3"]
        )
        if not all_services:
            return []

        names_json = json.dumps(all_services, ensure_ascii=True)
        script = f"""
$ErrorActionPreference = 'Stop'
try {{
    $names = ConvertFrom-Json @'
{names_json}
'@
    $result = @()
    foreach ($name in $names) {{
        $service = Get-Service -Name $name -ErrorAction SilentlyContinue
        if (-not $service) {{
            $result += @{{
                name = [string]$name
                display_name = $null
                state = 'NotFound'
                startup_type = $null
            }}
            continue
        }}

        $cim = Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction SilentlyContinue
        $startMode = if ($cim) {{ [string]$cim.StartMode }} else {{ $null }}

        $result += @{{
            name = [string]$service.Name
            display_name = [string]$service.DisplayName
            state = [string]$service.Status
            startup_type = $startMode
        }}
    }}
    $result | ConvertTo-Json -Compress
}} catch {{
    Write-Output "ERROR=$($_.Exception.Message)"
}}
"""
        raw_services = _load_json_from_ps(script, "services")
        items = raw_services if isinstance(raw_services, list) else [raw_services]

        normalized = []
        for item in items:
            name = item["name"]
            tier = _get_service_tier(name, config)
            state = item["state"]
            startup_type = item.get("startup_type")

            if state == "NotFound":
                normalized.append(
                    {
                        "name": name,
                        "display_name": None,
                        "state": "NotFound",
                        "startup_type": None,
                        "tier": tier,
                        "status": "not_available",
                    }
                )
                continue

            normalized.append(
                {
                    "name": name,
                    "display_name": item.get("display_name") or None,
                    "state": state,
                    "startup_type": startup_type,
                    "tier": tier,
                    "status": _get_service_status(state, startup_type, tier),
                }
            )

        return normalized
    except Exception as exc:  # noqa: BLE001
        log.warning("health_monitor: services fallo: %s", exc)
        return [
            {
                "name": "services",
                "display_name": None,
                "state": "Error",
                "startup_type": None,
                "tier": 0,
                "status": "error",
            }
        ]


# ===========================================================================
# Punto de entrada del plugin
# ===========================================================================

def collect() -> dict | None:
    """
    Interfaz pública del plugin.

    Recoge 8 métricas de salud del sistema Windows siguiendo la spec v1.1.
    Si una métrica falla, el bloque correspondiente queda marcado con status=error
    y la ejecución global continúa.

    Nunca lanza excepciones al caller.
    """
    started = time.perf_counter()

    try:
        config = _load_config()

        metrics = {
            "cpu": _get_cpu_metric(config),
            "memory": _get_memory_metric(config),
            "disk": _get_disk_metric(config),
            "events": _get_events_metric(config),
            "domain": _get_domain_metric(),
            "uptime": _get_uptime_metric(config),
            "boot_time": _get_boot_time_metric(config),
            "services": _get_services_metric(config),
        }

        duration_ms = int((time.perf_counter() - started) * 1000)
        metrics_successful = sum(1 for value in metrics.values() if _success_metric(value))

        return {
            "plugin_version": _PLUGIN_VERSION,
            "host": _get_host(),
            "domain": _get_domain_name(),
            "timestamp": _utc_now(),
            "execution": {
                "duration_ms": duration_ms,
                "metrics_attempted": _METRICS_ATTEMPTED,
                "metrics_successful": metrics_successful,
            },
            "metrics": metrics,
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("health_monitor: excepcion no esperada en collect(): %s", exc)
        return None
