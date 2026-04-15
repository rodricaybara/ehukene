# Health Monitor Plugin

**Versión:** 1.1.0  
**Tipo:** Core Metrics Plugin  
**Plataforma:** Windows 10/11 (corporativo)  
**Frecuencia:** Diaria  
**Autor:** EHUkene Development Team  
**Última actualización:** 2026-04-15

---

## 📋 Tabla de Contenidos

1. [Descripción General](#descripción-general)
2. [Métricas Recopiladas](#métricas-recopiladas)
3. [Configuración](#configuración)
4. [Estructura de Salida](#estructura-de-salida)
5. [Criterios de Estado](#criterios-de-estado)
6. [Limitaciones Conocidas](#limitaciones-conocidas)
7. [Troubleshooting](#troubleshooting)
8. [Changelog](#changelog)

---

## Descripción General

El **Health Monitor Plugin** es un componente de monitorización integral diseñado para evaluar el estado de salud de equipos Windows corporativos. Recopila 8 métricas críticas del sistema y proporciona una evaluación de estado basada en umbrales configurables.

### Principio de Diseño

**Fiabilidad sobre precisión.** El plugin está diseñado para funcionar en entornos corporativos restrictivos donde:

- Los Performance Counters pueden no estar accesibles
- Las GPOs bloquean scripts no firmados
- La conectividad VPN es intermitente
- Los permisos de usuario son limitados

### Arquitectura

```
health_monitor.py
├── Configuración (health_monitor_config.json)
├── 8 Métricas Independientes
│   ├── CPU Load
│   ├── Memory Usage
│   ├── Disk Space
│   ├── Event Log
│   ├── Domain Status
│   ├── Uptime
│   ├── Boot Time
│   └── Services
└── Output JSON (health_monitor)
```

Cada métrica se ejecuta de forma aislada con su propio manejo de errores. Si una métrica falla, las demás continúan su ejecución.

---

## Métricas Recopiladas

### 1. CPU Load (`cpu`)

**Fuente:** `Get-CimInstance Win32_Processor | Select-Object LoadPercentage`

**Descripción:** Porcentaje de carga de CPU en el momento de la ejecución.

**Campos:**
- `load_percentage` (int, 0-100): Porcentaje de uso de CPU
- `status` (str): `ok`, `warning`, `critical`, `error`
- `error_msg` (str|null): Mensaje de error si falla la métrica

**Thresholds por defecto:**
- `ok`: < 75%
- `warning`: 75-89%
- `critical`: ≥ 90%

**Ejemplo:**
```json
{
  "load_percentage": 45,
  "status": "ok",
  "error_msg": null
}
```

---

### 2. Memory Usage (`memory`)

**Fuente:** `Get-CimInstance Win32_OperatingSystem`

**Descripción:** Uso de memoria RAM del sistema.

**Campos:**
- `total_kb` (int): Memoria total en KB
- `free_kb` (int): Memoria libre en KB
- `usage_pct` (float, 0.00-100.00): Porcentaje de uso calculado
- `status` (str): `ok`, `warning`, `critical`, `error`
- `error_msg` (str|null): Mensaje de error

**Cálculo:**
```
usage_pct = ((total_kb - free_kb) / total_kb) * 100
```

**Thresholds por defecto:**
- `ok`: < 80%
- `warning`: 80-89%
- `critical`: ≥ 90%

**Ejemplo:**
```json
{
  "total_kb": 8388608,
  "free_kb": 2097152,
  "usage_pct": 75.00,
  "status": "ok",
  "error_msg": null
}
```

---

### 3. Disk Space (`disk`)

**Fuente:** `Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$env:SystemDrive'"`

**Descripción:** Espacio disponible en el disco del sistema (normalmente C:).

**Campos:**
- `drive` (str): Letra de unidad (ej: "C:")
- `total_gb` (float): Capacidad total en GB
- `free_gb` (float): Espacio libre en GB
- `free_pct` (float, 0.00-100.00): Porcentaje libre
- `status` (str): `ok`, `warning`, `critical`, `error`
- `error_msg` (str|null): Mensaje de error

**Thresholds por defecto:**
- `ok`: > 20% libre
- `warning`: 10-20% libre
- `critical`: < 10% libre

**Ejemplo:**
```json
{
  "drive": "C:",
  "total_gb": 238.47,
  "free_gb": 15.62,
  "free_pct": 6.55,
  "status": "critical",
  "error_msg": null
}
```

---

### 4. Event Log (`events`)

**Fuente:** `Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2}`

**Descripción:** Eventos críticos y de error del Event Log del sistema (últimas 24h). Filtrado triple:

1. **Filtrado por Provider + EventID** (whitelist de ruido conocido)
2. **Filtrado por combinaciones** específicas (ej: DistributedCOM + 10016)
3. **Eventos sin mensaje** (reducción de ruido adicional)

**Campos:**
- `critical_count` (int): Eventos de nivel Critical
- `error_count` (int): Eventos de nivel Error
- `filtered_count` (int): Total de eventos filtrados (ruido descartado)
- `top_sources` (array): Top 5 providers por frecuencia
  - `provider` (str): Nombre del provider
  - `count` (int): Número de eventos
- `sample_events` (array): Hasta 5 eventos de muestra
  - `event_id` (int): ID del evento
  - `provider` (str): Provider/Source
  - `level` (str): "Critical" o "Error"
  - `time_created` (str, ISO 8601 UTC): Timestamp del evento
- `status` (str): `ok`, `warning`, `critical`, `error`
- `error_msg` (str|null): Mensaje de error

**Thresholds por defecto:**
- `ok`: ≤ 5 eventos
- `warning`: 6-10 eventos
- `critical`: > 10 eventos

**Ejemplo:**
```json
{
  "critical_count": 0,
  "error_count": 4,
  "filtered_count": 25,
  "top_sources": [
    {"provider": "Microsoft-Windows-WindowsUpdateClient", "count": 2},
    {"provider": "DCOM", "count": 1}
  ],
  "sample_events": [
    {
      "event_id": 20,
      "provider": "Microsoft-Windows-WindowsUpdateClient",
      "level": "Error",
      "time_created": "2026-04-15T10:23:45Z"
    }
  ],
  "status": "ok",
  "error_msg": null
}
```

---

### 5. Domain Status (`domain`)

**Fuente:** `Test-ComputerSecureChannel`

**Descripción:** Estado del canal seguro con el controlador de dominio.

**Campos:**
- `secure_channel` (bool): `true` si el canal está activo y válido
- `status` (str): `ok`, `error`, `not_in_domain`
- `error_msg` (str|null): Mensaje de error

**Estados:**
- `ok`: Equipo unido a dominio con canal seguro activo
- `not_in_domain`: Equipo no está unido a un dominio (workgroup)
- `error`: Error al verificar el canal (permisos, red, etc.)

**Ejemplo:**
```json
{
  "secure_channel": true,
  "status": "ok",
  "error_msg": null
}
```

---

### 6. Uptime (`uptime`)

**Fuente:** `Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime`

**Descripción:** Tiempo transcurrido desde el último arranque del sistema.

**Campos:**
- `last_boot` (str, ISO 8601 UTC): Timestamp del último arranque
- `days` (float): Días desde el arranque (con 1 decimal)
- `status` (str): `ok`, `warning`, `critical`, `error`
- `error_msg` (str|null): Mensaje de error

**Cálculo:**
```python
days = (datetime.utcnow() - last_boot).total_seconds() / 86400
```

**Thresholds por defecto:**
- `ok`: < 30 días
- `warning`: 30-60 días
- `critical`: > 60 días

**Ejemplo:**
```json
{
  "last_boot": "2026-04-02T08:15:30Z",
  "days": 13.2,
  "status": "ok",
  "error_msg": null
}
```

---

### 7. Boot Time (`boot_time`)

**Fuente:** Estrategia dual con fallback automático

**Fuente primaria:** Event Log (Event ID 100, Microsoft-Windows-Diagnostics-Performance)
```powershell
Get-WinEvent -FilterHashtable @{
    LogName='Microsoft-Windows-Diagnostics-Performance/Operational';
    ID=100
} -MaxEvents 1
```

**Fuente secundaria (fallback):** WMI (si no hay Event ID 100 disponible)
```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime
```

**Descripción:** Duración del proceso de arranque del sistema. El Event ID 100 solo se genera cuando hay degradación detectada, por lo que puede no estar presente en todos los arranques.

**Campos:**
- `last_boot_time` (str, ISO 8601 local): Timestamp del arranque
- `boot_duration_seconds` (int|null): Duración del boot en segundos (null si solo hay WMI)
- `source` (str): `event_log` o `wmi`
- `status` (str): `optimal`, `ok`, `degraded`, `critical`, `unknown`, `error`
- `error_msg` (str|null): Mensaje de error

**Estados (solo para source=event_log):**
- `optimal`: < 60 segundos
- `ok`: 60-119 segundos
- `degraded`: 120-179 segundos
- `critical`: ≥ 180 segundos
- `unknown`: Solo WMI disponible (sin duración)

**Ejemplo (Event Log):**
```json
{
  "last_boot_time": "2026-04-02T09:15:30",
  "boot_duration_seconds": 115,
  "source": "event_log",
  "status": "ok",
  "error_msg": null
}
```

**Ejemplo (WMI fallback):**
```json
{
  "last_boot_time": "2026-04-15T08:30:00",
  "boot_duration_seconds": null,
  "source": "wmi",
  "status": "unknown",
  "error_msg": null
}
```

**Nota importante:** Es normal que `uptime.last_boot` y `boot_time.last_boot_time` difieran. El Event ID 100 es un evento histórico del último boot con degradación, mientras que uptime siempre reporta el boot actual del sistema.

---

### 8. Services (`services`)

**Fuente:** `Get-Service` con filtrado por tiers configurables

**Descripción:** Estado de servicios críticos del sistema organizados en 3 niveles (tiers).

**Campos (por servicio):**
- `name` (str): Nombre interno del servicio
- `display_name` (str): Nombre visible del servicio
- `state` (str): `Running`, `Stopped`, `Paused`, etc.
- `startup_type` (str): `Automatic`, `Manual`, `Disabled`
- `tier` (int, 1-3): Nivel de criticidad del servicio
- `status` (str): `ok`, `warning`, `critical`, `not_available`, `error`

**Tiers por defecto:**

**Tier 1 (Crítico):**
- `SepMasterService` - Symantec Endpoint Protection
- `EventLog` - Event Log del sistema
- `RpcSs` - Remote Procedure Call
- `LanmanWorkstation` - Workstation (acceso a red)

**Tier 2 (Importante):**
- `WinDefend` - Windows Defender
- `wuauserv` - Windows Update
- `Spooler` - Print Spooler
- `Dhcp` - DHCP Client

**Tier 3 (Monitoreo):**
- `LanmanServer` - Server (compartición de archivos)
- `W32Time` - Windows Time
- `Dnscache` - DNS Client
- `Netlogon` - Netlogon (autenticación de dominio)

**Lógica de evaluación:**
- **Tier 1 Stopped:** `critical` (a menos que esté Disabled)
- **Tier 2 Stopped:** `warning` (a menos que esté Disabled)
- **Tier 3 Stopped:** `ok` (solo monitoreo)
- **Regla especial:** `Stopped + Disabled = ok` (configuración intencional)
- **Servicio no encontrado:** `not_available`

**Ejemplo:**
```json
[
  {
    "name": "EventLog",
    "display_name": "Windows Event Log",
    "state": "Running",
    "startup_type": "Automatic",
    "tier": 1,
    "status": "ok"
  },
  {
    "name": "WinDefend",
    "display_name": "Windows Defender Antivirus Service",
    "state": "Stopped",
    "startup_type": "Manual",
    "tier": 2,
    "status": "ok"
  }
]
```

---

## Configuración

### Ubicación

```
{BASE_DIR}/config/health_monitor_config.json
```

Donde `{BASE_DIR}` es el directorio raíz del agente.

### Creación Automática

Si el archivo no existe, se crea automáticamente con valores por defecto al ejecutar el plugin por primera vez.

### Estructura

```json
{
  "thresholds": {
    "disk": {
      "critical_percent": 10.0,
      "warning_percent": 20.0
    },
    "memory": {
      "critical_percent": 90.0,
      "warning_percent": 80.0
    },
    "cpu": {
      "critical_percent": 90.0,
      "warning_percent": 75.0
    },
    "uptime": {
      "warning_days": 30,
      "critical_days": 60
    },
    "events": {
      "warning_count": 5,
      "critical_count": 10
    },
    "boot_time": {
      "optimal_seconds": 60,
      "normal_seconds": 120,
      "degraded_seconds": 180
    }
  },
  "services": {
    "tier1": [
      "SepMasterService",
      "EventLog",
      "RpcSs",
      "LanmanWorkstation"
    ],
    "tier2": [
      "WinDefend",
      "wuauserv",
      "Spooler",
      "Dhcp"
    ],
    "tier3": [
      "LanmanServer",
      "W32Time",
      "Dnscache",
      "Netlogon"
    ]
  },
  "event_filters": {
    "providers": {
      "Microsoft-Windows-DistributedCOM": [10016],
      "Microsoft-Windows-DNS-Client": [1014]
    }
  }
}
```

### Parámetros Configurables

#### Thresholds

| Parámetro | Tipo | Por Defecto | Descripción |
|-----------|------|-------------|-------------|
| `disk.critical_percent` | float | 10.0 | % libre mínimo antes de critical |
| `disk.warning_percent` | float | 20.0 | % libre mínimo antes de warning |
| `memory.critical_percent` | float | 90.0 | % usado máximo antes de critical |
| `memory.warning_percent` | float | 80.0 | % usado máximo antes de warning |
| `cpu.critical_percent` | float | 90.0 | % carga máximo antes de critical |
| `cpu.warning_percent` | float | 75.0 | % carga máximo antes de warning |
| `uptime.warning_days` | int | 30 | Días antes de warning |
| `uptime.critical_days` | int | 60 | Días antes de critical |
| `events.warning_count` | int | 5 | Nº eventos antes de warning |
| `events.critical_count` | int | 10 | Nº eventos antes de critical |
| `boot_time.optimal_seconds` | int | 60 | Umbral para boot optimal |
| `boot_time.normal_seconds` | int | 120 | Umbral para boot ok |
| `boot_time.degraded_seconds` | int | 180 | Umbral para boot degraded |

#### Services

Cada tier es un array de nombres de servicio (nombre interno, no display name).

**Añadir un servicio:**
```json
{
  "services": {
    "tier1": [
      "SepMasterService",
      "NuevoServicioCritico"  // ← Añadir aquí
    ]
  }
}
```

**Importante:** Usar el nombre interno del servicio, no el display name. Para obtenerlo:
```powershell
Get-Service | Where-Object {$_.DisplayName -like "*nombre*"} | Select-Object Name, DisplayName
```

#### Event Filters

Filtra ruido conocido del Event Log.

**Estructura:**
```json
{
  "event_filters": {
    "providers": {
      "NombreProvider": [EventID1, EventID2, ...]
    }
  }
}
```

**Ejemplo - Filtrar DCOM 10016:**
```json
{
  "event_filters": {
    "providers": {
      "Microsoft-Windows-DistributedCOM": [10016]
    }
  }
}
```

---

## Estructura de Salida

### JSON Output

El plugin genera un bloque `health_monitor` dentro del payload de telemetría:

```json
{
  "device_id": "HOSTNAME",
  "timestamp": "2026-04-15T14:30:00Z",
  "agent_version": "1.0.0",
  "username": "user@domain",
  "metrics": {
    "health_monitor": {
      "plugin_version": "1.1.0",
      "host": "HOSTNAME",
      "domain": "DOMAIN",
      "timestamp": "2026-04-15T14:30:15Z",
      "execution": {
        "duration_ms": 2847,
        "metrics_attempted": 8,
        "metrics_successful": 8
      },
      "metrics": {
        "cpu": { ... },
        "memory": { ... },
        "disk": { ... },
        "events": { ... },
        "domain": { ... },
        "uptime": { ... },
        "boot_time": { ... },
        "services": [ ... ]
      }
    }
  }
}
```

### Metadata de Ejecución

El bloque `execution` proporciona información sobre la ejecución del plugin:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `duration_ms` | int | Duración total de ejecución en milisegundos |
| `metrics_attempted` | int | Número de métricas intentadas (siempre 8) |
| `metrics_successful` | int | Número de métricas que completaron sin error |

**Interpretación:**
- `metrics_successful == 8`: Ejecución perfecta
- `metrics_successful < 8`: Al menos una métrica falló (revisar `error_msg` de cada métrica)

---

## Criterios de Estado

### Estados Posibles

| Estado | Descripción | Acción Recomendada |
|--------|-------------|-------------------|
| `ok` | Métrica dentro de rangos normales | Ninguna |
| `warning` | Métrica se aproxima a umbral crítico | Monitorear |
| `critical` | Métrica fuera de rangos aceptables | Intervención requerida |
| `error` | Error al recopilar la métrica | Revisar logs/permisos |
| `not_in_domain` | (solo domain) Equipo no está en dominio | Informativo |
| `not_available` | (solo services) Servicio no encontrado | Verificar instalación |
| `optimal` | (solo boot_time) Boot excepcionalmente rápido | Informativo |
| `degraded` | (solo boot_time) Boot lento pero aceptable | Monitorear |
| `unknown` | (solo boot_time) Sin datos de duración (WMI) | Informativo |

### Scoring (Backend)

El backend calcula un score de salud (0-100) basado en penalizaciones:

| Condición | Penalización |
|-----------|--------------|
| Disco < 10% | -40 puntos |
| RAM > 90% | -20 puntos |
| Eventos > 10 | -30 puntos |
| Canal dominio KO | -10 puntos |
| CPU > 90% | -10 puntos |
| Boot degraded | -5 puntos |
| Boot critical | -10 puntos |

**Escala de scores:**
- **90-100:** Excelente
- **70-89:** Bueno
- **50-69:** Regular (requiere atención)
- **< 50:** Crítico (intervención urgente)

---

## Limitaciones Conocidas

### 1. Permisos

**Problema:** El plugin requiere permisos de usuario estándar (no admin) para la mayoría de métricas.

**Excepciones:**
- `Event Log`: Requiere acceso al log de System (normalmente disponible)
- `Services`: Requiere permisos para consultar servicios (Get-Service)

**Solución:** Si una métrica falla por permisos, devuelve `status: "error"` con `error_msg` descriptivo.

---

### 2. Event ID 100 (Boot Time)

**Problema:** El Event ID 100 de Diagnostics-Performance solo se genera cuando Windows detecta degradación en el boot. No está presente en todos los arranques.

**Consecuencias:**
- La métrica puede reportar un boot antiguo (último boot con degradación)
- `uptime.last_boot` y `boot_time.last_boot_time` pueden diferir

**Solución:** El plugin usa fallback automático a WMI cuando no hay Event ID 100. El estado se marca como `unknown` cuando solo hay WMI disponible.

---

### 3. Performance Counters

**Problema:** El plugin NO usa Performance Counters porque:
- Pueden estar deshabilitados en entornos corporativos
- Requieren permisos elevados en algunos casos
- No son confiables en VPN intermitente

**Solución:** Se usan alternativas CIM/WMI que son más robustas.

---

### 4. Disco Multi-Partición

**Problema:** El plugin solo monitorea el disco del sistema (`$env:SystemDrive`, típicamente C:).

**Razón:** Simplificación del plugin. Discos secundarios (D:, E:) son datos de usuario, no críticos para salud del sistema.

**Solución futura:** Si se requiere, se puede extender para monitorear múltiples discos.

---

### 5. Timezone en Boot Time

**Problema:** `boot_time.last_boot_time` se reporta en hora local (sin zona horaria).

**Razón:** El Event ID 100 provee timestamps locales, no UTC.

**Solución:** El backend parsea como local y convierte internamente según configuración del servidor.

---

## Troubleshooting

### Error: "Access Denied" en Event Log

**Síntoma:**
```json
{
  "events": {
    "status": "error",
    "error_msg": "Access to the path 'Microsoft-Windows-Diagnostics-Performance/Operational' is denied."
  }
}
```

**Causa:** El usuario no tiene permisos para leer el Event Log.

**Solución:**
1. Verificar que el usuario está en el grupo "Event Log Readers"
2. Alternativamente, ejecutar el agente con credenciales apropiadas
3. Si el Event Log no es crítico, ignorar (la métrica se marca como error pero el resto funciona)

---

### Error: "Service not found" para todos los servicios

**Síntoma:**
```json
{
  "services": [
    {
      "name": "EventLog",
      "status": "not_available",
      "state": null,
      ...
    }
  ]
}
```

**Causa:** `Get-Service` está fallando (permisos, PowerShell restringido).

**Solución:**
1. Verificar que PowerShell puede ejecutar `Get-Service` manualmente
2. Revisar las políticas de ejecución de PowerShell (`Get-ExecutionPolicy`)
3. Contactar con IT para validar permisos

---

### Boot Time siempre reporta "unknown"

**Síntoma:**
```json
{
  "boot_time": {
    "boot_duration_seconds": null,
    "source": "wmi",
    "status": "unknown"
  }
}
```

**Causa:** No hay Event ID 100 disponible. Esto es normal si el sistema no ha experimentado degradación en el boot.

**Solución:** Esto no es un error. El estado `unknown` es informativo. Si se requiere la duración del boot, se puede forzar un evento manualmente (no recomendado en producción).

---

### Memoria reporta valores negativos o incorrectos

**Síntoma:**
```json
{
  "memory": {
    "usage_pct": -10.5,
    "status": "error"
  }
}
```

**Causa:** Error en la lectura de WMI (valores corruptos, sistema en estado inconsistente).

**Solución:**
1. Reiniciar el servicio WMI (`Restart-Service Winmgmt`)
2. Verificar integridad del sistema (`sfc /scannow`)
3. Si persiste, contactar con IT

---

### Events reporta 0 eventos pero status es "critical"

**Síntoma:**
```json
{
  "events": {
    "error_count": 0,
    "critical_count": 0,
    "status": "critical"
  }
}
```

**Causa:** Esto no debería ocurrir con la lógica actual. Posible bug.

**Solución:**
1. Revisar la versión del plugin (`plugin_version` en el output)
2. Actualizar a la última versión
3. Reportar el bug con el JSON completo del payload

---

### Configuración no se aplica después de modificar el JSON

**Síntoma:** Los thresholds no cambian después de editar `health_monitor_config.json`.

**Causa:** El archivo de configuración se carga al inicio del plugin. Si el agente ya estaba en ejecución, no se relee.

**Solución:**
1. Reiniciar el agente de EHUkene
2. O esperar a la próxima ejecución programada (diaria)
3. Para testing inmediato: ejecutar el plugin manualmente

---

## Changelog

### v1.1.0 (2026-04-15)

**Añadido:**
- Nueva métrica: `boot_time` con estrategia dual (Event Log + WMI fallback)
- Estados adicionales para boot: `optimal`, `degraded`, `unknown`
- Thresholds configurables para boot time
- Campo `source` en boot_time para indicar origen de datos
- Metadata de ejecución (`execution` block) con duración y contadores de éxito

**Cambiado:**
- Event Log: reducción de ruido mediante triple filtrado (providers, combinaciones, mensajes vacíos)
- Services: añadida regla "Stopped + Disabled = ok"
- Configuración: migrado a JSON (anteriormente era hardcoded)
- Uptime: mejorado cálculo de días con 1 decimal de precisión

**Corregido:**
- Memory: uso de BigInteger en backend para valores >2GB
- Disk: validación de `free_gb` puede ser 0 (disco lleno)
- Events: parseo de timestamps UTC correctamente
- Services: manejo de servicios no disponibles sin crashear

**Documentación:**
- Especificación técnica completa
- Guía de configuración
- Troubleshooting extendido

---

### v1.0.0 (2026-04-01)

**Release inicial:**
- 7 métricas básicas: CPU, Memory, Disk, Events, Domain, Uptime, Services
- Thresholds hardcoded
- Configuración básica

---

## Integración con Backend

### Tablas de Base de Datos

El plugin persiste sus datos en **8 tablas** en PostgreSQL:

1. `health_cpu_metrics`
2. `health_memory_metrics`
3. `health_disk_metrics`
4. `health_event_metrics` (con campos JSONB)
5. `health_domain_metrics`
6. `health_uptime_metrics`
7. `health_boot_time_metrics`
8. `health_service_metrics`

Todas las tablas incluyen:
- `device_id`: UUID del dispositivo
- `recorded_at`: Timestamp del agente
- `received_at`: Timestamp del servidor
- `status`: Estado de la métrica
- `error_msg`: Mensaje de error (si aplica)

### Endpoints API

**Recepción de telemetría:**
```
POST /api/telemetry
```

El payload consolidado incluye `health_monitor` dentro del bloque `metrics`.

**Histórico por dispositivo:**
```
GET /api/devices/{device_id}/history?metric=health_cpu
GET /api/devices/{device_id}/history?metric=health_memory
GET /api/devices/{device_id}/history?metric=health_disk
GET /api/devices/{device_id}/history?metric=health_events
GET /api/devices/{device_id}/history?metric=health_domain
GET /api/devices/{device_id}/history?metric=health_uptime
GET /api/devices/{device_id}/history?metric=health_boot_time
GET /api/devices/{device_id}/history?metric=health_services
```

**Última métrica por dispositivo:**
```
GET /api/devices/{device_id}
```

Incluye `last_metrics.health_monitor` con las 8 métricas más recientes.

### Deduplicación

El backend deduplica usando `agent_timestamp` (timestamp del agente, no del servidor) con una ventana configurable (por defecto ±12h).

Esto garantiza:
- Latencia de red no afecta la deduplicación
- Ventana determinista independiente de cuándo llega el paquete
- Envíos múltiples del mismo día se rechazan (409 Conflict)

---

## Casos de Uso

### Dashboard de Salud Corporativa

**Objetivo:** Visualizar el estado general de la flota de equipos.

**Métricas clave:**
- `cpu.status`, `memory.status`, `disk.status` → Semáforo por equipo
- `events.critical_count`, `events.error_count` → Tendencias de errores
- `domain.secure_channel` → Validar conectividad AD
- `uptime.days` → Identificar equipos que nunca se apagan

---

### Alertas Proactivas

**Objetivo:** Notificar antes de que un problema se vuelva crítico.

**Ejemplos:**
- Disco < 20% → Alerta warning → "Limpiar disco"
- Memoria > 80% durante 3 días → Alerta → "Posible memory leak"
- Canal dominio KO → Alerta crítica → "Equipo desconectado de AD"
- Uptime > 60 días → Alerta → "Programar reinicio"

---

### Inventario de Servicios

**Objetivo:** Auditar qué servicios están corriendo en cada equipo.

**Consultas útiles:**
```sql
-- Equipos sin SEP
SELECT device_id FROM health_service_metrics
WHERE service_name = 'SepMasterService' AND state = 'Stopped';

-- Equipos con Windows Update deshabilitado
SELECT device_id FROM health_service_metrics
WHERE service_name = 'wuauserv' AND startup_type = 'Disabled';
```

---

### Análisis de Rendimiento de Boot

**Objetivo:** Identificar equipos con arranque lento.

**Métricas:**
- `boot_time.boot_duration_seconds` → Comparar entre equipos
- `boot_time.status` = `critical` → Equipos prioritarios para optimización

**Insights:**
- Boot > 180s → Revisar startup programs
- Boot > 300s → Posible problema de hardware (disco lento)

---

## Mejores Prácticas

### 1. Configuración Inicial

Al desplegar el plugin por primera vez:

1. **Ejecutar con defaults:** Dejar que el plugin cree `health_monitor_config.json` automáticamente
2. **Revisar primera ejecución:** Validar que las 8 métricas se recopilan correctamente
3. **Ajustar thresholds:** Modificar según estándares corporativos (ej: disco crítico en 5% en lugar de 10%)
4. **Añadir servicios custom:** Incluir servicios corporativos en tiers

---

### 2. Monitoreo Continuo

- **Revisar `metrics_successful`:** Si es < 8, investigar qué métricas están fallando
- **Trending de estados:** Un equipo que pasa de `ok` a `warning` consistentemente indica deterioro
- **Correlación con tickets:** Cruzar equipos con `status: critical` con tickets de soporte

---

### 3. Mantenimiento del Filtro de Eventos

El Event Log puede generar mucho ruido. Mantener `event_filters` actualizado:

1. **Revisar `top_sources`:** Identificar providers frecuentes
2. **Evaluar relevancia:** ¿El evento indica un problema real?
3. **Añadir a filtros:** Si es ruido conocido, añadirlo a `event_filters.providers`

**Ejemplo:**
```json
{
  "event_filters": {
    "providers": {
      "Microsoft-Windows-DistributedCOM": [10016],
      "Microsoft-Windows-DNS-Client": [1014],
      "Service Control Manager": [7036]  // ← Nuevo filtro
    }
  }
}
```

---

### 4. Interpretación de Boot Time

**Boot antiguo vs Boot actual:**
- `boot_time.last_boot_time` puede ser de hace semanas (último evento de degradación)
- `uptime.last_boot` siempre es el boot actual

**Cuándo preocuparse:**
- `boot_time.status = critical` → Investigar, aunque sea un evento antiguo
- `boot_time.source = wmi` y `uptime.days > 30` → Equipo estable pero sin datos de duración de boot

---

## Soporte

### Logs

El plugin registra errores en:
```
{BASE_DIR}/logs/health_monitor.log
```

**Niveles de log:**
- `INFO`: Ejecución normal, inicio/fin de métricas
- `WARNING`: Métrica falló pero el plugin continúa
- `ERROR`: Error crítico (configuración inválida, fallo total)

---

### Contacto

**Equipo de desarrollo:** EHUkene Development Team  
**Repositorio:** (interno)  
**Documentación adicional:** `docs/` en el repositorio del agente

---

## Licencia

Copyright © 2026 EHU/UPV - Universidad del País Vasco  
Uso interno exclusivo - Todos los derechos reservados

---

**Última revisión:** 2026-04-15  
**Próxima revisión:** 2026-07-15  
**Mantenedor:** EHUkene Development Team
