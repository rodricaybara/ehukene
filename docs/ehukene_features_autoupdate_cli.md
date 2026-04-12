# EHUkene — Features: Auto-actualización y CLI de diagnóstico
## Documento de análisis y diseño

**Versión:** 1.0  
**Estado:** Propuesta  
**Fecha:** 2026-03-29  
**Relacionado con:** Documento técnico principal v1.0

---

## 1. Resumen ejecutivo

Este documento analiza dos nuevas funcionalidades propuestas para el sistema EHUkene:

- **Auto-actualización del agente:** capacidad del agente para actualizarse a sí mismo (core y plugins) sin intervención manual en cada endpoint.
- **CLI de diagnóstico (`agentcli`):** herramienta de línea de comandos para que el técnico pueda inspeccionar el estado del agente, ejecutar plugins de forma manual y verificar la conectividad con el backend.

Ambas features son compatibles entre sí, encajan con las decisiones de diseño existentes (mantenibilidad, Python, PyInstaller) y se propone incorporarlas a partir de la Fase 2 del roadmap.

---

## 2. Feature: Auto-actualización del agente

### 2.1 Motivación

Con un parque de ~7.000 equipos, actualizar el agente o sus plugins mediante despliegue manual vía Ivanti EPM es viable pero lento. La auto-actualización permite que cada agente se mantenga al día de forma autónoma, reduciendo la carga operativa y acortando el tiempo de propagación de nuevas versiones o correcciones.

### 2.2 Alcance

Se distinguen dos tipos de actualización con necesidades técnicas distintas:

| Tipo | Complejidad | Fase |
|---|---|---|
| Actualización de plugins (`.py`) | Baja | Fase 2 |
| Actualización del core (`.exe`) | Media | Fase 3 |

#### Plugins

Los plugins son ficheros `.py` independientes cargados dinámicamente por `plugin_loader.py`. Pueden reemplazarse en disco sin tocar el ejecutable principal. El agente descarga el nuevo fichero, verifica su integridad y en la siguiente ejecución lo carga automáticamente.

#### Core

El ejecutable empaquetado con PyInstaller no puede sobreescribirse a sí mismo mientras está en ejecución (limitación de Windows). La solución es un segundo ejecutable auxiliar, `updater.exe`, que actúa como intermediario: el agente detecta la nueva versión, descarga el ejecutable nuevo, lanza el updater y termina. El updater espera a que el agente haya terminado, reemplaza el ejecutable y puede relanzarlo si procede.

### 2.3 Diseño — Backend

Se añade un nuevo endpoint al backend:

```
GET /api/agent/version
```

No requiere API Key (es público pero solo accesible vía HTTPS). Devuelve el manifiesto de versiones actual:

```json
{
  "core_version": "1.2.0",
  "core_download_url": "https://ehukene.dominio.local/dist/agent-1.2.0.exe",
  "core_checksum_sha256": "a3f1...",
  "plugins": {
    "battery": {
      "version": "1.1.0",
      "url": "https://ehukene.dominio.local/dist/plugins/battery-1.1.0.py",
      "checksum_sha256": "c8d2..."
    },
    "software_usage": {
      "version": "1.0.3",
      "url": "https://ehukene.dominio.local/dist/plugins/software_usage-1.0.3.py",
      "checksum_sha256": "e91a..."
    },
    "boot_time": {
      "version": "1.0.0",
      "url": "https://ehukene.dominio.local/dist/plugins/boot_time-1.0.0.py",
      "checksum_sha256": "b47f..."
    }
  }
}
```

### 2.4 Diseño — Agente

#### Flujo de ejecución con auto-update

```
Inicio de sesión → Task Scheduler lanza agent.exe
        ↓
  Consulta GET /api/agent/version
        ↓
  ¿Hay plugins nuevos?
     Sí → Descarga, verifica checksum, reemplaza fichero .py
     No → Continúa
        ↓
  ¿Hay core nuevo?
     Sí → Descarga agent-X.Y.Z.exe, verifica checksum
           → Lanza updater.exe y termina
     No → Continúa con ejecución normal
        ↓
  Recogida de métricas y envío al backend
```

#### Cambios en `config.json`

```json
{
  "agent_version": "1.1.0",
  "auto_update": true,
  "enabled_plugins": ["battery", "software_usage", "boot_time"],
  "api_url": "https://ehukene.dominio.local/api",
  "api_key": "KEY_DEL_DISPOSITIVO"
}
```

El campo `agent_version` es la versión instalada actualmente. Se compara con `core_version` del manifiesto para determinar si hay actualización disponible.

#### Nuevo módulo: `core/updater.py`

```python
def check_updates(manifest_url: str) -> dict:
    """Consulta el manifiesto de versiones y devuelve qué hay que actualizar."""
    ...

def update_plugin(plugin_name: str, url: str, checksum: str) -> bool:
    """Descarga un plugin, verifica su integridad y lo reemplaza en disco."""
    ...

def schedule_core_update(url: str, checksum: str) -> bool:
    """Descarga el nuevo core y lanza updater.exe para aplicarlo."""
    ...
```

#### Nuevo ejecutable auxiliar: `updater.exe`

Binario mínimo e independiente (también empaquetado con PyInstaller). Su única función:

1. Esperar a que `agent.exe` haya terminado (polling del proceso).
2. Reemplazar `agent.exe` con la nueva versión descargada.
3. Guardar copia de la versión anterior como `agent.exe.bak` durante 48h (para rollback).
4. Opcionalmente relanzar el agente si la actualización fue forzada manualmente.

### 2.5 Estructura de directorios actualizada

```
agent/
├── core/
│   ├── main.py
│   ├── collector.py
│   ├── sender.py
│   ├── config.py
│   ├── plugin_loader.py
│   └── updater.py          # NUEVO — lógica de auto-update
│
├── updater/
│   └── updater_main.py     # NUEVO — punto de entrada del updater auxiliar
│
├── plugins/
│   ├── battery.py
│   ├── software_usage.py
│   ├── boot_time.py
│   └── custom_*.py
│
├── config.json
└── requirements.txt
```

### 2.6 Seguridad

- La descarga siempre se realiza por HTTPS (garantizado por la arquitectura existente).
- Antes de aplicar cualquier fichero descargado se verifica su checksum SHA256. Si no coincide, se descarta y se registra el error en el log local.
- El `updater.exe` solo acepta ejecutables firmados digitalmente si se dispone de certificado de firma de código (recomendado para Fase 3).
- Los ficheros descargados se almacenan temporalmente en un directorio de trabajo propio del agente, nunca en rutas compartidas.

### 2.7 Permisos

| Operación | Privilegios necesarios |
|---|---|
| Actualización de plugins | Usuario estándar (si el directorio de plugins es accesible) |
| Actualización del core en `Program Files` | Administrador local |
| Actualización del core en directorio de usuario | Usuario estándar |

Si el agente se ejecuta sin privilegios elevados, la actualización del core debe delegarse en Ivanti EPM o gestionarse mediante una tarea programada con credenciales de administrador.

### 2.8 Rollback

- El updater conserva `agent.exe.bak` durante 48 horas tras una actualización.
- Si el agente nuevo no contacta con el backend en las primeras 2 ejecuciones, el updater puede detectarlo y restaurar la versión anterior.
- Los plugins reemplazados también se conservan con extensión `.bak` durante el mismo período.

---

## 3. Feature: CLI de diagnóstico (`agentcli`)

### 3.1 Motivación

El técnico de sistemas no tiene actualmente forma de verificar el estado del agente en un equipo concreto sin revisar logs o forzar un reinicio de sesión. El `agentcli` proporciona una interfaz de diagnóstico directa, sin necesidad de acceder al backend ni interpretar ficheros de log manualmente.

### 3.2 Principio de diseño

> El CLI no tiene lógica propia. Es una capa de presentación que reutiliza exactamente el mismo código que el agente. Si el CLI y el agente divergen, el diagnóstico deja de ser representativo.

`agentcli.exe` se genera con PyInstaller desde el mismo codebase, importando los mismos módulos (`collector.py`, `plugin_loader.py`, `sender.py`, `config.py`). No duplica ninguna lógica.

### 3.3 Comandos

| Comando | Descripción |
|---|---|
| `agentcli version` | Versión del core y de todos los plugins cargados |
| `agentcli status` | Estado general: última ejecución, último envío, configuración activa |
| `agentcli run <plugin>` | Ejecuta un plugin y muestra el resultado en pantalla |
| `agentcli run --all` | Ejecuta todos los plugins habilitados |
| `agentcli check` | Verifica la conectividad con el backend (sin enviar datos) |
| `agentcli send` | Fuerza un envío inmediato ignorando el control de duplicados diario |
| `agentcli logs [--lines N]` | Muestra las últimas N líneas del log local (por defecto 20) |

### 3.4 Ejemplos de salida

#### `agentcli version`

```
EHUkene Agent — Diagnóstico
══════════════════════════════════════════════
Core version    : 1.1.0
Config          : C:\Program Files\EHUkene\config.json
API URL         : https://ehukene.dominio.local/api
Device ID       : HOSTNAME-001
Auto-update     : habilitado

Plugins cargados:
  [✓] battery         v1.1.0
  [✓] software_usage  v1.0.3
  [✓] boot_time       v1.0.0
  [✗] disk_trend      — no habilitado en config
```

#### `agentcli status`

```
Estado del agente
══════════════════════════════════════════════
Último envío exitoso    : 2026-03-28T08:15:00
Resultado               : OK (HTTP 200)
Próximo envío           : al próximo inicio de sesión
Versión instalada       : 1.1.0
Versión disponible      : 1.1.0 (sin actualizaciones pendientes)
```

#### `agentcli run battery`

```
Ejecutando plugin: battery
──────────────────────────────────────────────
battery_design_capacity      : 45000 mWh
battery_full_charge_capacity : 32850 mWh
battery_health_percent       : 73.0 %
battery_status               : 2 (Discharging)

Plugin completado en 0.34s — sin errores
```

#### `agentcli run --all`

```
Ejecutando todos los plugins habilitados
──────────────────────────────────────────────
[✓] battery          0.34s
[✓] software_usage   0.61s
[✓] boot_time        0.22s

Resultado consolidado:
{
  "battery": { "battery_health_percent": 73.0, "battery_status": 2 },
  "software_usage": { "acrobat_installed": true, "acrobat_version": "24.0.0", ... },
  "boot_time": { "last_boot_time": "2026-03-28T07:58:00", "boot_duration_seconds": 42 }
}
```

#### `agentcli check`

```
Verificando conectividad con el backend
──────────────────────────────────────────────
  Resolución DNS   ehukene.dominio.local     [✓]
  HTTPS GET /api/agent/version              [✓] 200 OK  (142ms)
  API Key                                   [✓] válida
  Certificado SSL                           [✓] válido hasta 2027-01-15

Todo correcto. El agente puede conectar con el backend.
```

#### `agentcli send`

```
Forzando envío de métricas...
──────────────────────────────────────────────
Recogiendo datos...  [✓]
Enviando al backend... [✓] HTTP 200

Envío completado. Registro de último envío actualizado.
```

### 3.5 Estructura de directorios actualizada

```
agent/
├── core/
│   └── ...  (sin cambios)
│
├── cli/
│   └── main_cli.py         # NUEVO — punto de entrada del CLI
│
├── updater/
│   └── updater_main.py
│
├── plugins/
│   └── ...  (sin cambios)
│
├── config.json
└── requirements.txt
```

### 3.6 Compilación con PyInstaller

Se generan dos ejecutables desde el mismo codebase:

```bash
# Agente principal (sin cambios)
pyinstaller --onefile core/main.py -n agent.exe

# CLI de diagnóstico
pyinstaller --onefile cli/main_cli.py -n agentcli.exe

# Updater auxiliar
pyinstaller --onefile updater/updater_main.py -n updater.exe
```

### 3.7 Permisos y modo de uso

El CLI requiere los mismos permisos que el agente para que el diagnóstico sea fiel. Si el agente se ejecuta en un contexto elevado, el técnico debe lanzar `agentcli.exe` desde una consola con privilegios de administrador para obtener resultados equivalentes.

El `agentcli send` registra el envío en el log local exactamente igual que un envío normal del agente, para no corromper el control de duplicados diario.

### 3.8 Distribución

`agentcli.exe` no tiene sentido desplegarlo en los 7.000 endpoints. Se distribuye únicamente en los equipos donde los técnicos lo necesiten, o se comparte directamente entre el equipo de sistemas. No tiene efectos secundarios si se copia y ejecuta en cualquier equipo donde ya esté instalado el agente (comparte el mismo `config.json`).

---

## 4. Interacción entre ambas features

En Fase 3, el `agentcli` puede incorporar un comando de actualización manual:

```
agentcli update          # Comprueba si hay actualizaciones disponibles y las aplica
agentcli update --check  # Solo informa, no aplica nada
```

Esto permite al técnico validar el mecanismo de auto-update en un equipo concreto de forma controlada antes de dejarlo funcionar de forma autónoma en el parque completo.

---

## 5. Impacto en el roadmap

### Fase 2 — Producción básica (adiciones)

- [ ] Auto-actualización de plugins (`core/updater.py`)
- [ ] Endpoint `GET /api/agent/version` en el backend
- [ ] `agentcli.exe` con comandos `version`, `status`, `run`, `check`, `send`, `logs`

### Fase 3 — Madurez (adiciones)

- [ ] Auto-actualización del core (`updater.exe`)
- [ ] Rollback automático tras actualización fallida
- [ ] Firma digital de ejecutables distribuidos
- [ ] `agentcli update` — actualización manual desde el CLI

---

## 6. Decisiones de diseño — Adiciones al resumen

| Decisión | Elección | Motivo |
|---|---|---|
| Actualización de plugins | Descarga directa + checksum | Simple, sin dependencias externas |
| Actualización del core | Updater auxiliar independiente | Windows no permite sobreescribir el propio proceso |
| CLI | Segundo ejecutable, código compartido | Sin duplicación de lógica, diagnóstico fiel |
| Distribución del CLI | Solo en equipos de técnicos | No aporta valor en endpoints de usuario final |
| Verificación de integridad | SHA256 pre-aplicación | Seguridad mínima necesaria ante descarga remota de ejecutables |
