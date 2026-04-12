# EHUkene — Mini Neurons
## Documento Técnico de Desarrollo

**Versión:** 1.0  
**Estado:** POC  
**Fecha:** 2026-03-28

---

## 1. Contexto y objetivo

EHUkene es un sistema ligero de telemetría e inventario para equipos Windows. Su propósito es **complementar Ivanti EPM**, cubriendo puntos ciegos que la herramienta no alcanza, sin sustituirla en ninguna de sus funciones actuales.

El sistema recoge métricas específicas, las almacena históricamente y las expone mediante dashboards para apoyar decisiones operativas y económicas.

### 1.1 Casos de uso — POC

| Prioridad | Métrica | Valor operativo |
|---|---|---|
| 1 | Degradación de batería | Planificación de reposición de hardware |
| 2 | Uso de Adobe Acrobat Pro | Optimización y reducción de licencias |
| 3 | Tiempo de arranque del sistema | Indicador de salud del equipo |

### 1.2 Casos de uso — Fases posteriores

- Antigüedad de hardware con alertas de renovación
- Tendencia de ocupación de disco (proyección)

---

## 2. Arquitectura general

```
[ Agente Windows ]
        ↓ HTTPS / JSON  (una vez al día, en inicio de sesión)
[ API Backend — FastAPI ]
        ↓
[ Base de datos — PostgreSQL ]
        ↓
[ Visualización — Grafana / Metabase ]
```

El agente se ejecuta en el inicio de sesión del usuario mediante **Task Scheduler**. No requiere servicio Windows en la POC.

---

## 3. Agente Windows

### 3.1 Tecnología

- **Lenguaje:** Python
- **Criterio de elección:** Mantenibilidad. El código debe poder ser mantenido por una persona con conocimiento medio de Python sin coste elevado.
- **Distribución:** Ejecutable empaquetado con PyInstaller (sin dependencia de runtime Python en el endpoint)

### 3.2 Estructura de directorios

```
agent/
├── core/
│   ├── main.py            # Punto de entrada
│   ├── collector.py       # Orquesta la ejecución de plugins
│   ├── sender.py          # Envío de datos al backend
│   ├── config.py          # Lectura de configuración
│   └── plugin_loader.py   # Carga dinámica de plugins
│
├── plugins/
│   ├── battery.py         # Degradación de batería
│   ├── software_usage.py  # Uso de Adobe Acrobat Pro
│   ├── boot_time.py       # Tiempo de arranque
│   └── custom_*.py        # Futuros plugins
│
├── config.json            # Configuración local del agente
└── requirements.txt
```

### 3.3 Sistema de plugins

Cada plugin es un módulo Python independiente que implementa una única función:

```python
def collect() -> dict:
    return {
        "metric_name": value
    }
```

El `plugin_loader.py` lee el directorio `/plugins` y ejecuta los que estén habilitados en `config.json`. Los fallos en un plugin no afectan al resto.

**Activación por configuración:**

```json
{
  "enabled_plugins": ["battery", "software_usage", "boot_time"],
  "api_url": "https://ehukene.dominio.local/api",
  "api_key": "KEY_DEL_DISPOSITIVO"
}
```

### 3.4 Plugins — Detalle técnico

#### Plugin: battery

Fuente de datos: WMI — clase `Win32_Battery`

Métricas recogidas:
- `battery_design_capacity` — capacidad original en mWh
- `battery_full_charge_capacity` — capacidad actual máxima en mWh
- `battery_health_percent` — porcentaje calculado: `(full / design) * 100`
- `battery_status` — estado actual (cargando, descargando, etc.)

```python
import wmi

def collect():
    c = wmi.WMI()
    battery = c.Win32_Battery()[0]
    design = battery.DesignCapacity or 1
    full = battery.FullChargeCapacity or 0
    return {
        "battery_design_capacity": design,
        "battery_full_charge_capacity": full,
        "battery_health_percent": round((full / design) * 100, 1),
        "battery_status": battery.BatteryStatus
    }
```

> **Nota:** En equipos de sobremesa sin batería, el plugin debe capturar la excepción y devolver `None` para ser ignorado por el collector.

---

#### Plugin: software_usage

Fuente de datos: Visor de eventos de Windows — registro de aplicaciones y WMI para procesos activos.

Métricas recogidas:
- `acrobat_installed` — booleano
- `acrobat_version` — versión instalada
- `acrobat_last_execution` — fecha/hora del último uso (desde registro de eventos o prefetch)
- `acrobat_executions_last_30d` — número de ejecuciones en los últimos 30 días

```python
import winreg
from datetime import datetime, timedelta
import subprocess

def collect():
    installed = False
    version = None
    last_exec = None
    exec_count = 0

    # Verificar instalación en el registro
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Adobe\Adobe Acrobat\DC\Installer")
        version = winreg.QueryValueEx(key, "ProductVersion")[0]
        installed = True
    except FileNotFoundError:
        pass

    # Consultar prefetch para uso real
    # (lógica de lectura de prefetch o eventos de aplicación)

    return {
        "acrobat_installed": installed,
        "acrobat_version": version,
        "acrobat_last_execution": last_exec,
        "acrobat_executions_last_30d": exec_count
    }
```

> **Nota:** La lectura del prefetch requiere permisos de administrador. Evaluar si el agente se ejecuta con privilegios elevados o si se usa una alternativa (eventos del sistema, registro de MRU).

---

#### Plugin: boot_time

Fuente de datos: Visor de eventos de Windows — Event ID 6005 (inicio del servicio de eventos) y Event ID 100 del canal `Microsoft-Windows-Diagnostics-Performance`.

Métricas recogidas:
- `last_boot_time` — timestamp del último arranque
- `boot_duration_seconds` — duración del arranque en segundos

```python
import wmi
from datetime import datetime

def collect():
    c = wmi.WMI()
    os_info = c.Win32_OperatingSystem()[0]
    last_boot = os_info.LastBootUpTime

    # LastBootUpTime viene en formato WMI: "20260328080000.000000+060"
    boot_dt = datetime.strptime(last_boot[:14], "%Y%m%d%H%M%S")

    return {
        "last_boot_time": boot_dt.isoformat(),
        "boot_duration_seconds": None  # A completar con Event ID 100
    }
```

---

### 3.5 Payload de envío

El `sender.py` consolida la salida de todos los plugins y la envía al backend:

```json
{
  "device_id": "HOSTNAME-001",
  "timestamp": "2026-03-28T08:15:00Z",
  "username": "usuario@dominio.local",
  "metrics": {
    "battery": {
      "battery_health_percent": 73.4,
      "battery_status": 2
    },
    "software_usage": {
      "acrobat_installed": true,
      "acrobat_version": "24.0.0",
      "acrobat_last_execution": "2026-03-20T10:30:00",
      "acrobat_executions_last_30d": 3
    },
    "boot_time": {
      "last_boot_time": "2026-03-28T07:58:00",
      "boot_duration_seconds": 42
    }
  }
}
```

### 3.6 Ejecución

**Mecanismo:** Windows Task Scheduler  
**Trigger:** Al inicio de sesión del usuario  
**Usuario de ejecución:** Usuario actual (sin privilegios elevados, salvo que algún plugin lo requiera)  
**Frecuencia:** Una vez al día  
**Control de duplicados:** El agente registra localmente la fecha del último envío exitoso y no vuelve a enviar si ya lo hizo en el día en curso.

---

## 4. Backend API

### 4.1 Tecnología

- **Framework:** FastAPI (Python)
- **Servidor:** Uvicorn + NGINX como reverse proxy
- **Autenticación:** API Key por dispositivo en cabecera HTTP

### 4.2 Endpoints

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/api/telemetry` | Recepción de métricas del agente |
| `GET` | `/api/devices` | Listado de dispositivos registrados |
| `GET` | `/api/devices/{device_id}` | Detalle de un dispositivo |
| `GET` | `/api/devices/{device_id}/history` | Histórico de métricas |
| `POST` | `/api/devices/register` | Registro inicial de un dispositivo nuevo |

### 4.3 Autenticación

Cada dispositivo tiene una API Key única. Se envía en la cabecera de cada petición:

```
X-API-Key: KEY_DEL_DISPOSITIVO
```

El backend valida la key contra la base de datos antes de procesar cualquier petición. Keys inválidas devuelven `401 Unauthorized`.

### 4.4 Validación de payload

FastAPI valida el payload de entrada mediante modelos Pydantic. Cualquier campo inesperado o tipo incorrecto es rechazado con `422 Unprocessable Entity` antes de tocar la base de datos.

### 4.5 Seguridad

- HTTPS obligatorio (certificado gestionado por NGINX)
- Rate limiting por IP y por API Key
- Logging de todos los accesos (IP, device_id, timestamp, código de respuesta)
- Rotación de API Keys sin downtime (soporte de key antigua durante período de gracia)

---

## 5. Base de datos

### 5.1 Tecnología

- **Motor:** PostgreSQL
- **Justificación:** Suficiente para el volumen esperado (7.000 equipos × 1 registro/día). TimescaleDB descartado por innecesario en este escenario.

### 5.2 Modelo de datos

#### Tabla: `devices`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `UUID` | Identificador único |
| `hostname` | `VARCHAR` | Nombre del equipo |
| `api_key_hash` | `VARCHAR` | Hash de la API Key |
| `first_seen` | `TIMESTAMP` | Primera conexión |
| `last_seen` | `TIMESTAMP` | Última conexión |
| `active` | `BOOLEAN` | Si el dispositivo está activo |

#### Tabla: `telemetry_raw`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `BIGSERIAL` | Identificador |
| `device_id` | `UUID` | Referencia a `devices` |
| `timestamp` | `TIMESTAMP` | Momento del registro |
| `payload` | `JSONB` | Métricas completas en JSON |

> El uso de `JSONB` permite almacenar el payload completo sin necesidad de alterar el esquema al añadir nuevos plugins.

#### Tabla: `battery_metrics`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `BIGSERIAL` | Identificador |
| `device_id` | `UUID` | Referencia a `devices` |
| `timestamp` | `TIMESTAMP` | Momento del registro |
| `health_percent` | `NUMERIC(5,2)` | Salud de la batería |
| `battery_status` | `SMALLINT` | Estado de la batería |

#### Tabla: `software_usage`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `BIGSERIAL` | Identificador |
| `device_id` | `UUID` | Referencia a `devices` |
| `timestamp` | `TIMESTAMP` | Momento del registro |
| `software_name` | `VARCHAR` | Nombre del software |
| `version` | `VARCHAR` | Versión instalada |
| `last_execution` | `TIMESTAMP` | Último uso |
| `executions_30d` | `INTEGER` | Ejecuciones últimos 30 días |

#### Tabla: `boot_metrics`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `BIGSERIAL` | Identificador |
| `device_id` | `UUID` | Referencia a `devices` |
| `timestamp` | `TIMESTAMP` | Momento del registro |
| `last_boot_time` | `TIMESTAMP` | Arranque del sistema |
| `boot_duration_seconds` | `INTEGER` | Duración del arranque |

### 5.3 Índices

```sql
CREATE INDEX idx_battery_device_time ON battery_metrics (device_id, timestamp DESC);
CREATE INDEX idx_software_device_name ON software_usage (device_id, software_name);
CREATE INDEX idx_boot_device_time ON boot_metrics (device_id, timestamp DESC);
```

### 5.4 Retención de datos

- Datos detallados: 12 meses
- Agregados mensuales: indefinido
- Implementar `pg_partman` para particionado automático por mes si el volumen crece

---

## 6. Acceso externo

Para equipos fuera de la red corporativa:

- API expuesta en puerto 443 vía NGINX
- Certificado SSL válido (Let's Encrypt o corporativo)
- Firewall con whitelist de IPs si es posible, o rate limiting estricto si no

NGINX actúa como reverse proxy hacia FastAPI en localhost. El agente siempre apunta a la misma URL pública independientemente de si el equipo está dentro o fuera de la red.

---

## 7. Visualización

| Herramienta | Uso principal |
|---|---|
| **Grafana** | Evolución temporal de métricas (batería, boot time) |
| **Metabase** | Informes de negocio (licencias Acrobat, equipos por estado) |

Ambas se conectan directamente a PostgreSQL como fuente de datos.

### 7.1 Dashboards previstos para la POC

- **Salud de baterías:** mapa de calor por equipo, distribución por rangos (>80%, 50-80%, <50%)
- **Licencias Acrobat Pro:** equipos con Acrobat instalado vs. usándolo activamente en los últimos 30 días
- **Tiempo de arranque:** ranking de equipos más lentos, evolución temporal por equipo

---

## 8. Consideraciones LOPD

Los datos recogidos (hostname, usuario, métricas de uso de software) son datos de actividad de empleados. No se requiere implementación técnica compleja, pero sí dejar constancia mínima interna:

- **Qué se recoge:** métricas de hardware y uso de software corporativo
- **Para qué:** gestión del parque informático y optimización de licencias
- **Quién tiene acceso:** equipo de sistemas
- **Cuánto tiempo se retiene:** 12 meses de datos detallados

---

## 9. Roadmap

### Fase 1 — POC
- [ ] Agente con los tres plugins iniciales (batería, Acrobat, boot time)
- [ ] Backend FastAPI con endpoint `/api/telemetry`
- [ ] Base de datos PostgreSQL con esquema inicial
- [ ] Dashboard básico en Grafana o Metabase

### Fase 2 — Producción básica
- [ ] Empaquetado del agente con PyInstaller
- [ ] Despliegue vía Ivanti EPM
- [ ] Seguridad completa (HTTPS, API Keys, rate limiting)
- [ ] Acceso externo (NGINX + firewall)

### Fase 3 — Madurez
- [ ] Alertas automáticas (baterías por debajo de umbral, equipos sin uso de Acrobat)
- [ ] Particionado de base de datos
- [ ] Rotación automática de API Keys
- [ ] Nuevos plugins: antigüedad de hardware, tendencia de disco

---

## 10. Decisiones de diseño — Resumen

| Decisión | Elección | Motivo |
|---|---|---|
| Lenguaje del agente | Python | Mantenibilidad |
| Arquitectura del agente | Plugins desacoplados | Extensibilidad sin tocar el core |
| Frecuencia de recogida | 1 vez al día | Suficiente para los casos de uso |
| Trigger de ejecución | Task Scheduler (inicio de sesión) | Simplicidad en POC |
| Backend | FastAPI | Ligero, tipado, bien documentado |
| Base de datos | PostgreSQL | Suficiente para el volumen real |
| Series temporales | PostgreSQL estándar | TimescaleDB innecesario a este volumen |
| Payload flexible | JSONB en `telemetry_raw` | Permite añadir plugins sin cambiar esquema |
| Autenticación | API Key por dispositivo | Simple y suficiente |
