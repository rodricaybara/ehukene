"""
collector.py — Ejecuta los plugins cargados y consolida los resultados.

Cada plugin se ejecuta de forma aislada con un timeout de 30 segundos
(contrato §1.1). Si uno falla, supera el tiempo o devuelve None,
se descarta sin interrumpir los demás.

Tipos de retorno válidos de collect() según contrato v1.3 §1.3 y §1.4:
  - dict  con al menos una clave → se incluye en el payload
  - list[dict]                   → se incluye en el payload (entidades múltiples)
  - []   (lista vacía)           → se incluye en el payload (sin targets configurados)
  - None                         → se omite silenciosamente del payload
"""

import threading
from typing import Callable, Dict, Any, Optional, Union

from core.logger import get_logger

logger = get_logger()

_PLUGIN_TIMEOUT_S = 30  # Contrato §1.1


def run_collection(plugins: Dict[str, Callable]) -> Dict[str, Any]:
    """
    Ejecuta todos los plugins cargados y devuelve sus métricas consolidadas.

    Args:
        plugins: Diccionario {nombre_plugin: función_collect} generado
                 por plugin_loader.

    Returns:
        Diccionario {nombre_plugin: resultado} con los plugins que
        produjeron datos válidos. Los plugins que devolvieron None
        o fallaron quedan excluidos. Los que devolvieron [] se incluyen.
    """
    metrics: Dict[str, Any] = {}

    for plugin_name, collect_fn in plugins.items():
        result = _run_plugin(plugin_name, collect_fn)
        # None → excluir. Cualquier otro valor (dict, list, []) → incluir.
        if result is not _SENTINEL:
            metrics[plugin_name] = result

    logger.info(
        f"Recogida completada. Plugins con datos: {list(metrics.keys())}"
    )
    return metrics


# Centinela interno para distinguir "omitir" de "incluir lista vacía"
_SENTINEL = object()


def _run_plugin(plugin_name: str, collect_fn: Callable) -> Any:
    """
    Ejecuta un plugin individual con timeout y manejo de excepciones.

    Returns:
        El resultado del plugin (dict, list o []) si es válido.
        _SENTINEL si el plugin debe omitirse (None, error, timeout, tipo inválido).
    """
    result_holder: Dict[str, Any] = {}
    exception_holder: Dict[str, Exception] = {}

    def _target():
        try:
            result_holder["value"] = collect_fn()
        except Exception as e:
            exception_holder["error"] = e

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=_PLUGIN_TIMEOUT_S)

    # ── Timeout ──────────────────────────────────────────────────────────────
    if thread.is_alive():
        logger.error(
            f"Plugin '{plugin_name}': superó el timeout de {_PLUGIN_TIMEOUT_S}s "
            "— se trata como None (contrato §1.1)"
        )
        return _SENTINEL

    # ── Excepción dentro del plugin ──────────────────────────────────────────
    if "error" in exception_holder:
        logger.error(
            f"Plugin '{plugin_name}': excepción durante collect() — "
            f"{exception_holder['error']}"
        )
        return _SENTINEL

    result = result_holder.get("value")

    # ── None explícito: equipo no aplica o error interno del plugin ──────────
    if result is None:
        logger.info(f"Plugin '{plugin_name}': devolvió None, se omite del payload")
        return _SENTINEL

    # ── list[dict]: plugins de entidades múltiples (ej: software_usage) ──────
    if isinstance(result, list):
        if result == []:
            # Lista vacía es retorno válido — sin targets configurados (contrato §1.3)
            logger.info(f"Plugin '{plugin_name}': devolvió lista vacía [], se incluye")
            return result
        # Verificar que todos los elementos son dicts planos
        if not all(isinstance(item, dict) for item in result):
            logger.error(
                f"Plugin '{plugin_name}': la lista devuelta contiene elementos "
                "que no son dict — se omite"
            )
            return _SENTINEL
        logger.info(
            f"Plugin '{plugin_name}': devolvió lista con {len(result)} elemento(s)"
        )
        return result

    # ── dict: plugin estándar ─────────────────────────────────────────────────
    if isinstance(result, dict):
        if not result:
            logger.info(f"Plugin '{plugin_name}': devolvió dict vacío {{}}, se omite")
            return _SENTINEL
        return result

    # ── Tipo no permitido por el contrato ─────────────────────────────────────
    logger.error(
        f"Plugin '{plugin_name}': collect() devolvió tipo no permitido "
        f"'{type(result).__name__}' — se omite (contrato §1.4)"
    )
    return _SENTINEL