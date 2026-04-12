"""
plugin_loader.py — Carga dinámica de plugins habilitados en config.json.

Importa cada plugin por nombre desde el directorio /plugins.
Un plugin que no existe o falla al importar se registra como error
y se excluye de la ejecución, sin afectar al resto.

El timeout de 30 segundos por ejecución de collect() (contrato §1.1)
lo aplica collector.py, no este módulo. La responsabilidad de este
módulo se limita a la carga e importación de los módulos.
"""

import importlib
import importlib.util
import os
import sys
from typing import Callable, Dict, Optional

from core.logger import get_logger

logger = get_logger()


def _get_plugins_dir() -> str:
    """Devuelve la ruta absoluta al directorio /plugins."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base_dir, "..", "plugins"))


def load_plugins(enabled_plugins: list) -> Dict[str, Callable]:
    """
    Carga los plugins habilitados y devuelve un diccionario
    {nombre_plugin: función_collect}.

    Plugins que no se pueden importar o no tienen función collect()
    son ignorados con un log de error.

    Args:
        enabled_plugins: Lista de nombres de plugin desde config.json.
                         Ejemplo: ["battery", "software_usage", "boot_time"]

    Returns:
        Diccionario con los plugins cargados correctamente.
    """
    plugins_dir = _get_plugins_dir()

    # Asegurar que el directorio de plugins está en el path de importación
    if plugins_dir not in sys.path:
        sys.path.insert(0, plugins_dir)

    loaded: Dict[str, Callable] = {}

    for plugin_name in enabled_plugins:
        collect_fn = _load_single_plugin(plugin_name, plugins_dir)
        if collect_fn is not None:
            loaded[plugin_name] = collect_fn

    logger.info(f"Plugins cargados: {list(loaded.keys())}")
    return loaded


def _load_single_plugin(plugin_name: str, plugins_dir: str) -> Optional[Callable]:
    """
    Intenta importar un plugin y devolver su función collect().

    Returns:
        La función collect() o None si el plugin no se puede cargar.
    """
    module_path = os.path.join(plugins_dir, f"{plugin_name}.py")

    if not os.path.exists(module_path):
        logger.error(f"Plugin '{plugin_name}': fichero no encontrado ({module_path})")
        return None

    try:
        spec = importlib.util.spec_from_file_location(
            f"plugins.{plugin_name}", module_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        logger.error(f"Plugin '{plugin_name}': error al importar — {e}")
        return None

    if not hasattr(module, "collect") or not callable(module.collect):
        logger.error(
            f"Plugin '{plugin_name}': no implementa la función collect()"
        )
        return None

    return module.collect