"""
main.py — Punto de entrada del agente EHUkene.

Flujo principal:
  1. Cargar configuración
  2. Inicializar logger
  3. Resolver api_key (config.json → data_dir/api_key.dat → auto-registro)
  4. Comprobar si ya se ejecutó hoy (last_run.json)
  5. Cargar plugins habilitados
  6. Ejecutar recogida de métricas
  7. Construir y enviar payload
  8. Actualizar last_run.json solo si el envío fue exitoso

Estrategia de persistencia de api_key (Opción 2):
  La api_key se guarda en data_dir/api_key.dat además de en config.json.
  Si Ivanti machaca config.json en un redespliegue, el agente recupera
  la key desde data_dir y evita registrar el dispositivo de nuevo.
"""

import json
import os
import sys
from datetime import date, datetime, timezone

from core.config import load_config, ConfigError
from core.logger import setup_logger, get_logger
from core.plugin_loader import load_plugins
from core.collector import run_collection
from core.sender import build_payload, send_payload, register_device

LAST_RUN_FILENAME = "last_run.json"
API_KEY_FILENAME  = "api_key.dat"


def _get_last_run_path(data_dir: str) -> str:
    return os.path.join(data_dir, LAST_RUN_FILENAME)


def _get_api_key_path(data_dir: str) -> str:
    return os.path.join(data_dir, API_KEY_FILENAME)


def _already_ran_today(data_dir: str) -> bool:
    """
    Comprueba si el agente ya realizó un envío exitoso hoy.

    Returns:
        True si ya se ejecutó hoy, False en caso contrario o si el
        fichero no existe o está corrupto.
    """
    path = _get_last_run_path(data_dir)
    if not os.path.exists(path):
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        last_run_date = date.fromisoformat(data["last_successful_run_date"])
        return last_run_date == date.today()
    except Exception:
        # Fichero corrupto o formato inesperado: ignorar y continuar
        return False


def _update_last_run(data_dir: str) -> None:
    """Actualiza last_run.json con la fecha de hoy."""
    os.makedirs(data_dir, exist_ok=True)
    path = _get_last_run_path(data_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "last_successful_run_date": date.today().isoformat(),
                "last_successful_run_ts": datetime.now(timezone.utc).isoformat(),
            },
            f,
            indent=2,
        )


def _load_api_key_from_dat(data_dir: str) -> str:
    """
    Lee la api_key persistida en data_dir/api_key.dat.

    Returns:
        La api_key si el fichero existe y no está vacío, "" en caso contrario.
    """
    path = _get_api_key_path(data_dir)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            key = f.read().strip()
        return key
    except Exception as e:
        get_logger().error(f"No se pudo leer api_key.dat: {e}")
        return ""


def _save_api_key(config_path: str, data_dir: str, api_key: str) -> None:
    """
    Persiste la api_key en dos ubicaciones:
      1. data_dir/api_key.dat  — copia de seguridad resistente a redespliegues.
      2. config.json           — para que el agente la use directamente en el
                                 próximo arranque sin leer api_key.dat.

    Si alguna escritura falla se loguea pero no se aborta — la key está
    en memoria y el envío del día puede continuar igualmente.
    """
    logger = get_logger()
    os.makedirs(data_dir, exist_ok=True)

    # 1. Guardar en data_dir/api_key.dat
    dat_path = _get_api_key_path(data_dir)
    try:
        with open(dat_path, "w", encoding="utf-8") as f:
            f.write(api_key)
        logger.info(f"api_key guardada en {dat_path}")
    except Exception as e:
        logger.error(f"No se pudo guardar api_key.dat: {e}")

    # 2. Actualizar config.json
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        raw["api_key"] = api_key
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)
        logger.info("api_key actualizada en config.json")
    except Exception as e:
        logger.error(
            f"No se pudo actualizar api_key en config.json: {e} "
            "(api_key.dat sigue siendo válido como respaldo)"
        )


def main() -> int:
    """
    Punto de entrada principal.

    Returns:
        0 si todo fue bien.
        1 si hubo error de configuración, registro o ningún plugin cargado.
        2 si el agente ya se ejecutó hoy.
        3 si el envío falló tras todos los reintentos.
    """
    # --- 1. Configuración ---
    try:
        config = load_config()
    except ConfigError as e:
        # El logger aún no está inicializado; escribir en stderr
        print(f"[EHUkene] Error de configuración: {e}", file=sys.stderr)
        return 1

    # --- 2. Logger ---
    setup_logger(config.data_dir)
    logger = get_logger()
    logger.info("=== EHUkene agente iniciado ===")

    # --- 3. Resolver api_key ---
    # Prioridad:
    #   a) config.json tiene api_key → usarla directamente.
    #   b) config.json vacío pero api_key.dat existe → recuperar de ahí
    #      (caso típico: Ivanti machacó config.json en un redespliegue).
    #   c) Ninguna → auto-registro y guardar en ambos sitios.
    if not config.api_key:
        api_key_from_dat = _load_api_key_from_dat(config.data_dir)

        if api_key_from_dat:
            logger.info(
                "api_key no encontrada en config.json pero sí en api_key.dat. "
                "Recuperando key existente — el dispositivo no necesita registrarse de nuevo."
            )
            config.api_key = api_key_from_dat
            # Sincronizar config.json para que el próximo arranque no pase por aquí
            _save_api_key(config.config_path, config.data_dir, api_key_from_dat)

        else:
            logger.info(
                "api_key no encontrada en ningún sitio. "
                "Iniciando auto-registro del dispositivo..."
            )
            api_key = register_device(config)
            if not api_key:
                logger.error(
                    "Auto-registro fallido. El agente no puede continuar sin api_key."
                )
                return 1
            config.api_key = api_key
            _save_api_key(config.config_path, config.data_dir, api_key)
            logger.info("Dispositivo registrado correctamente.")

    # --- 4. Control de duplicados ---
    if _already_ran_today(config.data_dir):
        logger.info("El agente ya realizó un envío exitoso hoy. Saliendo.")
        return 2

    # --- 5. Cargar plugins ---
    plugins = load_plugins(config.enabled_plugins)

    if not plugins:
        logger.error("No se pudo cargar ningún plugin. Abortando.")
        return 1

    # --- 6. Recogida de métricas ---
    metrics = run_collection(plugins)

    if not metrics:
        logger.error("Ningún plugin produjo datos. Abortando envío.")
        return 1

    # --- 7. Construir y enviar payload ---
    payload = build_payload(metrics, config)
    success = send_payload(payload, config)

    # --- 8. Actualizar last_run ---
    if success:
        _update_last_run(config.data_dir)
        logger.info("=== EHUkene agente finalizado correctamente ===")
        return 0
    else:
        logger.error("=== EHUkene agente finalizado con error de envío ===")
        return 3


if __name__ == "__main__":
    sys.exit(main())