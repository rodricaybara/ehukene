# Control de Versiones — software_targets.json

**Versión del documento:** 1.0  
**Fecha:** Abril 2026  
**Proyecto:** EHUkene Agent

---

## Descripción

El fichero `software_targets.json` contiene la lista de aplicaciones que el agente EHUkene monitoriza en los equipos. Este fichero incluye **control de versiones** para gestionar actualizaciones de forma inteligente.

---

## Estructura del fichero

```json
{
  "version": "1.1.0",
  "last_updated": "2026-04-09",
  "description": "Lista de software a monitorizar - UPV/EHU",
  "maintainer": "Vicegerencia TIC - UPV/EHU",
  "targets": [
    {
      "name": "adobe_acrobat_reader",
      "display_name": "Adobe Acrobat Reader",
      "package_name": "*Adobe Acrobat Reader*",
      "registry_keys": [
        "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Installer\\UserData\\S-1-5-18\\Products\\68AB67CA7DA74301B744CAF070E41400\\InstallProperties"
      ],
      "registry_version_value": "DisplayVersion",
      "prefetch_pattern": "ACRORD32.EXE-*.pf"
    }
  ]
}
```

### Campos obligatorios a nivel raíz:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `version` | String | **Obligatorio.** Versión semántica del fichero (ej: "1.0.0", "2.1.3") |
| `targets` | Array | **Obligatorio.** Lista de aplicaciones a monitorizar |

### Campos opcionales a nivel raíz (metadatos):

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `last_updated` | String | Fecha de la última actualización (formato: YYYY-MM-DD) |
| `description` | String | Descripción del propósito del fichero |
| `maintainer` | String | Responsable del mantenimiento |

### Campos de cada aplicación (`targets`):

| Campo | Tipo | Descripción | Ejemplo |
|-------|------|-------------|---------|
| `name` | String | **Obligatorio.** Identificador técnico único (snake_case) | `"adobe_acrobat_reader"` |
| `display_name` | String | **Obligatorio.** Nombre descriptivo para mostrar | `"Adobe Acrobat Reader"` |
| `package_name` | String | **Obligatorio.** Patrón de búsqueda del paquete (admite wildcards) | `"*Adobe Acrobat Reader*"` |
| `registry_keys` | Array | **Obligatorio.** Lista de rutas de registro donde buscar la aplicación | `["SOFTWARE\\...\\InstallProperties"]` |
| `registry_version_value` | String | **Obligatorio.** Nombre del valor de registro que contiene la versión | `"DisplayVersion"` o `"Version"` |
| `prefetch_pattern` | String | **Obligatorio.** Patrón del fichero Prefetch para detectar ejecuciones | `"ACRORD32.EXE-*.pf"` |

> **Nota:** El agente EHUkene usa estos campos para:
> - **`registry_keys`**: Detectar si la aplicación está instalada y obtener su versión
> - **`prefetch_pattern`**: Detectar si la aplicación se ha ejecutado recientemente (Windows Prefetch)
> - **`package_name`**: Correlacionar con información del inventario de software

---

## Cómo funciona el control de versiones

### Durante la instalación/actualización del paquete Ivanti:

El script `Install-EHUkene-Agent.ps1` compara la versión del fichero del paquete con la versión instalada en el equipo:

```
┌─────────────────────────────────────────────────────────────┐
│ ¿Existe software_targets.json en el equipo?                 │
└────────────┬────────────────────────────────────────────────┘
             │
      ┌──────┴──────┐
      │             │
     NO            SÍ
      │             │
      │             └─► Leer versión del equipo
      │                      │
      └─────────────────┬────┴─────────────────┐
                        │                      │
                  Versión paquete         Versión paquete
                   > versión equipo       ≤ versión equipo
                        │                      │
                   SOBRESCRIBIR          NO SOBRESCRIBIR
                        │                      │
                   (actualización)        (ya actualizado)
```

### Casos especiales:

1. **Primera instalación:** No existe el fichero → se copia del paquete
2. **Fichero antiguo sin campo `version`:** Se sobrescribe automáticamente (ver sección "Migración" más abajo)
3. **JSON corrupto:** Error al leer el fichero → se sobrescribe con el del paquete
4. **Versión superior en equipo:** El equipo tiene versión mayor → NO se sobrescribe (se registra WARNING en el log)

---

## Migración desde ficheros sin control de versiones

Si en vuestro entorno existen equipos con una **versión antigua de `software_targets.json` que NO tiene el campo `version`**, el script los gestiona automáticamente:

### Comportamiento durante la migración:

```
┌─────────────────────────────────────────────────────────────┐
│ Equipo tiene software_targets.json SIN campo "version"      │
└────────────┬────────────────────────────────────────────────┘
             │
             ├─► 1. Se registra WARNING en el log
             ├─► 2. Se SOBRESCRIBE con el fichero del paquete
             ├─► 3. Se crea backup del fichero antiguo
             └─► 4. Instalación continúa normalmente (no es error)
```

### Ejemplo de log durante migración:

```
Gestionando software_targets.json...
  Version en paquete: 1.1.0
  [AVISO] El fichero del equipo NO tiene campo 'version'. Sobrescribiendo...
  Backup creado: C:\Program Files\EHUkene\config\software_targets.json.backup_20260515_093022
  [ACTUALIZADO] Fichero sin version reemplazado por version 1.1.0
```

**Ventajas de este comportamiento:**

✅ **No requiere intervención manual** - la migración es automática  
✅ **Preserva el fichero antiguo** - se crea backup por seguridad  
✅ **Trazabilidad completa** - queda registrado en el log  
✅ **No interrumpe la instalación** - se trata como WARNING, no como ERROR

---

## Versionado semántico (recomendado)

Seguir el formato **MAJOR.MINOR.PATCH**:

```
1.0.0 → 1.0.1 → 1.1.0 → 2.0.0
```

### Incrementar versión cuando:

| Tipo de cambio | Incrementar | Ejemplo |
|----------------|-------------|---------|
| **MAJOR** (primer dígito) | Cambios importantes que rompen compatibilidad o reestructuración completa | `1.5.2` → `2.0.0` |
| **MINOR** (segundo dígito) | Añadir nuevas aplicaciones a la lista | `1.5.2` → `1.6.0` |
| **PATCH** (tercer dígito) | Corrección de errores (nombre mal escrito, categoría incorrecta) | `1.5.2` → `1.5.3` |

---

## Flujo de trabajo para actualizar la lista

### 1. Modificar el fichero `software_targets.json` del paquete

Editar el fichero que se incluirá en el paquete Ivanti:

```json
{
  "version": "1.1.0",    ← Incrementar versión
  "last_updated": "2026-05-15",
  "targets": [
    {
      "name": "Nueva Aplicación",
      "executable": "app.exe",
      "process_name": "app",
      "category": "utilidades"
    }
  ]
}
```

### 2. Actualizar el paquete Ivanti

1. Abrir **Ivanti EPM Console**
2. Ir al paquete `Install-EHUkene-Agent`
3. Reemplazar el fichero `software_targets.json` con la nueva versión
4. **Incrementar la versión del paquete Ivanti** (ej: `1.0` → `1.1`)

### 3. Desplegar a los equipos

- Crear una nueva tarea de distribución (o usar la existente)
- Los equipos que **ya tienen el agente** ejecutarán el paquete de nuevo
- El código de salida será `21` (ya instalado) pero `software_targets.json` se actualizará si hay nueva versión

### 4. Verificar en el log del cliente

En `C:\ProgramData\Ivanti\Logs\EHUkene\Install-EHUkene_*.log`:

```
=== FASE 4: INSTALACION DE FICHEROS ===
Gestionando software_targets.json...
  Version en paquete: 1.1.0
  Version en equipo : 1.0.0
  Backup creado: C:\Program Files\EHUkene\config\software_targets.json.backup_20260515_093022
  [ACTUALIZADO] Nueva version: 1.0.0 -> 1.1.0
```

---

## Ejemplos de uso

### Ejemplo 1: Añadir nueva aplicación

**Situación:** Queremos añadir "Slack" a la lista de software monitorizado.

**Acción:**

```json
{
  "version": "1.2.0",    ← Era 1.1.0, ahora 1.2.0 (MINOR - nueva aplicación)
  "last_updated": "2026-05-15",
  "targets": [
    // ... aplicaciones existentes ...
    {
      "name": "slack",
      "display_name": "Slack",
      "package_name": "*Slack*",
      "registry_keys": [
        "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Slack",
        "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Slack"
      ],
      "registry_version_value": "DisplayVersion",
      "prefetch_pattern": "SLACK.EXE-*.pf"
    }
  ]
}
```

**Resultado en equipos:**
- Equipos con versión `1.1.0` → se actualiza a `1.2.0`
- Equipos con versión `1.2.0` → sin cambios

---

### Ejemplo 2: Corregir ruta de registro incorrecta

**Situación:** La ruta de registro de Chrome está mal especificada.

**Acción:**

```json
{
  "version": "1.1.1",    ← Era 1.1.0, ahora 1.1.1 (PATCH - corrección)
  "last_updated": "2026-05-15",
  "targets": [
    {
      "name": "google_chrome",
      "display_name": "Google Chrome",
      "package_name": "*Google Chrome*",
      "registry_keys": [
        "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Google Chrome",
        "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Google Chrome"
      ],
      "registry_version_value": "DisplayVersion",    ← Corregido (antes: "Version")
      "prefetch_pattern": "CHROME.EXE-*.pf"
    }
  ]
}
```

**Resultado en equipos:**
- Equipos con versión `1.1.0` → se actualiza a `1.1.1` (corrección aplicada)
- Equipos con versión `1.1.1` → sin cambios

---

### Ejemplo 3: Cambio de estructura (MAJOR)

**Situación:** Se decide añadir un nuevo campo obligatorio a todas las aplicaciones o cambiar el formato del JSON.

**Acción:**

```json
{
  "version": "2.0.0",    ← Era 1.5.2, ahora 2.0.0 (MAJOR - cambio de estructura)
  "last_updated": "2026-05-15",
  "schema_version": "2",  ← Nueva estructura
  "targets": [
    {
      "name": "google_chrome",
      "display_name": "Google Chrome",
      "package_name": "*Google Chrome*",
      "registry_keys": [
        "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Google Chrome"
      ],
      "registry_version_value": "DisplayVersion",
      "prefetch_pattern": "CHROME.EXE-*.pf",
      "telemetry_enabled": true,    ← Nuevo campo obligatorio
      "priority": "high"             ← Nueva estructura
    }
  ]
}
```

> ⚠️ **IMPORTANTE:** Cambios MAJOR requieren actualizar también el código del agente para que entienda la nueva estructura.

---

## Backups automáticos

Cada vez que se **sobrescribe** un fichero existente, el script crea un backup automático:

```
C:\Program Files\EHUkene\config\
├── software_targets.json                           ← Versión actual
├── software_targets.json.backup_20260515_093022    ← Backup automático
└── software_targets.json.backup_20260601_141500    ← Otro backup
```

**Formato del backup:** `software_targets.json.backup_YYYYMMDD_HHMMSS`

Los backups **NO se purgan automáticamente**. Si se acumulan demasiados, limpiar manualmente los más antiguos.

---

## Troubleshooting

### El script no actualiza aunque haya nueva versión

**Causa probable:** Error en el formato de versión.

**Verificar:**

1. Abrir el log: `C:\ProgramData\Ivanti\Logs\EHUkene\Install-EHUkene_*.log`
2. Buscar la sección:
   ```
   Gestionando software_targets.json...
   ```
3. Ver qué versiones se detectaron

**Solución:** Asegurarse de que ambos ficheros (paquete y equipo) tienen el campo `version` con formato semántico válido (`X.Y.Z`).

---

### El equipo tiene versión superior a la del paquete

**Situación:** En el log aparece:

```
[AVISO] El equipo tiene una version SUPERIOR (2.0.0 > 1.5.0)
        No se sobrescribe. Revisar si es correcto.
```

**Causas posibles:**

1. **Prueba manual:** Se instaló manualmente una versión más reciente en ese equipo concreto
2. **Rollback del paquete:** Se volvió a una versión anterior del paquete por error
3. **Equipo piloto:** Ese equipo tiene una versión beta/test

**Acción:**

- Si es correcto → no hacer nada (el equipo mantiene su versión)
- Si es un error → incrementar la versión del paquete para que sea superior a `2.0.0`

---

### El fichero del paquete no tiene campo `version`

**Situación:** En el log aparece:

```
[AVISO] El fichero del paquete NO tiene campo 'version'. Usando '0.0.0'.
```

**Solución:** Añadir el campo `version` al fichero `software_targets.json` del paquete:

```json
{
  "version": "1.0.0",
  "targets": [ ... ]
}
```

---

## Consultas útiles

### Ver versión actual y número de aplicaciones en un equipo

```powershell
# Desde el equipo cliente
$json = Get-Content "C:\Program Files\EHUkene\config\software_targets.json" | ConvertFrom-Json
Write-Host "Version actual: $($json.version)"
Write-Host "Ultima actualizacion: $($json.last_updated)"
Write-Host "Numero de aplicaciones: $($json.targets.Count)"
Write-Host "`nAplicaciones monitorizadas:"
$json.targets | ForEach-Object { Write-Host "  - $($_.display_name) ($($_.name))" }
```

### Verificar integridad del fichero

```powershell
# Comprobar que todos los campos obligatorios están presentes
$json = Get-Content "C:\Program Files\EHUkene\config\software_targets.json" | ConvertFrom-Json

# Verificar campos raíz
if (-not $json.version) { Write-Host "ERROR: Falta campo 'version'" -ForegroundColor Red }
if (-not $json.targets) { Write-Host "ERROR: Falta campo 'targets'" -ForegroundColor Red }

# Verificar campos de cada aplicación
$json.targets | ForEach-Object {
    $app = $_
    $missing = @()
    if (-not $app.name) { $missing += "name" }
    if (-not $app.display_name) { $missing += "display_name" }
    if (-not $app.package_name) { $missing += "package_name" }
    if (-not $app.registry_keys) { $missing += "registry_keys" }
    if (-not $app.registry_version_value) { $missing += "registry_version_value" }
    if (-not $app.prefetch_pattern) { $missing += "prefetch_pattern" }
    
    if ($missing.Count -gt 0) {
        Write-Host "ERROR en $($app.name): Faltan campos: $($missing -join ', ')" -ForegroundColor Red
    }
}
```

### Ver todas las versiones (backups)

```powershell
Get-ChildItem "C:\Program Files\EHUkene\config\software_targets.json*" |
    Select-Object Name, LastWriteTime, @{N='Size(KB)';E={[math]::Round($_.Length/1KB,2)}}
```

### Comparar dos versiones del fichero

```powershell
# Comparar el fichero actual con un backup
$actual = Get-Content "C:\Program Files\EHUkene\config\software_targets.json" | ConvertFrom-Json
$backup = Get-Content "C:\Program Files\EHUkene\config\software_targets.json.backup_20260515_093022" | ConvertFrom-Json

Write-Host "Version actual: $($actual.version)"
Write-Host "Version backup: $($backup.version)"
Write-Host "`nAplicaciones en actual: $($actual.targets.Count)"
Write-Host "Aplicaciones en backup: $($backup.targets.Count)"

# Aplicaciones añadidas
$nuevas = $actual.targets | Where-Object { $_.name -notin $backup.targets.name }
if ($nuevas) {
    Write-Host "`nAplicaciones AÑADIDAS:" -ForegroundColor Green
    $nuevas | ForEach-Object { Write-Host "  + $($_.display_name)" -ForegroundColor Green }
}

# Aplicaciones eliminadas
$eliminadas = $backup.targets | Where-Object { $_.name -notin $actual.targets.name }
if ($eliminadas) {
    Write-Host "`nAplicaciones ELIMINADAS:" -ForegroundColor Red
    $eliminadas | ForEach-Object { Write-Host "  - $($_.display_name)" -ForegroundColor Red }
}
```

### Restaurar un backup

```powershell
# Listar backups disponibles
Get-ChildItem "C:\Program Files\EHUkene\config\software_targets.json.backup_*" |
    Sort-Object LastWriteTime -Descending

# Restaurar un backup específico
Copy-Item "C:\Program Files\EHUkene\config\software_targets.json.backup_20260515_093022" `
          -Destination "C:\Program Files\EHUkene\config\software_targets.json" `
          -Force
```

---

## Mejoras futuras (roadmap)

### Versión 2.0 (planificada)

- [ ] Delta updates: enviar solo los cambios en lugar del fichero completo
- [ ] Firma digital del fichero para validar autenticidad
- [ ] Versionado por categorías (permitir actualizar solo navegadores, por ejemplo)
- [ ] API REST para consultar la versión más reciente disponible

### Versión 3.0 (ideas)

- [ ] Distribución del fichero desde el backend en lugar del paquete Ivanti
- [ ] Hot reload: el agente detecta cambios sin reiniciar
- [ ] Configuración por grupo de equipos (PAS, PDI, Aulas, etc.)

---

*UPV/EHU · Servicio de Informática · Proyecto EHUkene · v1.0*
