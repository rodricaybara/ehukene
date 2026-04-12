"""
config.py — Lectura y validación de la configuración del agente.

Lee config.json desde el directorio del ejecutable.
Lanza ConfigError si algún campo obligatorio falta o es inválido.
"""

import json
import os
import sys
from dataclasses import dataclass
from typing import List


class ConfigError(Exception):
    """Error de configuración del agente."""
    pass


REQUIRED_FIELDS = ["enabled_plugins", "api_url", "agent_version"]


@dataclass
class AgentConfig:
    enabled_plugins: List[str]
    api_url: str
    agent_version: str
    # api_key vacía ("") indica que el dispositivo no está registrado aún.
    # main.py detecta este estado y ejecuta el auto-registro (Opción A).
    api_key: str = ""
    # Reintentos y timeouts — valores por defecto alineados con decisiones de diseño
    retry_attempts: int = 3
    retry_wait_seconds: int = 30
    timeout_connect: int = 5
    timeout_read: int = 10
    # Directorio de datos en el equipo
    data_dir: str = r"C:\ProgramData\EHUkene"
    # Auto-actualización — Fase 2. Aceptado en config pero sin lógica activa en Fase 1.
    auto_update: bool = False
    # Verificación SSL. False solo para POC con certificados autofirmados.
    # En producción debe ser True con certificado corporativo válido.
    verify_ssl: bool = True
    # Ruta al config.json — necesaria para que main.py pueda persistir la api_key
    # tras el auto-registro sin tener que recalcularla.
    config_path: str = ""


def load_config(config_path: str = None) -> AgentConfig:
    """
    Carga y valida config.json.

    Args:
        config_path: Ruta explícita al fichero. Si es None, lo busca
                     junto al ejecutable/script.

    Returns:
        AgentConfig con los valores leídos.

    Raises:
        ConfigError: Si el fichero no existe, no es JSON válido,
                     o faltan campos obligatorios.
    """
    if config_path is None:
        # sys.frozen indica que estamos dentro de un ejecutable PyInstaller.
        # En ese caso sys.executable apunta al .exe real, no al directorio
        # temporal donde PyInstaller extrae los ficheros en runtime.
        # En ejecución directa con Python usamos __file__ como antes.
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            # Subir un nivel: core/ → agent/
            base_dir = os.path.normpath(os.path.join(base_dir, ".."))
        config_path = os.path.join(base_dir, "config.json")

    if not os.path.exists(config_path):
        raise ConfigError(f"Fichero de configuración no encontrado: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"config.json no es JSON válido: {e}")

    # Validar campos obligatorios
    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        raise ConfigError(f"Campos obligatorios ausentes en config.json: {missing}")

    if not isinstance(raw["enabled_plugins"], list) or len(raw["enabled_plugins"]) == 0:
        raise ConfigError("'enabled_plugins' debe ser una lista no vacía.")

    if not raw["api_url"].startswith("https://"):
        raise ConfigError("'api_url' debe usar HTTPS.")

    return AgentConfig(
        enabled_plugins=raw["enabled_plugins"],
        api_url=raw["api_url"].rstrip("/"),
        agent_version=raw["agent_version"],
        api_key=raw.get("api_key", ""),
        retry_attempts=raw.get("retry_attempts", 3),
        retry_wait_seconds=raw.get("retry_wait_seconds", 30),
        timeout_connect=raw.get("timeout_connect", 5),
        timeout_read=raw.get("timeout_read", 10),
        data_dir=raw.get("data_dir", r"C:\ProgramData\EHUkene"),
        auto_update=raw.get("auto_update", False),
        verify_ssl=raw.get("verify_ssl", True),
        config_path=config_path,
    )