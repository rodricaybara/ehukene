# 🎯 Especificación Técnica Completa: Plugin de Monitorización de Salud de Equipos Windows

**Versión:** 1.1.0  
**Fecha:** 2026-04-14  
**Autor:** Equipo de Infraestructura  
**Destinatario:** Codex (Desarrollador)  
**Changelog:** Añadida métrica de tiempo de arranque (boot_time)

---

## 📋 Índice

1. [Contexto y Objetivo](#1-contexto-y-objetivo)
2. [Arquitectura General](#2-arquitectura-general)
3. [Estructura de Archivos](#3-estructura-de-archivos)
4. [Archivo de Configuración](#4-archivo-de-configuración)
5. [Métricas a Recoger](#5-métricas-a-recoger)
6. [Formato de Salida JSON](#6-formato-de-salida-json)
7. [Manejo de Errores](#7-manejo-de-errores)
8. [Requisitos de Implementación](#8-requisitos-de-implementación)
9. [Casos Edge y Validaciones](#9-casos-edge-y-validaciones)
10. [Ejemplos de Output](#10-ejemplos-de-output)

---

## 1. Contexto y Objetivo

### 1.1 Problema a Resolver

Crear un plugin de PowerShell que recopile métricas de salud del sistema Windows en entornos corporativos donde:
- Los Performance Counters pueden no estar disponibles
- Las políticas de grupo (GPO) limitan el acceso a ciertas APIs
- La conectividad de red (VPN/dominio) es intermitente

### 1.2 Objetivo del Plugin

**Recoger datos fiables** de salud del sistema que:
- Funcionen en el 100% de los equipos Windows corporativos
- No generen falsos positivos por ruido operativo
- Sean enviados al backend para cálculo de scoring
- Permitan análisis posterior con RAG

### 1.3 Principios de Diseño

✅ **Fiabilidad sobre precisión**: Mejor 5 métricas que siempre funcionan que 20 que fallan  
✅ **Resiliencia a fallos**: Si una métrica falla, las demás continúan  
✅ **Simplicidad**: Usar APIs básicas de Windows (CIM, WMI, EventLog)  
✅ **Stateless**: El plugin no mantiene estado entre ejecuciones  

---

## 2. Arquitectura General

### 2.1 Flujo de Ejecución

```
Inicio
  ↓
Cargar configuración (o crear por defecto)
  ↓
Recoger métricas (en paralelo, con try-catch individual)
  ├── CPU
  ├── Memoria
  ├── Disco
  ├── Eventos
  ├── Dominio
  ├── Uptime
  ├── Boot Time ⭐ NUEVA
  └── Servicios
  ↓
Construir JSON de salida
  ↓
Enviar al backend (HTTP POST)
  ↓
Fin
```

### 2.2 Frecuencia de Ejecución

- **1 vez al día**
- Programado mediante Windows Scheduled Task
- Hora de ejecución: Configurable por el administrador

### 2.3 Timeout

- Timeout total del plugin: **60 segundos**
- Timeout por métrica individual: **10 segundos**

---

## 3. Estructura de Archivos

### 3.1 Organización del Proyecto

```
health_monitor/
├── agent/
│   └── plugins/
│       └── health_monitor.ps1         # Script principal
├── config/
│   └── health_monitor_config.json     # Configuración
└── logs/                               # (Opcional, para debugging local)
    └── health_monitor.log
```

### 3.2 Detección de Rutas (PATH Resolution)

**Patrón a seguir** (basado en el plugin de software_usage):

```python
# Equivalente en PowerShell
if ($PSVersionTable.PSEdition -eq 'Desktop' -or $PSVersionTable.PSEdition -eq 'Core') {
    if ($MyInvocation.MyCommand.Path) {
        $BASE_DIR = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    } else {
        $BASE_DIR = $PSScriptRoot
    }
}
$CONFIG_PATH = Join-Path $BASE_DIR "config\health_monitor_config.json"
```

**Comportamiento esperado:**

| Contexto | BASE_DIR | CONFIG_PATH |
|----------|----------|-------------|
| **Desarrollo** (ejecutado directamente) | `health_monitor/agent/` | `health_monitor/config/health_monitor_config.json` |
| **Producción** (instalado en Program Files) | `C:\Program Files\EHUkene\` | `C:\Program Files\EHUkene\config\health_monitor_config.json` |

---

## 4. Archivo de Configuración

### 4.1 Ubicación

- **Ruta:** `{BASE_DIR}/config/health_monitor_config.json`
- **Formato:** JSON válido (UTF-8)
- **Permisos:** Lectura para SYSTEM y Administradores

### 4.2 Comportamiento si No Existe

**Opción seleccionada:** Crear automáticamente con valores por defecto

```powershell
if (-not (Test-Path $CONFIG_PATH)) {
    $defaultConfig = @{
        version = "1.0"
        thresholds = @{...}
        services = @{...}
        event_filters = @{...}
    }
    $defaultConfig | ConvertTo-Json -Depth 10 | Out-File $CONFIG_PATH -Encoding UTF8
}
```

### 4.3 Estructura del Archivo

```json
{
  "version": "1.1",
  "thresholds": {
    "disk": {
      "critical": 10,
      "warning": 20
    },
    "memory": {
      "critical": 90,
      "warning": 80
    },
    "cpu": {
      "critical": 90,
      "warning": 75
    },
    "events": {
      "critical_count_threshold": 10,
      "error_count_threshold": 50
    },
    "uptime": {
      "max_days_without_reboot": 90
    },
    "boot_time": {
      "optimal": 60,
      "normal": 120,
      "degraded": 180
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
      "BITS",
      "Dnscache",
      "W32Time",
      "WinRM"
    ],
    "tier3": [
      "Spooler"
    ]
  },
  "event_filters": {
    "ignored_providers": [
      "Microsoft-Windows-GroupPolicy",
      "NETLOGON",
      "Microsoft-Windows-Time-Service",
      "Microsoft-Windows-DistributedCOM",
      "Microsoft-Windows-Kernel-General",
      "USER32"
    ],
    "ignored_event_ids": [
      1014,
      10016,
      10010,
      1001,
      10154,
      15,
      1,
      37
    ],
    "ignored_combinations": [
      {
        "provider": "Microsoft-Windows-DNS-Client",
        "event_id": 1014
      },
      {
        "provider": "Microsoft-Windows-DistributedCOM",
        "event_id": 10016
      },
      {
        "provider": "Microsoft-Windows-DistributedCOM",
        "event_id": 10010
      }
    ]
  }
}
```

### 4.4 Validación del Archivo

**NO se requiere validación exhaustiva**. Si el archivo existe y es JSON válido, se usa. Si no se puede parsear, se usan valores hardcodeados por defecto.

---

## 5. Métricas a Recoger

### 5.1 CPU

#### Comando
```powershell
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$cpuLoad = $cpu.LoadPercentage
```

#### Datos a recoger
- `load_percentage`: Porcentaje de uso actual (0-100)

#### Determinación de status
```powershell
if ($cpuLoad -ge $config.thresholds.cpu.critical) {
    $status = "critical"
} elseif ($cpuLoad -ge $config.thresholds.cpu.warning) {
    $status = "warning"
} else {
    $status = "ok"
}
```

#### Manejo de errores
```powershell
try {
    # código de obtención
} catch {
    $cpuData = @{
        value = $null
        status = "error"
        error_msg = $_.Exception.Message
    }
}
```

---

### 5.2 Memoria RAM

#### Comando
```powershell
$os = Get-CimInstance Win32_OperatingSystem
$totalKB = $os.TotalVisibleMemorySize
$freeKB = $os.FreePhysicalMemory
$usedKB = $totalKB - $freeKB
$usagePct = [Math]::Round(($usedKB / $totalKB) * 100, 2)
```

#### Datos a recoger
- `total_kb`: Memoria total en KB
- `free_kb`: Memoria libre en KB
- `usage_pct`: Porcentaje de uso (0-100, 2 decimales)

#### Determinación de status
```powershell
if ($usagePct -ge $config.thresholds.memory.critical) {
    $status = "critical"
} elseif ($usagePct -ge $config.thresholds.memory.warning) {
    $status = "warning"
} else {
    $status = "ok"
}
```

#### Notas importantes
⚠️ **Trabajar siempre en KB** para evitar errores de conversión  
⚠️ No redondear hasta el cálculo final del porcentaje

---

### 5.3 Disco del Sistema

#### Comando
```powershell
# Intentar primero C:
$systemDrive = "C:"
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$systemDrive' AND DriveType=3"

# Si C: no existe, usar variable de entorno
if (-not $disk) {
    $systemDrive = $env:SystemDrive
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$systemDrive' AND DriveType=3"
}
```

#### Datos a recoger
- `drive`: Letra del disco (ej: "C:")
- `total_gb`: Tamaño total en GB (redondeado a 2 decimales)
- `free_gb`: Espacio libre en GB (redondeado a 2 decimales)
- `free_pct`: Porcentaje libre (0-100, 2 decimales)

#### Cálculo
```powershell
$totalGB = [Math]::Round($disk.Size / 1GB, 2)
$freeGB = [Math]::Round($disk.FreeSpace / 1GB, 2)
$freePct = [Math]::Round(($disk.FreeSpace / $disk.Size) * 100, 2)
```

#### Determinación de status
```powershell
if ($freePct -le $config.thresholds.disk.critical) {
    $status = "critical"
} elseif ($freePct -le $config.thresholds.disk.warning) {
    $status = "warning"
} else {
    $status = "ok"
}
```

#### Caso especial
Si no se encuentra ningún disco del sistema:
```json
{
  "disk": {
    "value": null,
    "status": "error",
    "error_msg": "System drive not found or not accessible"
  }
}
```

---

### 5.4 Eventos del Sistema

#### Comando base
```powershell
$events = Get-WinEvent -FilterHashtable @{
    LogName = 'System'
    Level = 1,2  # 1=Critical, 2=Error
    StartTime = (Get-Date).AddDays(-1)
} -ErrorAction SilentlyContinue
```

#### Filtrado de eventos

**Paso 1: Filtrar por Provider**
```powershell
$filteredEvents = $events | Where-Object {
    $_.ProviderName -notin $config.event_filters.ignored_providers
}
```

**Paso 2: Filtrar por EventID**
```powershell
$filteredEvents = $filteredEvents | Where-Object {
    $_.Id -notin $config.event_filters.ignored_event_ids
}
```

**Paso 3: Filtrar por combinaciones Provider+EventID**
```powershell
$filteredEvents = $filteredEvents | Where-Object {
    $event = $_
    $isIgnored = $false
    foreach ($combo in $config.event_filters.ignored_combinations) {
        if ($event.ProviderName -eq $combo.provider -and $event.Id -eq $combo.event_id) {
            $isIgnored = $true
            break
        }
    }
    -not $isIgnored
}
```

#### Datos a recoger

**Contadores:**
- `critical_count`: Eventos de nivel Critical (Level=1)
- `error_count`: Eventos de nivel Error (Level=2)
- `filtered_count`: Eventos descartados por filtros

**Top sources:**
```powershell
$topSources = $filteredEvents | 
    Group-Object ProviderName | 
    Sort-Object Count -Descending | 
    Select-Object -First 5 | 
    ForEach-Object {
        @{
            provider = $_.Name
            count = $_.Count
        }
    }
```

**Sample events (Top 5 por severidad):**
```powershell
$sampleEvents = $filteredEvents | 
    Sort-Object Level, TimeCreated -Descending |
    Select-Object -First 5 |
    ForEach-Object {
        @{
            event_id = $_.Id
            provider = $_.ProviderName
            level = switch($_.Level) {
                1 { "Critical" }
                2 { "Error" }
                default { "Unknown" }
            }
            time_created = $_.TimeCreated.ToString("yyyy-MM-ddTHH:mm:ssZ")
        }
    }
```

#### Determinación de status
```powershell
if ($criticalCount -ge $config.thresholds.events.critical_count_threshold) {
    $status = "critical"
} elseif ($errorCount -ge $config.thresholds.events.error_count_threshold) {
    $status = "warning"
} else {
    $status = "ok"
}
```

#### Notas importantes
⚠️ **NO incluir el mensaje de error** (introduce ruido)  
⚠️ Limitar a **Top 5** eventos para evitar JSONs enormes  
⚠️ Usar `-ErrorAction SilentlyContinue` para evitar fallos si el log no es accesible

---

### 5.5 Estado de Dominio

#### Comando
```powershell
$secureChannel = Test-ComputerSecureChannel
```

#### Datos a recoger
- `secure_channel`: Boolean (true/false)

#### Determinación de status
```powershell
if (-not $secureChannel) {
    $status = "error"
} else {
    $status = "ok"
}
```

#### Manejo de errores
Si el equipo no está en dominio, el comando puede fallar:
```powershell
try {
    $secureChannel = Test-ComputerSecureChannel
    $status = if ($secureChannel) { "ok" } else { "error" }
} catch {
    # Equipo no está en dominio o no se puede verificar
    $secureChannel = $false
    $status = "not_in_domain"
}
```

---

### 5.6 Uptime

#### Comando
```powershell
$os = Get-CimInstance Win32_OperatingSystem
$lastBoot = $os.LastBootUpTime
$uptime = (Get-Date) - $lastBoot
$uptimeDays = [Math]::Round($uptime.TotalDays, 1)
```

#### Datos a recoger
- `last_boot`: Fecha/hora del último arranque (ISO 8601 UTC)
- `days`: Días desde el último arranque (1 decimal)

#### Determinación de status
```powershell
if ($uptimeDays -ge $config.thresholds.uptime.max_days_without_reboot) {
    $status = "warning"
} else {
    $status = "ok"
}
```

#### Formato de fecha
```powershell
$lastBootISO = $lastBoot.ToString("yyyy-MM-ddTHH:mm:ssZ")
```

---

### 5.7 ⭐ Boot Time (Tiempo de Arranque) - NUEVA MÉTRICA

#### Descripción

Esta métrica mide la duración del último arranque del sistema en segundos. Se utiliza una estrategia de doble fuente para máxima fiabilidad:

1. **Fuente primaria:** Event ID 100 del canal `Microsoft-Windows-Diagnostics-Performance/Operational`
2. **Fuente fallback:** Win32_OperatingSystem vía WMI (solo proporciona timestamp, no duración)

#### Estrategia de Implementación

```
┌─────────────────────────────────┐
│ Intentar Event ID 100           │
│ (Diagnostics-Performance)       │
└────────────┬────────────────────┘
             │
             ├─ ✅ Éxito → Tenemos boot_duration_seconds + last_boot_time
             │
             └─ ❌ Fallo → Fallback a WMI
                          │
                          └─ ✅ Éxito → Solo last_boot_time (boot_duration = null)
                          │
                          └─ ❌ Fallo → Métrica completa en error
```

---

#### 5.7.1 Fuente Primaria: Event ID 100 (Diagnostics-Performance)

**Canal:** `Microsoft-Windows-Diagnostics-Performance/Operational`  
**Event ID:** 100  
**Datos disponibles:**
- `BootStartTime`: Timestamp UTC del inicio del arranque (formato ISO 8601)
- `BootTime`: Duración total del arranque en milisegundos

**Script PowerShell:**

```powershell
$ErrorActionPreference = 'SilentlyContinue'

try {
    $event = Get-WinEvent -LogName 'Microsoft-Windows-Diagnostics-Performance/Operational' `
                          -MaxEvents 50 -ErrorAction Stop |
             Where-Object { $_.Id -eq 100 } |
             Select-Object -First 1

    if (-not $event) {
        # No hay eventos ID 100
        return $null
    }

    # Parsear XML del evento
    $xml = [xml]$event.ToXml()
    $data = @{}
    foreach ($node in $xml.Event.EventData.Data) {
        $data[$node.Name] = $node.'#text'
    }

    $bootStartTime = $data['BootStartTime']
    $bootTimeMs = $data['BootTime']

    if (-not $bootStartTime -or -not $bootTimeMs) {
        # Campos ausentes en el XML
        return $null
    }

    # Convertir BootStartTime UTC → hora local
    # Formato: "2026-03-28T07:11:38.588792900Z"
    $bootStartNormalized = $bootStartTime.TrimEnd('Z').Split('.')[0]  # "2026-03-28T07:11:38"
    $bootDtUtc = [datetime]::ParseExact($bootStartNormalized, "yyyy-MM-ddTHH:mm:ss", $null)
    $bootDtUtc = [datetime]::SpecifyKind($bootDtUtc, [DateTimeKind]::Utc)
    $bootDtLocal = $bootDtUtc.ToLocalTime()
    $lastBootTime = $bootDtLocal.ToString("yyyy-MM-ddTHH:mm:ss")

    # Convertir BootTime ms → segundos enteros
    $bootTimeMsInt = [int]$bootTimeMs
    if ($bootTimeMsInt -le 0) {
        return $null
    }
    
    # Garantizar mínimo 1 segundo
    $bootDurationSeconds = [Math]::Max(1, [int]($bootTimeMsInt / 1000))

    return @{
        last_boot_time = $lastBootTime
        boot_duration_seconds = $bootDurationSeconds
        source = "event_log"
    }

} catch {
    # Error al consultar Event Log
    return $null
}
```

---

#### 5.7.2 Fuente Fallback: WMI (Win32_OperatingSystem)

**Clase WMI:** `Win32_OperatingSystem`  
**Propiedad:** `LastBootUpTime`  
**Datos disponibles:**
- Solo timestamp de arranque (NO duración)

**Script PowerShell:**

```powershell
$ErrorActionPreference = 'SilentlyContinue'

try {
    $os = Get-WmiObject -Class Win32_OperatingSystem -Namespace root\cimv2 -ErrorAction Stop |
          Select-Object -First 1

    if (-not $os) {
        return $null
    }

    $lastBootRaw = $os.LastBootUpTime
    if (-not $lastBootRaw) {
        return $null
    }

    # Formato WMI: "20260328071138.000000+060"
    # Los primeros 14 caracteres son la parte datetime: "YYYYMMDDHHMMSS"
    $bootDt = [datetime]::ParseExact($lastBootRaw.Substring(0, 14), "yyyyMMddHHmmss", $null)
    $lastBootTime = $bootDt.ToString("yyyy-MM-ddTHH:mm:ss")

    return @{
        last_boot_time = $lastBootTime
        boot_duration_seconds = $null  # No disponible vía WMI
        source = "wmi"
    }

} catch {
    return $null
}
```

---

#### 5.7.3 Lógica de Obtención Completa

```powershell
function Get-BootTimeMetric {
    # Intentar fuente primaria (Event ID 100)
    $bootData = Get-BootTimeFromEventLog
    
    if ($bootData) {
        # Éxito con Event Log
        return $bootData
    }
    
    # Fallback a WMI
    $bootData = Get-BootTimeFromWMI
    
    if ($bootData) {
        # Éxito con WMI (sin duración)
        return $bootData
    }
    
    # Ambas fuentes fallaron
    return @{
        last_boot_time = $null
        boot_duration_seconds = $null
        status = "error"
        error_msg = "Could not retrieve boot time from Event Log or WMI"
    }
}
```

---

#### 5.7.4 Datos a Recoger

| Campo | Tipo | Descripción | Fuente |
|-------|------|-------------|--------|
| `last_boot_time` | String | Timestamp del último arranque (ISO 8601 local) | Event Log o WMI |
| `boot_duration_seconds` | Integer o null | Duración del arranque en segundos | Solo Event Log |
| `source` | String | Fuente de datos ("event_log" o "wmi") | Ambas |
| `status` | String | Estado de la métrica | Calculado |

---

#### 5.7.5 Determinación de Status

**Basado en `boot_duration_seconds`** (si está disponible):

```powershell
if ($bootDurationSeconds -eq $null) {
    # WMI fallback: no tenemos duración
    $status = "unknown"
} elseif ($bootDurationSeconds -lt $config.thresholds.boot_time.optimal) {
    # < 60 segundos
    $status = "optimal"
} elseif ($bootDurationSeconds -lt $config.thresholds.boot_time.normal) {
    # 60-119 segundos
    $status = "ok"
} elseif ($bootDurationSeconds -lt $config.thresholds.boot_time.degraded) {
    # 120-179 segundos
    $status = "degraded"
} else {
    # >= 180 segundos
    $status = "critical"
}
```

---

#### 5.7.6 Scoring (Backend)

El backend aplicará las siguientes penalizaciones basadas en el status:

| Status | Rango (segundos) | Penalización | Descripción |
|--------|------------------|--------------|-------------|
| `optimal` | < 60 | 0 | Arranque muy rápido |
| `ok` | 60-119 | 0 | Arranque normal |
| `degraded` | 120-179 | -5 | Arranque lento |
| `critical` | >= 180 | -10 | Arranque muy lento |
| `unknown` | N/A | 0 | Sin datos (WMI fallback) |
| `error` | N/A | -5 | Error al obtener métrica |

---

#### 5.7.7 Casos Especiales

**Caso 1: Event Log disponible (ideal)**
```json
{
  "boot_time": {
    "last_boot_time": "2026-04-14T08:15:32",
    "boot_duration_seconds": 45,
    "source": "event_log",
    "status": "optimal"
  }
}
```

**Caso 2: Solo WMI disponible (sin duración)**
```json
{
  "boot_time": {
    "last_boot_time": "2026-04-14T08:15:32",
    "boot_duration_seconds": null,
    "source": "wmi",
    "status": "unknown"
  }
}
```

**Caso 3: Ambas fuentes fallaron**
```json
{
  "boot_time": {
    "last_boot_time": null,
    "boot_duration_seconds": null,
    "status": "error",
    "error_msg": "Could not retrieve boot time from Event Log or WMI"
  }
}
```

**Caso 4: Arranque crítico (>180s)**
```json
{
  "boot_time": {
    "last_boot_time": "2026-04-14T08:15:32",
    "boot_duration_seconds": 245,
    "source": "event_log",
    "status": "critical"
  }
}
```

---

#### 5.7.8 Notas Importantes

⚠️ **Prioridad de fuentes:** Siempre intentar Event Log primero (tiene duración)  
⚠️ **Timestamp local:** Convertir UTC a hora local del sistema  
⚠️ **Mínimo 1 segundo:** Si `boot_time_ms < 1000`, garantizar `boot_duration_seconds = 1`  
⚠️ **Manejo de errores:** No fallar si Event Log no está disponible, usar WMI como fallback  
⚠️ **Normalización de timestamp:** El Event ID 100 incluye nanosegundos, eliminarlos antes de parsear  

---

### 5.8 Servicios Críticos

#### Comando
```powershell
# Obtener todos los servicios críticos de los 3 tiers
$allCriticalServices = $config.services.tier1 + $config.services.tier2 + $config.services.tier3

$services = Get-Service -Name $allCriticalServices -ErrorAction SilentlyContinue
```

#### Datos a recoger por servicio
```powershell
@{
    name = $service.Name
    display_name = $service.DisplayName
    state = $service.Status.ToString()  # Running, Stopped, etc.
    startup_type = (Get-Service -Name $service.Name).StartType.ToString()  # Automatic, Manual, Disabled
    tier = # Determinar tier (1, 2 o 3)
    status = # ok, warning o critical
}
```

#### Determinación de status por servicio

**Regla de oro:** `Stopped + Disabled = no penaliza`

```powershell
function Get-ServiceStatus {
    param($service, $tier)
    
    # Si está Running, siempre OK
    if ($service.Status -eq 'Running') {
        return "ok"
    }
    
    # Si está Stopped
    if ($service.Status -eq 'Stopped') {
        $startType = (Get-Service -Name $service.Name).StartType
        
        # Disabled intencionalmente = OK
        if ($startType -eq 'Disabled') {
            return "ok"
        }
        
        # Stopped + Automatic = problema según tier
        if ($startType -eq 'Automatic') {
            switch ($tier) {
                1 { return "critical" }
                2 { return "warning" }
                3 { return "warning" }
            }
        }
        
        # Stopped + Manual = warning solo en tier1
        if ($startType -eq 'Manual') {
            if ($tier -eq 1) {
                return "warning"
            } else {
                return "ok"
            }
        }
    }
    
    return "ok"
}
```

#### Determinación de tier
```powershell
function Get-ServiceTier {
    param($serviceName, $config)
    
    if ($serviceName -in $config.services.tier1) { return 1 }
    if ($serviceName -in $config.services.tier2) { return 2 }
    if ($serviceName -in $config.services.tier3) { return 3 }
    return 0
}
```

#### Manejo de servicios no encontrados
Si un servicio de la lista no existe en el sistema:
```json
{
  "name": "SepMasterService",
  "display_name": null,
  "state": "NotFound",
  "startup_type": null,
  "tier": 1,
  "status": "not_available"
}
```

---

## 6. Formato de Salida JSON

### 6.1 Estructura Completa

```json
{
  "plugin_version": "1.1.0",
  "host": "U110370",
  "domain": "CORP.LOCAL",
  "timestamp": "2026-04-14T08:15:32Z",
  "execution": {
    "duration_ms": 1847,
    "metrics_attempted": 8,
    "metrics_successful": 8
  },
  "metrics": {
    "cpu": {
      "load_percentage": 23,
      "status": "ok"
    },
    "memory": {
      "total_kb": 16777216,
      "free_kb": 4718592,
      "usage_pct": 71.87,
      "status": "ok"
    },
    "disk": {
      "drive": "C:",
      "total_gb": 237.45,
      "free_gb": 16.23,
      "free_pct": 6.84,
      "status": "critical"
    },
    "events": {
      "critical_count": 3,
      "error_count": 12,
      "filtered_count": 47,
      "top_sources": [
        {
          "provider": "Disk",
          "count": 3
        },
        {
          "provider": "Service Control Manager",
          "count": 2
        }
      ],
      "sample_events": [
        {
          "event_id": 7001,
          "provider": "Service Control Manager",
          "level": "Error",
          "time_created": "2026-04-14T06:23:15Z"
        },
        {
          "event_id": 41,
          "provider": "Kernel-Power",
          "level": "Critical",
          "time_created": "2026-04-13T18:45:02Z"
        }
      ],
      "status": "ok"
    },
    "domain": {
      "secure_channel": false,
      "status": "error"
    },
    "uptime": {
      "last_boot": "2026-04-01T09:30:00Z",
      "days": 12.9,
      "status": "ok"
    },
    "boot_time": {
      "last_boot_time": "2026-04-01T09:30:15",
      "boot_duration_seconds": 45,
      "source": "event_log",
      "status": "optimal"
    },
    "services": [
      {
        "name": "SepMasterService",
        "display_name": "Symantec Endpoint Protection",
        "state": "Running",
        "startup_type": "Automatic",
        "tier": 1,
        "status": "ok"
      },
      {
        "name": "Spooler",
        "display_name": "Print Spooler",
        "state": "Stopped",
        "startup_type": "Disabled",
        "tier": 3,
        "status": "ok"
      },
      {
        "name": "wuauserv",
        "display_name": "Windows Update",
        "state": "Stopped",
        "startup_type": "Automatic",
        "tier": 2,
        "status": "warning"
      }
    ]
  }
}
```

### 6.2 Campos Obligatorios Nivel Superior

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `plugin_version` | String | Versión del plugin (semver: "1.1.0") |
| `host` | String | Nombre del equipo (NETBIOS name) |
| `domain` | String | Dominio al que pertenece (o "WORKGROUP") |
| `timestamp` | String | Timestamp de ejecución (ISO 8601 UTC) |
| `execution` | Object | Metadata de la ejecución |
| `metrics` | Object | Todas las métricas recopiladas |

### 6.3 Objeto `execution`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `duration_ms` | Integer | Duración total de la ejecución en milisegundos |
| `metrics_attempted` | Integer | Número de métricas que se intentaron recoger (ahora 8) |
| `metrics_successful` | Integer | Número de métricas recopiladas exitosamente |

### 6.4 Estados Posibles (`status`)

- `"ok"`: Métrica dentro de umbrales normales
- `"optimal"`: (Solo boot_time) Métrica excepcionalmente buena
- `"warning"`: Métrica en rango de advertencia
- `"degraded"`: (Solo boot_time) Métrica degradada pero no crítica
- `"critical"`: Métrica en rango crítico
- `"error"`: Error al obtener la métrica
- `"not_available"`: Métrica no disponible en este sistema
- `"not_in_domain"`: (Solo para `domain`) Equipo no está en dominio
- `"unknown"`: (Solo boot_time) Duración no disponible (fallback WMI)

---

## 7. Manejo de Errores

### 7.1 Patrón Obligatorio

**Cada métrica** debe estar envuelta en su propio try-catch:

```powershell
try {
    # Código de obtención de métrica
    $value = Get-Something
    $status = "ok"
} catch {
    $value = $null
    $status = "error"
    $errorMsg = $_.Exception.Message
}
```

### 7.2 Resiliencia

**Principio:** Si una métrica falla, las demás continúan ejecutándose.

```powershell
# MAL: Un fallo detiene todo
$cpu = Get-CPU
$memory = Get-Memory
$disk = Get-Disk

# BIEN: Cada métrica es independiente
$cpuData = Get-CPUMetric
$memoryData = Get-MemoryMetric
$diskData = Get-DiskMetric
```

### 7.3 Logging de Errores

Los errores **NO deben detener la ejecución**, pero pueden loguearse para debugging:

```powershell
if ($status -eq "error") {
    Write-Host "[ERROR] Failed to get CPU: $errorMsg" -ForegroundColor Red
    # Opcional: escribir a log file
}
```

### 7.4 Timeout por Métrica

Cada métrica tiene un timeout individual de **10 segundos**:

```powershell
$job = Start-Job -ScriptBlock { Get-SomeMetric }
$result = Wait-Job $job -Timeout 10

if ($result) {
    $value = Receive-Job $job
} else {
    Stop-Job $job
    $status = "error"
    $errorMsg = "Timeout after 10 seconds"
}
```

---

## 8. Requisitos de Implementación

### 8.1 Lenguaje y Versión

- **PowerShell 5.1** (Windows PowerShell) o superior
- Compatible con **PowerShell Core 7.x** (opcional)
- No usar características exclusivas de PS 7.x

### 8.2 Módulos Necesarios

**Ningún módulo externo requerido**. Solo usar cmdlets nativos:
- `Get-CimInstance`
- `Get-WinEvent`
- `Get-Service`
- `Test-ComputerSecureChannel`
- `Get-WmiObject` (solo para boot_time fallback)

### 8.3 Permisos Necesarios

El script debe ejecutarse con:
- **SYSTEM** (recomendado para Scheduled Task)
- O **Administrator** (para testing manual)

### 8.4 Compatibilidad

- Windows 10 / 11
- Windows Server 2016 / 2019 / 2022
- Entornos de dominio (Active Directory)
- Entornos workgroup (sin dominio)

### 8.5 Salida del Script

El script debe:
1. **Imprimir el JSON a STDOUT** (para testing manual)
2. **Enviar el JSON al backend** vía HTTP POST
3. **Devolver exit code 0** si todo va bien
4. **Devolver exit code 1** si hay errores críticos

### 8.6 Envío al Backend

```powershell
$backendURL = "https://backend.example.com/api/health"
$headers = @{
    "Content-Type" = "application/json"
    "Authorization" = "Bearer $TOKEN"  # Token desde variable de entorno o config
}

try {
    $response = Invoke-RestMethod -Uri $backendURL -Method Post -Body $jsonOutput -Headers $headers
    Write-Host "Data sent successfully"
} catch {
    Write-Host "Failed to send data to backend: $($_.Exception.Message)"
    # No fallar, solo loguear
}
```

**Nota:** La URL del backend y el token deben ser configurables (variable de entorno o archivo de config).

---

## 9. Casos Edge y Validaciones

### 9.1 Equipo sin Conexión a Dominio

```json
{
  "domain": {
    "secure_channel": false,
    "status": "not_in_domain"
  }
}
```

### 9.2 Disco del Sistema no es C:

```powershell
# Intentar C: primero
$systemDrive = "C:"
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$systemDrive' AND DriveType=3"

if (-not $disk) {
    $systemDrive = $env:SystemDrive
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$systemDrive' AND DriveType=3"
}
```

### 9.3 EventLog Inaccesible

```powershell
try {
    $events = Get-WinEvent -FilterHashtable @{...} -ErrorAction Stop
} catch {
    $eventsData = @{
        critical_count = 0
        error_count = 0
        filtered_count = 0
        top_sources = @()
        sample_events = @()
        status = "error"
        error_msg = "Event log not accessible"
    }
}
```

### 9.4 Servicio Crítico No Existe

Si `SepMasterService` no está instalado:
```json
{
  "name": "SepMasterService",
  "display_name": null,
  "state": "NotFound",
  "startup_type": null,
  "tier": 1,
  "status": "not_available"
}
```

### 9.5 Boot Time - Event Log No Disponible

Si el canal de Diagnostics-Performance no existe o no tiene eventos:
```json
{
  "boot_time": {
    "last_boot_time": "2026-04-14T08:15:32",
    "boot_duration_seconds": null,
    "source": "wmi",
    "status": "unknown"
  }
}
```

### 9.6 Valores Numéricos

**Redondeo:**
- Porcentajes: 2 decimales (ej: 71.87)
- GB: 2 decimales (ej: 237.45)
- Días de uptime: 1 decimal (ej: 12.9)
- Boot duration: entero (ej: 45)

**Tipo de datos:**
- Usar `[Math]::Round()` para redondear
- No usar `ToString("F2")` para cálculos, solo para display

### 9.7 Fechas y Timestamps

**Formato obligatorio:** ISO 8601 en UTC (para timestamp global) y local (para boot_time)

```powershell
# Timestamp global (UTC)
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

# Boot time (local)
$bootTimeLocal = $bootDt.ToString("yyyy-MM-ddTHH:mm:ss")
```

**Ejemplos:**
- UTC: `"2026-04-14T08:15:32Z"`
- Local: `"2026-04-14T10:15:32"` (sin Z al final)

---

## 10. Ejemplos de Output

### 10.1 Ejecución Exitosa (Todo OK)

```json
{
  "plugin_version": "1.1.0",
  "host": "WKS-FINANCE-01",
  "domain": "CORP.LOCAL",
  "timestamp": "2026-04-14T08:00:00Z",
  "execution": {
    "duration_ms": 1234,
    "metrics_attempted": 8,
    "metrics_successful": 8
  },
  "metrics": {
    "cpu": {
      "load_percentage": 15,
      "status": "ok"
    },
    "memory": {
      "total_kb": 16777216,
      "free_kb": 8388608,
      "usage_pct": 50.00,
      "status": "ok"
    },
    "disk": {
      "drive": "C:",
      "total_gb": 500.00,
      "free_gb": 250.00,
      "free_pct": 50.00,
      "status": "ok"
    },
    "events": {
      "critical_count": 0,
      "error_count": 2,
      "filtered_count": 15,
      "top_sources": [],
      "sample_events": [],
      "status": "ok"
    },
    "domain": {
      "secure_channel": true,
      "status": "ok"
    },
    "uptime": {
      "last_boot": "2026-04-13T08:00:00Z",
      "days": 1.0,
      "status": "ok"
    },
    "boot_time": {
      "last_boot_time": "2026-04-13T10:00:15",
      "boot_duration_seconds": 42,
      "source": "event_log",
      "status": "optimal"
    },
    "services": [
      {
        "name": "SepMasterService",
        "display_name": "Symantec Endpoint Protection",
        "state": "Running",
        "startup_type": "Automatic",
        "tier": 1,
        "status": "ok"
      }
    ]
  }
}
```

### 10.2 Equipo Degradado (Múltiples Problemas)

```json
{
  "plugin_version": "1.1.0",
  "host": "WKS-IT-05",
  "domain": "CORP.LOCAL",
  "timestamp": "2026-04-14T08:00:00Z",
  "execution": {
    "duration_ms": 2156,
    "metrics_attempted": 8,
    "metrics_successful": 7
  },
  "metrics": {
    "cpu": {
      "load_percentage": 95,
      "status": "critical"
    },
    "memory": {
      "total_kb": 8388608,
      "free_kb": 419430,
      "usage_pct": 95.00,
      "status": "critical"
    },
    "disk": {
      "drive": "C:",
      "total_gb": 237.00,
      "free_gb": 5.20,
      "free_pct": 2.19,
      "status": "critical"
    },
    "events": {
      "critical_count": 15,
      "error_count": 45,
      "filtered_count": 120,
      "top_sources": [
        {"provider": "Disk", "count": 10},
        {"provider": "Service Control Manager", "count": 5}
      ],
      "sample_events": [
        {
          "event_id": 7001,
          "provider": "Service Control Manager",
          "level": "Error",
          "time_created": "2026-04-14T07:23:15Z"
        }
      ],
      "status": "critical"
    },
    "domain": {
      "secure_channel": false,
      "status": "error"
    },
    "uptime": {
      "last_boot": "2025-12-01T09:00:00Z",
      "days": 134.5,
      "status": "warning"
    },
    "boot_time": {
      "last_boot_time": "2025-12-01T11:00:45",
      "boot_duration_seconds": 215,
      "source": "event_log",
      "status": "critical"
    },
    "services": [
      {
        "name": "wuauserv",
        "display_name": "Windows Update",
        "state": "Stopped",
        "startup_type": "Automatic",
        "tier": 2,
        "status": "warning"
      },
      {
        "name": "SepMasterService",
        "display_name": null,
        "state": "NotFound",
        "startup_type": null,
        "tier": 1,
        "status": "not_available"
      }
    ]
  }
}
```

### 10.3 Boot Time - Solo WMI Disponible

```json
{
  "plugin_version": "1.1.0",
  "host": "SRV-APP-03",
  "domain": "CORP.LOCAL",
  "timestamp": "2026-04-14T08:00:00Z",
  "execution": {
    "duration_ms": 1890,
    "metrics_attempted": 8,
    "metrics_successful": 8
  },
  "metrics": {
    "cpu": {
      "load_percentage": 25,
      "status": "ok"
    },
    "memory": {
      "total_kb": 33554432,
      "free_kb": 16777216,
      "usage_pct": 50.00,
      "status": "ok"
    },
    "disk": {
      "drive": "C:",
      "total_gb": 100.00,
      "free_gb": 30.00,
      "free_pct": 30.00,
      "status": "ok"
    },
    "events": {
      "critical_count": 0,
      "error_count": 3,
      "filtered_count": 12,
      "top_sources": [],
      "sample_events": [],
      "status": "ok"
    },
    "domain": {
      "secure_channel": true,
      "status": "ok"
    },
    "uptime": {
      "last_boot": "2026-04-10T08:00:00Z",
      "days": 4.0,
      "status": "ok"
    },
    "boot_time": {
      "last_boot_time": "2026-04-10T10:00:00",
      "boot_duration_seconds": null,
      "source": "wmi",
      "status": "unknown"
    },
    "services": [
      {
        "name": "W32Time",
        "display_name": "Windows Time",
        "state": "Running",
        "startup_type": "Automatic",
        "tier": 2,
        "status": "ok"
      }
    ]
  }
}
```

### 10.4 Boot Time - Arranque Degradado

```json
{
  "boot_time": {
    "last_boot_time": "2026-04-14T10:15:32",
    "boot_duration_seconds": 145,
    "source": "event_log",
    "status": "degraded"
  }
}
```

---

## 📝 Checklist de Implementación

Cuando Codex (el becario) termine el desarrollo, validar:

### Funcionalidad Básica
- [ ] El script se ejecuta sin errores en PowerShell 5.1
- [ ] Genera un archivo de config por defecto si no existe
- [ ] Lee correctamente el archivo de config JSON
- [ ] Todas las métricas se recogen correctamente (ahora 8 métricas)

### Métricas Individuales
- [ ] CPU: `Get-CimInstance Win32_Processor` funciona
- [ ] Memoria: Cálculos en KB son correctos
- [ ] Disco: Detecta C: o $env:SystemDrive
- [ ] Eventos: Filtra por Provider, EventID y combinaciones
- [ ] Dominio: `Test-ComputerSecureChannel` maneja errores
- [ ] Uptime: Calcula días correctamente
- [ ] **Boot Time: Intenta Event ID 100 primero, fallback a WMI** ⭐
- [ ] **Boot Time: Convierte UTC a local correctamente** ⭐
- [ ] **Boot Time: Calcula status según thresholds** ⭐
- [ ] Servicios: Determina status según StartType y State

### Formato de Salida
- [ ] El JSON generado es válido
- [ ] Los timestamps están en formato ISO 8601 UTC (excepto boot_time que es local)
- [ ] Los números tienen el redondeo correcto (2 decimales)
- [ ] Los estados son: ok, optimal, warning, degraded, critical, error, not_available, unknown

### Manejo de Errores
- [ ] Cada métrica tiene su propio try-catch
- [ ] Si una métrica falla, las demás continúan
- [ ] Los errores se loguean pero no detienen la ejecución
- [ ] El JSON final siempre se genera (incluso con errores)
- [ ] **Boot Time maneja correctamente el fallback Event Log → WMI** ⭐

### Casos Edge
- [ ] Funciona en equipo sin dominio
- [ ] Funciona si C: no existe (usa $env:SystemDrive)
- [ ] Funciona si EventLog no es accesible
- [ ] Servicios no instalados marcan status "not_available"
- [ ] Print Spooler deshabilitado NO penaliza
- [ ] **Boot Time funciona si Event ID 100 no existe (usa WMI)** ⭐
- [ ] **Boot Time maneja timestamps con nanosegundos correctamente** ⭐

### Performance
- [ ] Ejecución completa toma menos de 60 segundos
- [ ] No hay memory leaks evidentes
- [ ] No deja procesos huérfanos

---

## 🎓 Notas para el Becario (Codex)

Hola Codex, bienvenido al equipo. Este es tu primer proyecto y queremos que lo hagas bien. Aquí van algunos consejos:

### ✅ DO's (Haz esto)
1. **Lee TODO el documento** antes de escribir código
2. **Sigue la estructura exacta del JSON** especificada en la sección 6
3. **Usa try-catch en cada métrica** para resiliencia
4. **Testea en un equipo real** antes de entregar
5. **Comenta tu código** explicando las decisiones no obvias
6. **Para Boot Time: Intenta Event Log primero, luego WMI** ⭐

### ❌ DON'Ts (No hagas esto)
1. **NO uses módulos externos** (solo cmdlets nativos)
2. **NO asumas que todo funciona** (siempre maneja errores)
3. **NO calcules el score** (eso lo hace el backend)
4. **NO incluyas mensajes de error completos** en el JSON de eventos
5. **NO hagas el código "más inteligente"** de lo especificado (KISS)
6. **NO confundas UTC con local en boot_time** ⭐

### 🐛 Testing
Prueba el script en:
- Un equipo sano (todo OK)
- Un equipo degradado (disco lleno, RAM alta)
- Un equipo sin dominio
- Un equipo con Symantec Endpoint Protection
- Un equipo sin Symantec (para ver el "not_available")
- **Un equipo donde Event ID 100 esté disponible** ⭐
- **Un equipo donde Event ID 100 NO esté disponible (forzar WMI)** ⭐

### 📋 Entregables
1. `health_monitor.ps1` - Script principal
2. `health_monitor_config.json` - Config por defecto (versión 1.1)
3. `README.md` - Instrucciones de instalación
4. `test_output.json` - Ejemplo de output real de tu equipo de testing

---

## 🚀 Próximos Pasos

1. Codex desarrolla el plugin según esta spec
2. Senior (yo) reviso el código
3. Testing en entorno de desarrollo
4. Despliegue en piloto (5-10 equipos)
5. Análisis de resultados
6. Despliegue masivo

---

## 📊 Resumen de Cambios v1.1

### Nuevas Métricas
- ✅ **Boot Time** (tiempo de arranque)
  - Fuente primaria: Event ID 100 (Diagnostics-Performance)
  - Fuente fallback: WMI (Win32_OperatingSystem)
  - Status: optimal, ok, degraded, critical, unknown, error

### Nuevos Thresholds en Config
```json
"boot_time": {
  "optimal": 60,
  "normal": 120,
  "degraded": 180
}
```

### Nuevos Status
- `"optimal"`: Solo para boot_time (< 60s)
- `"degraded"`: Solo para boot_time (120-179s)
- `"unknown"`: Solo para boot_time cuando no hay duración (WMI fallback)

### Cambios en Execution Metadata
- `metrics_attempted`: 7 → **8**

---

**Firma:**  
Senior Developer (Claude)  
Fecha: 2026-04-14  
Versión: 1.1.0

---

**Este documento es la única fuente de verdad para el desarrollo del plugin. Cualquier duda, consultar antes de implementar.**
