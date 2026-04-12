"""
Plugin: battery
Fuente principal : powercfg /batteryreport → parseo del HTML generado
Fallback         : WMI — clases BatteryStaticData, BatteryFullChargedCapacity,
                   Win32_Battery (Get-WmiObject vía subprocess, compatible 32/64 bit)
Privilegios      : Administrador local (requerido por powercfg /batteryreport)
Plataforma       : Solo Windows, equipos con batería

Contrato de retorno (ehukene_contratos.md §1.5 — battery, v1.1):

    {
        "battery_source":                "powercfg" | "wmi",
        "battery_name":                  str | None,
        "battery_manufacturer":          str | None,
        "battery_serial":                str | None,
        "battery_chemistry":             str | None,
        "battery_design_capacity_wh":    float   (> 0, 3 decimales),
        "battery_full_charge_capacity_wh": float (>= 0, 3 decimales),
        "battery_health_percent":        float   ([0.0, 150.0], 1 decimal),
        "battery_status":                int | None,
    }

    Devuelve None si el equipo no tiene batería o si ambas fuentes fallan.

Invariantes:
    - battery_source nunca es None.
    - battery_design_capacity_wh > 0 siempre.
    - battery_full_charge_capacity_wh >= 0 siempre.
    - battery_health_percent en [0.0, 150.0]; fuera de rango → None.
    - battery_status en [1, 11] si fuente es wmi (se incluye igualmente
      aunque esté fuera de rango, pero se registra anomalía en log).
    - Cuando battery_source es "wmi": name, manufacturer, serial,
      chemistry son None (WMI no los expone de forma fiable).
    - Capacidades WMI vienen en mWh (int); se convierten a Wh (/ 1000).
"""

import logging
import os
import re
import subprocess
import tempfile
from html.parser import HTMLParser

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_POWERCFG_TIMEOUT_S = 20          # segundos máximos para ejecutar powercfg
_PLUGIN_MAX_HEALTH  = 150.0       # límite superior del contrato


# ===========================================================================
# Fuente 1: powercfg /batteryreport
# ===========================================================================

class _BatteryReportParser(HTMLParser):
    """
    Parsea el HTML generado por 'powercfg /batteryreport'.

    Estrategia: busca la sección "Installed batteries" y extrae los valores
    de las filas de la tabla mediante un pequeño autómata de estado.  El
    formato del HTML es fijo y producido por Windows, por lo que el parseo
    por etiquetas es suficiente y robusto.
    """

    # Etiquetas de fila que nos interesan (en minúsculas, tal como las emite
    # el parser cuando encuentra el texto de celda de cabecera).
    _FIELD_MAP = {
        "name":                  "battery_name",
        "manufacturer":          "battery_manufacturer",
        "serial number":         "battery_serial",
        "chemistry":             "battery_chemistry",
        "design capacity":       "_design_raw",
        "full charge capacity":  "_full_raw",
    }

    def __init__(self):
        super().__init__()
        self._in_installed_section = False
        self._current_label        = None
        self._capture_next_td      = False
        self._in_td                = False
        self._td_text_parts        = []
        self._td_depth             = 0

        # Resultados
        self.battery_name         = None
        self.battery_manufacturer = None
        self.battery_serial       = None
        self.battery_chemistry    = None
        self._design_raw          = None   # p.e. "60.002 mWh"
        self._full_raw            = None

    # ── HTML parser callbacks ────────────────────────────────────────────────

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attr_dict = dict(attrs)

        if tag == "h2":
            self._pending_h2 = True
            return

        if tag == "td":
            self._in_td = True
            self._td_depth += 1
            self._td_text_parts = []

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag == "td" and self._in_td:
            self._td_depth -= 1
            if self._td_depth <= 0:
                self._process_td_text("".join(self._td_text_parts).strip())
                self._in_td = False
                self._td_depth = 0
                self._td_text_parts = []

    def handle_data(self, data):
        # Detectar sección "Installed batteries"
        stripped = data.strip()
        if "installed batteries" in stripped.lower():
            self._in_installed_section = True
            return
        # Salir de la sección cuando llega la siguiente h2 relevante
        if self._in_installed_section and stripped.lower() in (
            "recent usage", "battery usage", "usage history",
            "battery information", "current estimate",
        ):
            self._in_installed_section = False
            return

        if self._in_td and self._in_installed_section:
            self._td_text_parts.append(data)

    # ── Lógica de extracción ─────────────────────────────────────────────────

    def _process_td_text(self, text: str):
        if not self._in_installed_section or not text:
            return

        lower = text.lower()

        # ¿Es una etiqueta conocida?
        for label_key, attr in self._FIELD_MAP.items():
            if lower == label_key:
                self._current_label = attr
                return

        # ¿Tenemos una etiqueta pendiente?
        if self._current_label:
            setattr(self, self._current_label, text)
            self._current_label = None

    # ── Conversión de capacidades ────────────────────────────────────────────

    @staticmethod
    def _parse_capacity_wh(raw: str) -> float | None:
        """
        Convierte cadenas como "60.002 mWh" o "21,683 mWh" a float en Wh.

        powercfg puede usar coma o punto como separador decimal dependiendo
        del locale del sistema.  Normalizar antes de parsear.
        """
        if not raw:
            return None
        # Eliminar unidad y espacios
        cleaned = raw.strip().lower().replace("mwh", "").replace("wh", "").strip()
        # Normalizar separador decimal: si hay coma y no hay punto, la coma es decimal
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        elif "," in cleaned and "." in cleaned:
            # Formato tipo "60,002.5" → eliminar coma de miles
            cleaned = cleaned.replace(",", "")
        try:
            return round(float(cleaned), 3)
        except ValueError:
            return None

    def design_capacity_wh(self) -> float | None:
        return self._parse_capacity_wh(self._design_raw)

    def full_charge_capacity_wh(self) -> float | None:
        return self._parse_capacity_wh(self._full_raw)


def _run_powercfg() -> dict | None:
    """
    Ejecuta 'powercfg /batteryreport', parsea el HTML resultante y devuelve
    un dict con los campos del contrato (fuente "powercfg") o None si falla.
    """
    tmp_dir  = tempfile.gettempdir()
    tmp_file = os.path.join(tmp_dir, "ehukene_batteryreport.html")

    try:
        result = subprocess.run(
            ["powercfg", "/batteryreport", "/output", tmp_file, "/duration", "1"],
            capture_output=True,
            timeout=_POWERCFG_TIMEOUT_S,
        )
        if result.returncode != 0:
            log.debug(
                "powercfg retornó %d: %s",
                result.returncode,
                result.stderr.decode("utf-8", errors="replace").strip(),
            )
            return None
    except FileNotFoundError:
        log.debug("powercfg no encontrado en PATH")
        return None
    except subprocess.TimeoutExpired:
        log.warning("powercfg excedió el timeout de %ds", _POWERCFG_TIMEOUT_S)
        return None
    except Exception as exc:
        log.warning("Error ejecutando powercfg: %s", exc)
        return None

    try:
        with open(tmp_file, encoding="utf-8", errors="replace") as fh:
            html_content = fh.read()
    except OSError as exc:
        log.warning("No se pudo leer el informe de powercfg: %s", exc)
        return None
    finally:
        try:
            os.remove(tmp_file)
        except OSError:
            pass

    # Comprobar si el equipo no tiene batería (el informe lo indica explícitamente)
    if "no battery is installed" in html_content.lower():
        log.debug("powercfg: equipo sin batería")
        return None  # Señal de "sin batería"

    parser = _BatteryReportParser()
    try:
        parser.feed(html_content)
    except Exception as exc:
        log.warning("Error parseando HTML de powercfg: %s", exc)
        return None

    design_wh = parser.design_capacity_wh()
    full_wh   = parser.full_charge_capacity_wh()

    if design_wh is None or design_wh <= 0:
        log.debug("powercfg: design_capacity_wh no válida (%s)", design_wh)
        return None

    if full_wh is None or full_wh < 0:
        log.debug("powercfg: full_charge_capacity_wh no válida (%s)", full_wh)
        return None

    health = round((full_wh / design_wh) * 100, 1)

    if not (0.0 <= health <= _PLUGIN_MAX_HEALTH):
        log.warning(
            "battery_health_percent fuera de rango: %.1f (design=%.3f, full=%.3f)",
            health, design_wh, full_wh,
        )
        return None

    return {
        "battery_source":                  "powercfg",
        "battery_name":                    parser.battery_name,
        "battery_manufacturer":            parser.battery_manufacturer,
        "battery_serial":                  parser.battery_serial,
        "battery_chemistry":               parser.battery_chemistry,
        "battery_design_capacity_wh":      design_wh,
        "battery_full_charge_capacity_wh": full_wh,
        "battery_health_percent":          health,
        "battery_status":                  None,  # no disponible vía powercfg
    }


# ===========================================================================
# Fuente 2: WMI (fallback)
# ===========================================================================

def _run_wmi() -> dict | None:
    """
    Consulta WMI mediante subprocess + PowerShell para evitar la dependencia
    del paquete 'wmi' (que requiere pywin32) y los problemas WOW64 de
    Get-CimInstance en root\\WMI documentados en el script Ivanti anterior.

    Usa Get-WmiObject (DCOM) en las clases:
        - root\\WMI :: BatteryStaticData          → diseño + fabricante
        - root\\WMI :: BatteryFullChargedCapacity → capacidad actual
        - root\\cimv2 :: Win32_Battery            → estado + detección

    Devuelve dict con fuente "wmi" o None si no hay batería o falla.
    """
    ps_script = r"""
$ErrorActionPreference = 'Stop'

# Detección de batería via Win32_Battery
try {
    $wb = Get-WmiObject -Class Win32_Battery -Namespace root\cimv2 -ErrorAction Stop |
          Select-Object -First 1
    if (-not $wb) { Write-Output 'NO_BATTERY'; exit 0 }
    $batteryStatus = [int]$wb.BatteryStatus
} catch {
    Write-Output 'NO_BATTERY'; exit 0
}

# Capacidades via root\WMI
try {
    $sd = Get-WmiObject -Namespace root\WMI -Class BatteryStaticData -ErrorAction Stop |
          Where-Object { $_.Active -eq $true } | Select-Object -First 1
    if (-not $sd) { Write-Output 'WMI_FAILED'; exit 0 }
    $design = [long]$sd.DesignedCapacity
} catch {
    Write-Output 'WMI_FAILED'; exit 0
}

try {
    $fc = Get-WmiObject -Namespace root\WMI -Class BatteryFullChargedCapacity -ErrorAction Stop |
          Where-Object { $_.Active -eq $true } | Select-Object -First 1
    if (-not $fc) { Write-Output 'WMI_FAILED'; exit 0 }
    $full = [long]$fc.FullChargedCapacity
} catch {
    Write-Output 'WMI_FAILED'; exit 0
}

# Salida en formato parseable
Write-Output "DESIGN=$design"
Write-Output "FULL=$full"
Write-Output "STATUS=$batteryStatus"
"""

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as exc:
        log.debug("WMI fallback via PowerShell falló: %s", exc)
        return None

    output = result.stdout.decode("utf-8", errors="replace")
    log.debug("WMI PowerShell output: %s", output.strip())

    if "NO_BATTERY" in output:
        return None  # Sin batería
    if "WMI_FAILED" in output:
        log.warning("WMI: BatteryStaticData o BatteryFullChargedCapacity no disponibles")
        return None

    # Parsear valores
    values = {}
    for line in output.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip()

    try:
        design_mwh = int(values["DESIGN"])
        full_mwh   = int(values["FULL"])
        status     = int(values["STATUS"])
    except (KeyError, ValueError) as exc:
        log.warning("WMI: no se pudieron parsear los valores (%s)", exc)
        return None

    if design_mwh <= 0:
        log.warning("WMI: DesignedCapacity = %d mWh, no válido", design_mwh)
        return None

    # Convertir mWh → Wh (contrato v1.1: unidad uniforme en Wh)
    design_wh = round(design_mwh / 1000, 3)
    full_wh   = round(full_mwh   / 1000, 3)

    health = round((full_wh / design_wh) * 100, 1)

    if not (0.0 <= health <= _PLUGIN_MAX_HEALTH):
        log.warning(
            "WMI: battery_health_percent fuera de rango: %.1f (design=%d mWh, full=%d mWh)",
            health, design_mwh, full_mwh,
        )
        return None

    # battery_status: incluir aunque esté fuera de [1,11] (contrato §1.5)
    if not (1 <= status <= 11):
        log.warning("WMI: battery_status=%d fuera del rango esperado [1,11]", status)

    return {
        "battery_source":                  "wmi",
        "battery_name":                    None,   # no disponible vía WMI
        "battery_manufacturer":            None,
        "battery_serial":                  None,
        "battery_chemistry":               None,
        "battery_design_capacity_wh":      design_wh,
        "battery_full_charge_capacity_wh": full_wh,
        "battery_health_percent":          health,
        "battery_status":                  status,
    }


# ===========================================================================
# Punto de entrada del plugin
# ===========================================================================

def collect() -> dict | None:
    """
    Interfaz pública del plugin.  El collector llama únicamente a esta función.

    Estrategia de fuente con fallback (contrato §1.5):
        1. powercfg /batteryreport  → parseo del HTML generado
        2. WMI vía PowerShell       → si powercfg falla o no hay batería
        3. Devuelve None            → si ambas fuentes fallan

    Nunca lanza excepciones al caller.
    """
    try:
        log.debug("battery: intentando fuente powercfg")
        result = _run_powercfg()
        if result is not None:
            log.debug(
                "battery: powercfg OK — health=%.1f%% design=%.3f Wh full=%.3f Wh",
                result["battery_health_percent"],
                result["battery_design_capacity_wh"],
                result["battery_full_charge_capacity_wh"],
            )
            return result

        log.debug("battery: powercfg sin resultado, intentando WMI")
        result = _run_wmi()
        if result is not None:
            log.debug(
                "battery: WMI OK — health=%.1f%% design=%.3f Wh full=%.3f Wh",
                result["battery_health_percent"],
                result["battery_design_capacity_wh"],
                result["battery_full_charge_capacity_wh"],
            )
            return result

        log.debug("battery: ambas fuentes sin resultado (equipo sin batería o error)")
        return None

    except Exception as exc:  # noqa: BLE001
        # El contrato exige que collect() nunca propague excepciones
        log.exception("battery: excepción no esperada en collect(): %s", exc)
        return None
