# EHUkene Agent — Documentación del código

**Versión:** 1.0  
**Fecha:** 2026-04-08  
**Módulos:** `core/config.py` · `core/logger.py` · `core/plugin_loader.py` · `core/collector.py` · `core/sender.py` · `core/main.py`

---

## Índice

1. [Arquitectura general](#1-arquitectura-general)
2. [Flujo de ejecución](#2-flujo-de-ejecución)
3. [config.py](#3-configpy)
4. [logger.py](#4-loggerpy)
5. [plugin_loader.py](#5-plugin_loaderpy)
6. [collector.py](#6-collectorpy)
7. [sender.py](#7-senderpy)
8. [main.py](#8-mainpy)
9. [config.json — referencia de campos](#9-configjson--referencia-de-campos)

---

## 1. Arquitectura general

El agente está organizado en módulos con responsabilidades estrictamente separadas. Ningún módulo conoce los detalles internos de otro salvo a través de sus interfaces públicas.

```
config.json
    ↓
config.py       → lee y valida la configuración
    ↓
logger.py       → inicializa el sistema de logging
    ↓
plugin_loader.py → carga dinámicamente los plugins habilitados
    ↓
collector.py    → ejecuta cada plugin con timeout y consolida resultados
    ↓
sender.py       → construye el payload y lo envía al backend
    ↓
main.py         → orquesta todo el flujo, controla duplicados y auto-registro
```

**Dependencias entre módulos:**

```
main.py
  ├── core.config      (load_config, ConfigError)
  ├── core.logger      (setup_logger, get_logger)
  ├── core.plugin_loader (load_plugins)
  ├── core.collector   (run_collection)
  └── core.sender      (build_payload, send_payload, register_device)

collector.py
  └── core.logger

plugin_loader.py
  └── core.logger

sender.py
  ├── core.config
  └── core.logger
```

Los plugins en `agent/plugins/` son módulos independientes. No pueden importar nada de `core/` — su única interfaz con el sistema es la función `collect()`.

---

## 2. Flujo de ejecución

```
Task Scheduler lanza agent.exe al inicio de sesión
        │
        ▼
  1. Cargar config.json
        │
        ▼
  2. Inicializar logger → C:\ProgramData\EHUkene\agent.log
        │
        ▼
  3. ¿api_key vacía?
     Sí → POST /api/devices/register → guardar api_key en config.json
     No → continuar
        │
        ▼
  4. ¿Ya se ejecutó hoy? (last_run.json)
     Sí → salir con código 2
     No → continuar
        │
        ▼
  5. Cargar plugins habilitados desde /plugins
        │
        ▼
  6. Ejecutar cada plugin con timeout de 30s
        │
        ▼
  7. Construir payload + enviar a POST /api/telemetry
     (hasta 3 reintentos con 30s de espera)
        │
        ▼
  8. ¿Envío exitoso?
     Sí → actualizar last_run.json → salir con código 0
     No → salir con código 3
```

---

## 3. config.py

**Responsabilidad:** leer `config.json`, validar los campos obligatorios y exponer la configuración como un objeto tipado (`AgentConfig`).

### `AgentConfig`

Dataclass con todos los parámetros del agente. Todos los campos opcionales tienen valor por defecto.

| Campo | Tipo | Obligatorio | Por defecto | Descripción |
|---|---|---|---|---|
| `enabled_plugins` | `List[str]` | Sí | — | Plugins a ejecutar |
| `api_url` | `str` | Sí | — | URL base del backend. Debe empezar por `https://` |
| `agent_version` | `str` | Sí | — | Versión del agente en semver |
| `api_key` | `str` | No | `""` | Key de autenticación. Vacía = no registrado |
| `retry_attempts` | `int` | No | `3` | Reintentos de envío |
| `retry_wait_seconds` | `int` | No | `30` | Segundos entre reintentos |
| `timeout_connect` | `int` | No | `5` | Timeout de conexión en segundos |
| `timeout_read` | `int` | No | `10` | Timeout de lectura en segundos |
| `data_dir` | `str` | No | `C:\ProgramData\EHUkene` | Directorio de datos en runtime |
| `auto_update` | `bool` | No | `False` | Auto-actualización (Fase 2, sin lógica activa) |
| `verify_ssl` | `bool` | No | `True` | Verificación de certificado SSL |
| `config_path` | `str` | No | `""` | Ruta resuelta al config.json (uso interno) |

### `load_config(config_path=None)`

Localiza y carga `config.json`. La resolución de ruta distingue dos contextos:

```python
if getattr(sys, 'frozen', False):
    # Ejecutable PyInstaller → junto al .exe real
    base_dir = os.path.dirname(sys.executable)
else:
    # Ejecución directa → subir un nivel desde core/
    base_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
```

Esta distinción es necesaria porque PyInstaller en modo `--onefile` extrae los ficheros a un directorio temporal (`%TEMP%\_MEIxxxxxx\`), y `__file__` apuntaría a ese directorio temporal en lugar de al directorio del `.exe` real.

**Validaciones:**
- Los campos `enabled_plugins`, `api_url` y `agent_version` son obligatorios.
- `enabled_plugins` debe ser una lista no vacía.
- `api_url` debe empezar por `https://`.

### `ConfigError`

Excepción lanzada por `load_config()` ante cualquier problema de configuración. Se captura en `main.py` antes de que el logger esté inicializado, por lo que el mensaje se escribe en `stderr`.

---

## 4. logger.py

**Responsabilidad:** configurar un logger compartido por todos los módulos del agente, con salida a fichero rotativo y consola.

### Constantes

| Constante | Valor | Descripción |
|---|---|---|
| `LOGGER_NAME` | `"ehukene"` | Nombre del logger. Todos los módulos lo obtienen con `getLogger("ehukene")` |
| `LOG_FILENAME` | `"agent.log"` | Nombre del fichero de log |
| `LOG_MAX_BYTES` | `5 MB` | Tamaño máximo por fichero antes de rotar |
| `LOG_BACKUP_COUNT` | `3` | Número de ficheros rotados a conservar |

### `setup_logger(data_dir, debug=False)`

Inicializa el logger con dos handlers:

- **`RotatingFileHandler`** → `C:\ProgramData\EHUkene\agent.log`. Crea el directorio si no existe.
- **`StreamHandler`** → consola. Útil en desarrollo y cuando `console=True` en PyInstaller.

Nivel por defecto: `INFO` (errores + eventos clave). Con `debug=True`: `DEBUG`.

Formato de los mensajes:
```
2026-04-08 11:34:13 [INFO] main — === EHUkene agente iniciado ===
```

Protegido contra doble inicialización — si el logger ya tiene handlers no añade nuevos.

### `get_logger()`

Devuelve el logger ya inicializado. Todos los módulos lo obtienen con esta función tras haber llamado a `setup_logger()` en `main.py`.

---

## 5. plugin_loader.py

**Responsabilidad:** cargar dinámicamente los módulos Python de los plugins habilitados en `config.json` y exponer su función `collect()`.

### `load_plugins(enabled_plugins)`

Itera la lista de nombres de plugin, intenta importar cada módulo desde `agent/plugins/` y devuelve un diccionario `{nombre: función_collect}`. Los plugins que fallan al importar se excluyen sin afectar al resto.

Añade el directorio `plugins/` a `sys.path` para que los imports dentro de los propios plugins funcionen correctamente.

### `_load_single_plugin(plugin_name, plugins_dir)`

Carga un plugin individual usando `importlib.util`:

```python
spec = importlib.util.spec_from_file_location(f"plugins.{plugin_name}", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
```

Condiciones para que un plugin sea válido:
1. El fichero `{nombre}.py` existe en `plugins/`.
2. El módulo se puede importar sin errores.
3. El módulo tiene un atributo `collect` que es callable.

Si alguna condición falla, se loguea el error y se devuelve `None`.

> **Nota:** el timeout de 30 segundos por ejecución de `collect()` lo aplica `collector.py`, no este módulo. La responsabilidad de `plugin_loader` se limita a la carga e importación.

---

## 6. collector.py

**Responsabilidad:** ejecutar cada plugin cargado de forma aislada, aplicar el timeout del contrato y consolidar los resultados.

### `_SENTINEL`

Objeto centinela interno usado para distinguir "omitir del payload" de "incluir lista vacía". Es necesario porque `None` y `[]` tienen significados distintos según el contrato:

| Retorno del plugin | Significado | Acción |
|---|---|---|
| `dict` no vacío | Datos válidos | Incluir en payload |
| `list[dict]` | Datos de entidades múltiples | Incluir en payload |
| `[]` | Sin targets configurados — retorno válido | Incluir en payload |
| `None` | Equipo no aplica o error interno | Omitir del payload |

### `run_collection(plugins)`

Ejecuta `_run_plugin()` para cada plugin y construye el diccionario de métricas. Solo incluye en el resultado los plugins cuyo retorno no es `_SENTINEL`.

### `_run_plugin(plugin_name, collect_fn)`

Ejecuta `collect_fn()` en un hilo daemon con timeout de 30 segundos:

```python
thread = threading.Thread(target=_target, daemon=True)
thread.start()
thread.join(timeout=_PLUGIN_TIMEOUT_S)

if thread.is_alive():
    # Timeout superado
    return _SENTINEL
```

El uso de `daemon=True` garantiza que el hilo no impide que el proceso principal termine aunque el plugin se quede colgado.

Tras la ejecución valida el tipo del resultado según el contrato §1.4:
- `None` → `_SENTINEL`
- `list` vacía → devuelve `[]`
- `list` con elementos no-dict → `_SENTINEL` + error en log
- `list` con dicts → devuelve la lista
- `dict` vacío → `_SENTINEL`
- `dict` no vacío → devuelve el dict
- Cualquier otro tipo → `_SENTINEL` + error en log

---

## 7. sender.py

**Responsabilidad:** registro del dispositivo, construcción del payload y envío al backend con reintentos.

### `_ssl_context(verify)`

Helper que devuelve un `ssl.SSLContext` configurado según el flag `verify_ssl` de la configuración:

```python
if verify:
    return ssl.create_default_context()   # Producción
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE           # POC con certificado autofirmado
return ctx
```

Usado en todas las llamadas HTTP del módulo.

### `register_device(config)`

Llama a `POST /api/devices/register` con el hostname del equipo. No requiere autenticación (Opción A — POC).

Gestiona explícitamente el error 409: si el backend devuelve `Conflict`, significa que el hostname ya existe pero la `api_key` se perdió del `config.json` — situación que requiere intervención manual.

**Retorna:** la `api_key` en claro si el registro fue exitoso, `None` en cualquier otro caso.

### `build_payload(metrics, config)`

Construye el payload según el contrato §2.3:

```json
{
  "device_id": "HOSTNAME",
  "timestamp": "2026-04-08T11:34:13Z",
  "agent_version": "1.0.0",
  "username": "usuario@dominio",
  "metrics": { ... }
}
```

El timestamp usa `strftime("%Y-%m-%dT%H:%M:%SZ")` — formato exacto exigido por el contrato, sin microsegundos.

### `send_payload(payload, config)`

Serializa el payload a JSON y lo envía con reintentos. Política:

- Hasta `config.retry_attempts` intentos (por defecto 3).
- `config.retry_wait_seconds` de espera entre intentos (por defecto 30s).
- Timeout total por intento: `timeout_connect + timeout_read` (por defecto 15s).

**Retorna:** `True` si algún intento fue exitoso, `False` si todos fallaron.

### `_http_post(url, headers, body, config)`

Realiza la petición HTTP usando `urllib` de la biblioteca estándar — sin dependencias externas, compatible con PyInstaller.

**Retorna:** `(True, "")` si la respuesta es 2xx, `(False, mensaje_error)` en cualquier otro caso.

---

## 8. main.py

**Responsabilidad:** punto de entrada del agente. Orquesta todos los módulos y gestiona el ciclo de vida completo de cada ejecución.

### Funciones auxiliares

**`_already_ran_today(data_dir)`**

Lee `last_run.json` y compara la fecha almacenada con la fecha actual. Si el fichero no existe, está corrupto o la fecha es distinta, devuelve `False` y el agente continúa. Ante cualquier error de lectura también devuelve `False` — es más seguro ejecutar de más que de menos.

**`_update_last_run(data_dir)`**

Escribe `last_run.json` con la fecha y timestamp UTC del envío exitoso:

```json
{
  "last_successful_run_date": "2026-04-08",
  "last_successful_run_ts": "2026-04-08T11:34:13+00:00"
}
```

Solo se llama si el envío al backend fue exitoso.

**`_save_api_key(config_path, api_key)`**

Lee `config.json`, actualiza solo el campo `api_key` y lo escribe de vuelta preservando el resto de campos. Diseñada para ser lo menos destructiva posible ante un fallo de escritura.

### `main()`

Flujo completo con 8 pasos numerados en el código. Códigos de salida:

| Código | Cuándo |
|---|---|
| `0` | Envío completado correctamente |
| `1` | Error de configuración, registro fallido o ningún plugin cargó |
| `2` | Ya se ejecutó hoy |
| `3` | Envío fallido tras todos los reintentos |

**Paso 3 — Auto-registro:** si `config.api_key` está vacía, llama a `register_device()`. Si la key llega pero no se puede persistir en disco (error de permisos, etc.), continúa igualmente con la key en memoria para no perder la ejecución del día — el próximo arranque intentará el registro de nuevo.

---

## 9. config.json — referencia de campos

```json
{
  "agent_version": "1.0.0",
  "auto_update": false,
  "api_key": "",
  "verify_ssl": false,
  "enabled_plugins": ["battery", "software_usage", "boot_time"],
  "api_url": "https://ehukene.dominio.local/api",
  "retry_attempts": 3,
  "retry_wait_seconds": 30,
  "timeout_connect": 5,
  "timeout_read": 10,
  "data_dir": "C:\\ProgramData\\EHUkene"
}
```

| Campo | Obligatorio | Descripción |
|---|---|---|
| `agent_version` | Sí | Versión del agente. Se incluye en cada payload enviado al backend. |
| `auto_update` | No | Reservado para Fase 2. Sin efecto en Fase 1. |
| `api_key` | No | Vacía en el despliegue inicial. El agente la rellena tras el auto-registro y la persiste aquí. |
| `verify_ssl` | No | `false` en POC con certificado autofirmado. `true` en producción. |
| `enabled_plugins` | Sí | Lista de plugins a ejecutar. Cada nombre debe coincidir con un fichero `.py` en `agent/plugins/`. |
| `api_url` | Sí | URL base del backend sin barra final. Debe usar `https://`. |
| `retry_attempts` | No | Número de reintentos si el envío falla. Por defecto `3`. |
| `retry_wait_seconds` | No | Segundos de espera entre reintentos. Por defecto `30`. |
| `timeout_connect` | No | Timeout de conexión HTTP en segundos. Por defecto `5`. |
| `timeout_read` | No | Timeout de lectura HTTP en segundos. Por defecto `10`. |
| `data_dir` | No | Directorio donde el agente escribe `agent.log` y `last_run.json`. Por defecto `C:\ProgramData\EHUkene`. |
