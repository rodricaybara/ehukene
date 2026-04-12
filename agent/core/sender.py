"""
sender.py — Construye el payload y lo envía al backend con reintentos.

Política de reintentos: 3 intentos con 30 segundos de espera entre ellos.
Timeouts: 5s de conexión, 10s de lectura.
En caso de fallo tras todos los reintentos, registra el error y abandona.
"""

import json
import os
import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Dict

import urllib.request
import urllib.error

from core.config import AgentConfig
from core.logger import get_logger

logger = get_logger()


def _ssl_context(verify: bool) -> ssl.SSLContext:
    """
    Devuelve un contexto SSL con o sin verificación de certificado.

    verify=True  → comportamiento estándar (producción).
    verify=False → sin verificación (POC con certificados autofirmados).
    """
    if verify:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def register_device(config: AgentConfig) -> str | None:
    """
    Registra el dispositivo en el backend y devuelve la api_key asignada.

    Llama a POST /api/devices/register con el hostname del equipo.
    Este endpoint no requiere autenticación (Opción A — POC).

    Args:
        config: Configuración del agente (se usa api_url y timeouts).

    Returns:
        La api_key en claro si el registro fue exitoso.
        None si el registro falló.
    """
    url = f"{config.api_url}/devices/register"
    hostname = socket.gethostname()
    body = json.dumps({
        "hostname": hostname,
        "requested_by": "agent_auto_register",
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    total_timeout = config.timeout_connect + config.timeout_read

    logger.info(f"Auto-registro: contactando backend para registrar '{hostname}'...")

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(
            req,
            timeout=total_timeout,
            context=_ssl_context(config.verify_ssl),
        ) as response:
            if response.status == 201:
                data = json.loads(response.read().decode("utf-8"))
                api_key = data.get("api_key", "")
                if api_key:
                    logger.info(f"Auto-registro completado. Device ID: {data.get('device_id')}")
                    return api_key
                else:
                    logger.error("Auto-registro: respuesta 201 pero api_key ausente en el body.")
                    return None
            else:
                logger.error(f"Auto-registro: respuesta inesperada HTTP {response.status}")
                return None

    except urllib.error.HTTPError as e:
        if e.code == 409:
            logger.error(
                f"Auto-registro: el hostname '{hostname}' ya existe en el backend "
                "(HTTP 409). Revisar config.json — puede que api_key se haya perdido."
            )
        else:
            logger.error(f"Auto-registro: HTTP {e.code} — {e.reason}")
        return None

    except urllib.error.URLError as e:
        logger.error(f"Auto-registro: error de red — {e.reason}")
        return None

    except TimeoutError:
        logger.error("Auto-registro: timeout al conectar con el backend")
        return None

    except Exception as e:
        logger.error(f"Auto-registro: error inesperado — {e}")
        return None


def build_payload(metrics: Dict[str, Any], config: AgentConfig) -> Dict:
    """
    Construye el payload completo listo para enviar al backend.

    Args:
        metrics: Resultado consolidado del collector.
        config:  Configuración del agente.

    Returns:
        Diccionario con la estructura definida en el contrato v1.1 (sección 2.3).
        Campos raíz: device_id, timestamp, agent_version, username, metrics.
    """
    # El contrato exige formato "YYYY-MM-DDTHH:MM:SSZ" (sin microsegundos)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "device_id": socket.gethostname(),
        "timestamp": timestamp,
        "agent_version": config.agent_version,
        "username": os.environ.get("USERNAME") or os.environ.get("USER", "unknown"),
        "metrics": metrics,
    }


def send_payload(payload: Dict, config: AgentConfig) -> bool:
    """
    Envía el payload al backend con reintentos.

    Intenta hasta config.retry_attempts veces, esperando
    config.retry_wait_seconds entre cada intento.

    Args:
        payload: Diccionario a enviar como JSON.
        config:  Configuración del agente (URL, API key, reintentos).

    Returns:
        True si el envío fue exitoso, False si todos los reintentos fallaron.
    """
    url = f"{config.api_url}/telemetry"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": config.api_key,
    }
    body = json.dumps(payload).encode("utf-8")

    for attempt in range(1, config.retry_attempts + 1):
        logger.info(f"Envío al backend — intento {attempt}/{config.retry_attempts}")

        success, error_msg = _http_post(url, headers, body, config)

        if success:
            logger.info("Envío completado correctamente.")
            return True

        logger.error(f"Intento {attempt} fallido: {error_msg}")

        if attempt < config.retry_attempts:
            logger.info(f"Esperando {config.retry_wait_seconds}s antes del siguiente intento...")
            time.sleep(config.retry_wait_seconds)

    logger.error(
        f"Envío fallido tras {config.retry_attempts} intentos. "
        "Los datos de esta ejecución se descartan."
    )
    return False


def _http_post(
    url: str,
    headers: Dict[str, str],
    body: bytes,
    config: AgentConfig,
) -> tuple[bool, str]:
    """
    Realiza una petición HTTP POST.

    Usa urllib de la librería estándar para evitar dependencias externas
    en el ejecutable empaquetado con PyInstaller.

    Returns:
        (True, "") si la respuesta es 2xx.
        (False, mensaje_error) en cualquier otro caso.
    """
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        # urllib no tiene timeout separado por conexión/lectura en su API estándar,
        # usamos el timeout global de socket como total máximo.
        total_timeout = config.timeout_connect + config.timeout_read

        with urllib.request.urlopen(
            req,
            timeout=total_timeout,
            context=_ssl_context(config.verify_ssl),
        ) as response:
            status = response.status
            if 200 <= status < 300:
                return True, ""
            else:
                return False, f"HTTP {status}"

    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} — {e.reason}"

    except urllib.error.URLError as e:
        return False, f"Error de red — {e.reason}"

    except TimeoutError:
        return False, "Timeout al conectar con el backend"

    except Exception as e:
        return False, f"Error inesperado — {e}"
