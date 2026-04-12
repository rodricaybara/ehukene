"""
Plugin: disk_usage
Fuente principal : CIM — Win32_LogicalDisk (DriveType=3) vía subprocess PowerShell
Privilegios      : Usuario estándar
Plataforma       : Solo Windows

Contrato de retorno (propuesto para disk_usage, entidades múltiples):

    list[dict] — una entrada por unidad lógica local

    Cada dict:
    {
        "disk_source":        "cim",
        "drive_letter":       str,
        "volume_name":        str | None,
        "filesystem":         str | None,
        "total_capacity_gb":  float,  # > 0, 3 decimales
        "free_capacity_gb":   float,  # >= 0, 3 decimales
        "used_capacity_gb":   float,  # >= 0, 3 decimales
        "used_percent":       float,  # [0.0, 100.0], 1 decimal
    }

    Devuelve [] si el equipo no tiene unidades locales detectables.
    Devuelve None si la fuente falla o el plugin sufre un error interno inesperado.

Invariantes:
    - disk_source es siempre "cim".
    - drive_letter nunca es None ni cadena vacía.
    - total_capacity_gb > 0.0 siempre.
    - free_capacity_gb >= 0.0 siempre.
    - used_capacity_gb >= 0.0 siempre.
    - free_capacity_gb <= total_capacity_gb siempre.
    - used_percent está en [0.0, 100.0].
"""

import json
import logging
import subprocess

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_CIM_TIMEOUT_S = 15
_BYTES_PER_GB = 1024 ** 3


# ===========================================================================
# Fuente 1: CIM — Win32_LogicalDisk
# ===========================================================================

def _normalize_optional_str(value: object) -> str | None:
    """Normaliza strings opcionales: cadena vacía -> None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _run_cim() -> list[dict] | None:
    """
    Consulta Win32_LogicalDisk vía CIM para unidades locales (DriveType=3) y devuelve
    una lista con el contrato completo por unidad.
    """
    ps_script = r"""
$ErrorActionPreference = 'Stop'

try {
    $items = @(Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction Stop |
        Select-Object DeviceID, VolumeName, FileSystem, Size, FreeSpace)

    if ($items.Count -eq 0) {
        Write-Output 'NO_LOCAL_DISKS'
        exit 0
    }

    $items | ConvertTo-Json -Compress
} catch {
    Write-Output "WMI_ERROR=$($_.Exception.Message)"
}
"""

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=_CIM_TIMEOUT_S,
        )
    except FileNotFoundError:
        log.debug("disk_cim: PowerShell no encontrado en PATH")
        return None
    except subprocess.TimeoutExpired:
        log.warning("disk_cim: Get-CimInstance excedió el timeout de %ds", _CIM_TIMEOUT_S)
        return None
    except Exception as exc:
        log.warning("disk_cim: error inesperado ejecutando PowerShell: %s", exc)
        return None

    output = result.stdout.strip()
    log.debug("disk_cim: PowerShell output: %s", output)

    if output == "NO_LOCAL_DISKS":
        log.debug("disk_cim: equipo sin unidades locales detectables")
        return []

    if output.startswith("WMI_ERROR="):
        log.warning("disk_cim: error al consultar CIM: %s", output[len("WMI_ERROR="):])
        return None

    try:
        raw_items = json.loads(output)
    except json.JSONDecodeError as exc:
        log.warning("disk_cim: no se pudo parsear la salida JSON: %s", exc)
        return None

    if isinstance(raw_items, list):
        items = raw_items
    elif isinstance(raw_items, dict):
        items = [raw_items]
    else:
        log.warning("disk_cim: salida JSON no es lista ni dict: %r", type(raw_items))
        return None

    normalized: list[dict] = []

    for item in items:
        if not isinstance(item, dict):
            log.warning("disk_cim: elemento no válido en la salida: %r", item)
            return None

        drive_letter = _normalize_optional_str(item.get("DeviceID"))
        if drive_letter is None:
            log.warning("disk_cim: DeviceID ausente o vacío")
            return None

        try:
            total_bytes = int(item["Size"])
            free_bytes = int(item["FreeSpace"])
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("disk_cim: Size o FreeSpace no válidos para %s: %s", drive_letter, exc)
            return None

        if total_bytes <= 0:
            log.warning("disk_cim: Size no válido para %s: %d", drive_letter, total_bytes)
            return None

        if free_bytes < 0:
            log.warning("disk_cim: FreeSpace no válido para %s: %d", drive_letter, free_bytes)
            return None

        if free_bytes > total_bytes:
            log.warning(
                "disk_cim: FreeSpace > Size para %s (%d > %d)",
                drive_letter,
                free_bytes,
                total_bytes,
            )
            return None

        used_bytes = total_bytes - free_bytes
        used_percent = round((used_bytes / total_bytes) * 100, 1)

        if not (0.0 <= used_percent <= 100.0):
            log.warning(
                "disk_cim: used_percent fuera de rango para %s: %.1f",
                drive_letter,
                used_percent,
            )
            return None

        normalized.append(
            {
                "disk_source": "cim",
                "drive_letter": drive_letter,
                "volume_name": _normalize_optional_str(item.get("VolumeName")),
                "filesystem": _normalize_optional_str(item.get("FileSystem")),
                "total_capacity_gb": round(total_bytes / _BYTES_PER_GB, 3),
                "free_capacity_gb": round(free_bytes / _BYTES_PER_GB, 3),
                "used_capacity_gb": round(used_bytes / _BYTES_PER_GB, 3),
                "used_percent": used_percent,
            }
        )

    normalized.sort(key=lambda disk: disk["drive_letter"])
    return normalized


# ===========================================================================
# Punto de entrada del plugin
# ===========================================================================

def collect() -> list[dict] | None:
    """
    Interfaz pública del plugin. El collector llama únicamente a esta función.

    Fuente: CIM (Win32_LogicalDisk, DriveType=3).
    Devuelve [] si no hay unidades locales detectables.
    Devuelve None si la consulta CIM falla.

    Ejemplo de retorno:
        [
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
                ...
            }
        ]

    Nunca lanza excepciones al caller.
    """
    try:
        log.debug("disk_usage: recogiendo métricas")
        result = _run_cim()
        if result is not None:
            log.debug("disk_usage: OK — unidades=%d", len(result))
            return result

        log.debug("disk_usage: fallo en consulta CIM")
        return None

    except Exception as exc:  # noqa: BLE001
        log.exception("disk_usage: excepción no esperada en collect(): %s", exc)
        return None
