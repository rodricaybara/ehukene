"""
logger.py — Configuración centralizada de logging.

Escribe en C:\\ProgramData\\EHUkene\\agent.log con rotación automática.
Nivel: INFO (errores + eventos clave). DEBUG disponible si se activa.

Un único logger compartido por todos los módulos del agente.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOGGER_NAME = "ehukene"
LOG_FILENAME = "agent.log"
LOG_MAX_BYTES = 5 * 1024 * 1024   # 5 MB por fichero
LOG_BACKUP_COUNT = 3               # Conservar hasta 3 ficheros rotados


def setup_logger(data_dir: str, debug: bool = False) -> logging.Logger:
    """
    Inicializa y devuelve el logger del agente.

    Crea el directorio data_dir si no existe.
    Añade dos handlers: fichero rotativo + consola (para desarrollo).

    Args:
        data_dir: Ruta al directorio de datos (C:\\ProgramData\\EHUkene).
        debug:    Si True, activa nivel DEBUG en lugar de INFO.

    Returns:
        Logger configurado.
    """
    os.makedirs(data_dir, exist_ok=True)

    log_path = os.path.join(data_dir, LOG_FILENAME)
    level = logging.DEBUG if debug else logging.INFO

    logger = logging.getLogger(LOGGER_NAME)

    # Evitar duplicar handlers si se llama varias veces (tests, etc.)
    if logger.handlers:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(module)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler de fichero con rotación
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Handler de consola (útil en desarrollo y para ver output en Task Scheduler)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def get_logger() -> logging.Logger:
    """
    Devuelve el logger del agente ya inicializado.
    Llamar a setup_logger() antes de usar este método.
    """
    return logging.getLogger(LOGGER_NAME)