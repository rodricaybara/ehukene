# IVANTI EPM — Paquete: Instalación Agente EHUkene
**Versión:** 1.0  
**Compatibilidad:** Ivanti EPM 2021+, Windows 10/11, Server 2016/2019/2022  
**Proyecto:** EHUkene — Sistema de monitorización de endpoints UPV/EHU

---

## Descripción

Paquete de distribución para el despliegue masivo del agente EHUkene, un sistema
de monitorización de endpoints que recopila métricas de batería, uso de software
y tiempos de arranque.

El agente se ejecuta automáticamente al inicio de sesión de cualquier usuario y
envía los datos al backend centralizado vía API REST.

---

## Contenido del paquete

```
Install-EHUkene-Agent\
├── agent.exe                           ← Ejecutable compilado (PyInstaller)
├── config.json                         ← Configuración del agente
├── software_targets.json               ← Lista de software a monitorizar
├── Install-EHUkene-Agent.ps1          ← Script principal de instalación
├── Launch-Install-EHUkene.cmd         ← Wrapper para Ivanti (punto de entrada)
└── README.md                           ← Esta documentación
```

> ⚠️ **IMPORTANTE:** Los tres primeros ficheros deben obtenerse del repositorio
> del proyecto EHUkene antes de crear el paquete en Ivanti.

---

## Flujo de ejecución

```
Ivanti EPM (Local System)
    │
    └─► Launch-Install-EHUkene.cmd
            │
            └─► Install-EHUkene-Agent.ps1
                    │
                    ├── FASE 1: Validar privilegios Admin/SYSTEM
                    ├── FASE 2: ¿Agente ya instalado? → salida 21 (idempotente)
                    ├── FASE 3: Localizar ficheros del paquete (agent.exe, config.json, etc.)
                    ├── FASE 4: Registrar dispositivo en backend → obtener API key única
                    ├── FASE 5: Copiar ficheros a C:\Program Files\EHUkene\
                    ├── FASE 6: Actualizar config.json con la API key
                    ├── FASE 7: Crear tarea programada en Task Scheduler
                    ├── FASE 8: Verificación multicapa (ficheros + tarea + config válido)
                    └── FASE 9: Auditoría (registro local + CSV centralizado)
                            │
                            └─► Código de salida → Ivanti EPM
```

---

## CONFIGURACIÓN PREVIA OBLIGATORIA

### 1. Backend EHUkene

El backend debe estar operativo y accesible desde los equipos cliente. Verificar:

```powershell
# Desde un equipo cliente de prueba, comprobar accesibilidad
Invoke-RestMethod -Uri "https://ehukene.ehu.eus/api/health" -Method GET
```

### 2. Cuenta de servicio para la tarea programada

Crear en Active Directory una cuenta de servicio con estos requisitos:

| Propiedad | Valor |
|-----------|-------|
| **Nombre** | `svc_ehukene` |
| **UPN** | `svc_ehukene@adm.ehu.es` |
| **Contraseña** | Segura, sin caducidad |
| **Miembro de** | Grupo que tenga privilegios de administrador local en equipos destino |
| **Privilegios** | "Iniciar sesión como proceso por lotes" |

> ⚠️ **Seguridad:** La contraseña de esta cuenta quedará en texto claro en el script
> PowerShell. Asegúrate de que el paquete Ivanti tenga permisos restringidos en la
> consola EPM (solo accesible por administradores).

### 3. Editar el script PowerShell

Abrir `Install-EHUkene-Agent.ps1` y configurar estos valores en la sección `$Script:Config`:

```powershell
# --- Backend EHUkene ---
BackendRegisterUrl   = "https://ehukene.ehu.eus/api/devices/register"
BackendTimeout       = 10

# --- Tarea programada ---
TaskUser             = "ADMEHU\svc_ehukene"
TaskPassword         = "CONTRASEÑA_REAL_AQUI"

# --- Auditoría ---
AuditRegistryPath   = "HKLM:\SOFTWARE\UPVEHU\EHUkene"
AuditCsvPath        = "\\nas-landesk.adm.ehu.es\landesk_paquetes$\scripts\auditoria_ehukene\auditoria_install_ehukene.csv"
```

> **Nota sobre la API key:** El script la obtiene automáticamente del backend durante
> la instalación (FASE 4). No hay que configurarla manualmente.

### 4. Configuración de auditoría

#### Opción A — Registro local (recomendado)

Añadir estas líneas al `ldappl3.ini` del servidor Ivanti para que el inventario
recoja los datos de instalación:

```ini
[Custom Data - Registry Items]
KEY=HKLM, SOFTWARE\UPVEHU\EHUkene\Install-EHUkene-Agent, Estado,  Custom Data - EHUkene - Install Agent - Estado
KEY=HKLM, SOFTWARE\UPVEHU\EHUkene\Install-EHUkene-Agent, Codigo,  Custom Data - EHUkene - Install Agent - Codigo
KEY=HKLM, SOFTWARE\UPVEHU\EHUkene\Install-EHUkene-Agent, Fecha,   Custom Data - EHUkene - Install Agent - Fecha
KEY=HKLM, SOFTWARE\UPVEHU\EHUkene\Install-EHUkene-Agent, Detalle, Custom Data - EHUkene - Install Agent - Detalle
```

Tras editar el `ldappl3.ini`, publicar el cambio desde la consola EPM:
`Configure → Services → Inventory → Manage Software List → Custom Data → Registry Items`

#### Opción B — CSV centralizado

Crear el directorio compartido y configurar permisos:

```
\\nas-landesk.adm.ehu.es\landesk_paquetes$\scripts\auditoria_ehukene\
```

Permisos NTFS:
- `Domain Computers`: Modificar (para que Local System pueda escribir)
- `Administradores`: Control total

Si Local System no tiene acceso, descomentar y configurar las credenciales en el script:

```powershell
AuditCsvUser        = "ADMEHU\svc_auditoria"
AuditCsvPassword    = "Contraseña"
```

---

## Configuración del paquete en Ivanti EPM

### 1. Preparar el paquete

1. Obtener los ficheros del proyecto EHUkene:
   - `agent.exe` (ejecutable compilado con PyInstaller)
   - `config.json` (plantilla de configuración)
   - `software_targets.json` (lista de software a monitorizar)

2. Colocar **todos** los ficheros en la carpeta del paquete Ivanti:
   ```
   ├── agent.exe
   ├── config.json
   ├── software_targets.json
   ├── Install-EHUkene-Agent.ps1
   ├── Launch-Install-EHUkene.cmd
   └── README.md
   ```

3. Editar `Install-EHUkene-Agent.ps1` con la configuración del entorno (ver sección anterior)

### 2. Crear el paquete de software

1. Abrir **Ivanti EPM Console**
2. Ir a `Tools → Distribution → Software Distribution`
3. Clic en **New Package** → **Software Package**
4. Datos básicos:
   - **Package Name:** `Install-EHUkene-Agent`
   - **Version:** `1.0`
   - **Description:** `Instalación del agente EHUkene para monitorización de endpoints`

### 3. Configurar la tarea

En la pestaña **Install**:

| Campo | Valor |
|-------|-------|
| **Command** | `Launch-Install-EHUkene.cmd` |
| **Working Directory** | `.\` |
| **Run As** | `Local System Account` ✅ |
| **Wait for process** | `Yes` |
| **Timeout** | `300` segundos (5 minutos) |

> **Nota:** El timeout de 5 minutos es más que suficiente. La instalación solo
> copia ficheros y crea una tarea programada; no hay procesos largos de instalación.

### 4. Códigos de retorno

En la pestaña **Return Codes**, añadir:

| Código | Tipo | Descripción |
|--------|------|-------------|
| `0` | Success | Instalación exitosa |
| `21` | Success | Agente ya estaba instalado (comportamiento idempotente) |
| `20` | Failure | agent.exe no encontrado en el paquete |
| `22` | Failure | Verificación post-instalación fallida |
| `23` | Failure | Error al crear la tarea programada |
| `24` | Failure | Error de configuración (API key o config.json) |
| `25` | Failure | Excepción inesperada |

---

## Instalación en el endpoint

El script crea esta estructura en cada equipo:

```
C:\Program Files\EHUkene\
├── agent.exe
├── config.json                    ← Actualizado con API key única
└── config\
    └── software_targets.json

C:\ProgramData\EHUkene\
├── agent.log                      ← Log rotativo (3 × 5 MB)
└── last_run.json                  ← Control de duplicados
```

### Tarea programada creada

| Propiedad | Valor |
|-----------|-------|
| **Nombre** | `EHUkene Agent` |
| **Trigger** | Al inicio de sesión — cualquier usuario |
| **Acción** | `C:\Program Files\EHUkene\agent.exe` |
| **Usuario** | `ADMEHU\svc_ehukene` |
| **Privilegios** | Ejecutar con privilegios más altos |

---

## Logs generados en el cliente

Ubicación: `C:\ProgramData\Ivanti\Logs\EHUkene\`

| Archivo | Descripción |
|---------|-------------|
| `Install-EHUkene_YYYYMMDD_HHMMSS.log` | Log principal del script PowerShell |
| `Wrapper_YYYYMMDD_HHMMSS.log` | Log del wrapper CMD |

Los logs se purgan automáticamente tras **30 días**.

### Ejemplo de log exitoso

```
======================================================================
  IVANTI - INSTALACION AGENTE EHUKENE
======================================================================
10:05:01 [INFO   ] Inicio       : 20/03/2026 10:05:01
10:05:01 [INFO   ] Equipo       : WORKSTATION-42
10:05:01 [INFO   ] Usuario      : NT AUTHORITY\SYSTEM

=== FASE 1: VALIDACIONES PREVIAS ===
10:05:02 [SUCCESS] Contexto: SYSTEM (ejecucion via Ivanti Agent).

=== FASE 2: COMPROBACION DE INSTALACION PREVIA ===
10:05:02 [SUCCESS] Agente EHUkene no detectado. Procediendo con la instalacion.

=== FASE 3: LOCALIZACION DE FICHEROS DEL PAQUETE ===
10:05:02 [SUCCESS] [OK] agent.exe encontrado
10:05:02 [SUCCESS] [OK] config.json encontrado
10:05:02 [SUCCESS] [OK] software_targets.json encontrado

=== FASE 4: REGISTRO DEL DISPOSITIVO EN EL BACKEND ===
10:05:03 [INFO   ] Registrando dispositivo en el backend EHUkene...
10:05:03 [INFO   ]   URL      : https://ehukene.ehu.eus/api/devices/register
10:05:03 [INFO   ]   Hostname : WORKSTATION-42
10:05:04 [SUCCESS] [OK] API key obtenida correctamente.

=== FASE 5: INSTALACION DE FICHEROS ===
10:05:05 [SUCCESS] Creado directorio: C:\Program Files\EHUkene
10:05:05 [SUCCESS] [OK] Copiado: agent.exe
10:05:05 [SUCCESS] [OK] Copiado: config.json
10:05:05 [SUCCESS] [OK] Copiado: software_targets.json

=== FASE 6: CONFIGURACION DE API KEY ===
10:05:06 [SUCCESS] [OK] config.json actualizado con API key.

=== FASE 7: CREACION DE TAREA PROGRAMADA ===
10:05:07 [INFO   ] Creando tarea programada en Task Scheduler...
10:05:07 [SUCCESS] [OK] Tarea programada creada correctamente.

=== FASE 8: VERIFICACION POST-INSTALACION ===
10:05:08 [SUCCESS] [OK] agent.exe presente
10:05:08 [SUCCESS] [OK] config.json valido
10:05:08 [SUCCESS] [OK] Tarea programada presente

=== AUDITORIA DE INSTALACION ===
10:05:09 [DEBUG  ] [AUDITORIA-REG] Valores escritos en registro local.
10:05:09 [DEBUG  ] [AUDITORIA-CSV] Linea aniadida al CSV centralizado.

======================================================================
FIN DEL PROCESO : 20/03/2026 10:05:09
RESULTADO       : EXITO - Agente EHUkene instalado y tarea programada configurada correctamente.
Codigo de salida: 0
======================================================================
```

---

## Códigos de salida

| Código | Tipo Ivanti | Descripción |
|--------|-------------|-------------|
| `0` | ✅ Success | Agente instalado correctamente |
| `21` | ℹ️ Success* | Agente ya estaba instalado (idempotente) |
| `20` | ❌ Failure | agent.exe no encontrado en el paquete |
| `22` | ❌ Failure | Verificación post-instalación fallida |
| `23` | ❌ Failure | Error al crear la tarea programada |
| `24` | ❌ Failure | Error de configuración (API key o config.json) |
| `25` | ❌ Failure | Excepción inesperada |

> *El código `21` se configura como Success en Ivanti para garantizar comportamiento idempotente.

---

## Verificación post-despliegue

### En el equipo cliente

```powershell
# 1. Verificar ficheros instalados
Test-Path "C:\Program Files\EHUkene\agent.exe"
Test-Path "C:\Program Files\EHUkene\config.json"

# 2. Verificar tarea programada
Get-ScheduledTask -TaskName "EHUkene Agent"

# 3. Verificar config.json válido
$config = Get-Content "C:\Program Files\EHUkene\config.json" | ConvertFrom-Json
$config.api_key  # Debe tener un valor
$config.api_url  # Debe apuntar al backend

# 4. Verificar auditoría en registro local
Get-ItemProperty "HKLM:\SOFTWARE\UPVEHU\EHUkene\Install-EHUkene-Agent"
```

### En el backend EHUkene

```bash
# Verificar que el dispositivo se registró correctamente
curl -X GET https://ehukene.ehu.eus/api/devices/WORKSTATION-42
```

---

## Monitorización del despliegue en Ivanti

### Consultas por Custom Data

Una vez que el inventario haya recogido los datos del registro:

**Equipos con instalación exitosa:**
```
Custom Data - EHUkene - Install Agent - Codigo = "0"
```

**Equipos con error en la instalación:**
```
Custom Data - EHUkene - Install Agent - Codigo exists
  AND
Custom Data - EHUkene - Install Agent - Codigo != "0"
  AND
Custom Data - EHUkene - Install Agent - Codigo != "21"
```

**Equipos pendientes de instalación:**
```
Custom Data - EHUkene - Install Agent - Codigo not exists
```

### CSV centralizado

Abrir el CSV de auditoría para análisis histórico:

```
\\nas-landesk.adm.ehu.es\landesk_paquetes$\scripts\auditoria_ehukene\auditoria_install_ehukene.csv
```

Columnas disponibles:
- Timestamp
- Equipo
- SO
- Arquitectura
- Paquete
- CodigoSalida
- Estado
- Detalle
- UsuarioContexto

---

## Resolución de problemas

| Código | Causa probable | Acción |
|--------|---------------|--------|
| `20` | `agent.exe` no está en el paquete | Verificar que el fichero se copió correctamente a la carpeta del paquete en Ivanti |
| `22` | Verificación fallida | Revisar log completo; puede ser un problema de permisos en `C:\Program Files\` |
| `23` | Error creando tarea programada | Verificar que la cuenta `svc_ehukene` existe en AD y tiene privilegios de administrador local |
| `24` | Error de configuración | Verificar conectividad con el backend: `Test-NetConnection ehukene.ehu.eus -Port 443` |
| `25` | Excepción inesperada | Revisar `Install-EHUkene_*.log` en `C:\ProgramData\Ivanti\Logs\EHUkene\` |

### Problemas de conectividad con el backend

Si el código de salida es `24` y en el log aparece:

```
[ERROR] No se pudo obtener API key del backend.
```

Verificar:

1. **Conectividad de red:**
   ```powershell
   Test-NetConnection ehukene.ehu.eus -Port 443
   ```

2. **Endpoint activo:**
   ```powershell
   Invoke-RestMethod -Uri "https://ehukene.ehu.eus/api/health"
   ```

3. **Certificado SSL válido:**
   Si hay error de certificado, puede ser necesario añadir el certificado raíz
   al almacén de certificados del equipo.

### La tarea programada no se crea (código 23)

Causas comunes:

1. **Cuenta de servicio inexistente o contraseña incorrecta:**
   - Verificar que `ADMEHU\svc_ehukene` existe en AD
   - Probar login manual con esas credenciales

2. **Falta el privilegio "Iniciar sesión como proceso por lotes":**
   - Añadir `svc_ehukene` a este privilegio vía GPO o localmente

3. **Task Scheduler deshabilitado:**
   ```powershell
   Get-Service Schedule | Start-Service
   ```

---

## Preguntas frecuentes

**¿El agente necesita reinicio tras la instalación?**

No. El agente se ejecutará automáticamente en el siguiente inicio de sesión de
cualquier usuario gracias a la tarea programada.

**¿Qué hace el agente exactamente?**

Recopila tres tipos de datos:
1. Métricas de batería (portátiles)
2. Uso de software (según `software_targets.json`)
3. Tiempos de arranque del equipo

Los datos se envían al backend EHUkene vía API REST.

**¿Con qué frecuencia se ejecuta el agente?**

Al inicio de sesión de cualquier usuario. El propio agente controla duplicados
internamente usando `last_run.json` para evitar envíos múltiples el mismo día.

**¿Puedo relanzar el paquete si falló?**

Sí. El script es **idempotente**:
- Si el agente ya está instalado correctamente, devuelve código `21` sin reinstalar.
- Si la instalación previa está incompleta, la completa.

**¿Cómo desinstalar el agente?**

Crear un paquete de desinstalación que:
1. Elimine la tarea programada: `Unregister-ScheduledTask -TaskName "EHUkene Agent"`
2. Elimine los directorios: `Remove-Item "C:\Program Files\EHUkene" -Recurse -Force`
3. Elimine los datos: `Remove-Item "C:\ProgramData\EHUkene" -Recurse -Force`

**¿Los logs del agente ocupan mucho espacio?**

No. El agente usa log rotativo de máximo 3 ficheros de 5 MB cada uno (15 MB total).

**¿Dónde se almacena la API key?**

En `C:\Program Files\EHUkene\config.json` en texto claro. Los permisos NTFS de
`C:\Program Files\` protegen el fichero contra acceso de usuarios no privilegiados.

---

*UPV/EHU · Servicio de Informática · Proyecto EHUkene · v1.0*
